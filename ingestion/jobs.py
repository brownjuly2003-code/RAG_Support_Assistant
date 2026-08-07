"""Durable ingestion job service (tenant-owned job_id identity).

Async helpers for API routes; narrow synchronous SQLAlchemy session for the
Celery worker so state transitions do not reuse a global async engine across
fresh ``asyncio.run`` loops.

Worker ownership uses an opaque lease token with conditional CAS updates.
Async helpers for the synchronous upload path do not require a worker lease.

Upload idempotency (plan step 4.4 core) stores only SHA-256 key hash and
payload fingerprint; raw Idempotency-Key values never enter this module.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from db.models import IngestionJob
from utils.pii import redact_pii

logger = logging.getLogger(__name__)

JOB_STATUSES = frozenset({"queued", "running", "completed", "failed"})
_MAX_ERROR_LEN = 500

# URI userinfo (scheme://user:pass@host) and common secret assignments.
_URI_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s@]+@)")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|PWD|SECRET|TOKEN|API[_-]?KEY|"
    r"ACCESS[_-]?KEY|PRIVATE[_-]?KEY|DATABASE_URL|DSN))\s*[=:]\s*([^\s,;]+)"
)

_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _lease_duration_sec() -> int:
    """Validated lease horizon; shares the fail-closed path with ingestion.liveness."""
    from ingestion.liveness import lease_duration_sec

    return lease_duration_sec()


def _new_lease_token() -> str:
    # Cryptographically unpredictable opaque token; never log or serialize publicly.
    return secrets.token_urlsafe(32)


def _async_session() -> Any:
    """Indirection so tests can monkeypatch ``db.engine.async_session``."""
    from db.engine import async_session

    return async_session()


def _database_url_for_sync() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://rag:rag_dev_password@localhost:5432/rag_assistant",
    )
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _get_sync_session_factory() -> sessionmaker[Session]:
    global _sync_engine, _sync_session_factory
    if _sync_session_factory is not None:
        return _sync_session_factory
    _sync_engine = create_engine(_database_url_for_sync(), pool_pre_ping=True)
    _sync_session_factory = sessionmaker(_sync_engine, expire_on_commit=False)
    return _sync_session_factory


def get_sync_engine() -> Engine:
    """Return the worker's shared synchronous engine for scoped infrastructure work."""
    _get_sync_session_factory()
    if _sync_engine is None:
        raise RuntimeError("Synchronous database engine is unavailable")
    return _sync_engine


@contextmanager
def sync_session() -> Iterator[Session]:
    """Narrow sync session for Celery worker job state transitions."""
    factory = _get_sync_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def project_relative_source_path(project_root: Path, file_path: Path) -> str:
    """Store a project-relative path; never an absolute host path in the row."""
    try:
        return file_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return f"data/uploads/{file_path.name}"


def safe_error_message(exc: BaseException | str, *, limit: int = _MAX_ERROR_LEN) -> str:
    """Truncate and redact PII/secrets for durable/public error surfaces."""
    text = str(exc).strip() or "unknown error"
    text = redact_pii(text)
    text = _URI_USERINFO_RE.sub(r"\1***@", text)
    text = _SECRET_ASSIGN_RE.sub(r"\1=***", text)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _serialize_ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def job_public_dict(job: IngestionJob) -> dict[str, Any]:
    # lease_token is intentionally omitted — never public.
    return {
        "job_id": str(job.id),
        "task_id": job.celery_task_id,
        "tenant_id": job.tenant_id,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "created_at": _serialize_ts(job.created_at),
        "started_at": _serialize_ts(job.started_at),
        "finished_at": _serialize_ts(job.finished_at),
        "heartbeat_at": _serialize_ts(job.heartbeat_at),
        "lease_expires_at": _serialize_ts(job.lease_expires_at),
        "meta": {
            "filename": job.filename,
        },
    }


class IdempotencyConflictError(ValueError):
    """Same tenant Idempotency-Key hash with a different payload fingerprint."""


@dataclass(frozen=True, slots=True)
class CreateJobOutcome:
    """Explicit created/replayed result for upload identity reservation."""

    job: IngestionJob
    created: bool

    @property
    def outcome(self) -> Literal["created", "replayed"]:
        return "created" if self.created else "replayed"


def hash_idempotency_key(raw_key: str) -> str:
    """SHA-256 hex digest of the raw key; never store or log the raw value."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def compute_payload_fingerprint(safe_filename: str, content: bytes) -> str:
    """Bind normalized safe filename + exact uploaded bytes."""
    digest = hashlib.sha256()
    digest.update(safe_filename.encode("utf-8"))
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()


def reserved_celery_task_id(job_id: uuid.UUID | str) -> str:
    """Deterministic Celery task id reserved before broker publish."""
    return f"ingest-{job_id}"


async def create_ingestion_job(
    *,
    tenant_id: str,
    filename: str,
    source_path: str,
    job_id: uuid.UUID | None = None,
    celery_task_id: str | None = None,
    idempotency_key_hash: str | None = None,
    payload_fingerprint: str | None = None,
) -> IngestionJob:
    """Create a durable queued job (compatibility wrapper; always inserts)."""
    outcome = await create_or_reuse_ingestion_job(
        tenant_id=tenant_id,
        filename=filename,
        source_path=source_path,
        job_id=job_id,
        celery_task_id=celery_task_id,
        idempotency_key_hash=idempotency_key_hash,
        payload_fingerprint=payload_fingerprint,
    )
    return outcome.job


async def create_or_reuse_ingestion_job(
    *,
    tenant_id: str,
    filename: str,
    source_path: str,
    job_id: uuid.UUID | None = None,
    celery_task_id: str | None = None,
    idempotency_key_hash: str | None = None,
    payload_fingerprint: str | None = None,
) -> CreateJobOutcome:
    """Atomically create or reuse a tenant-scoped idempotent job row.

    When ``idempotency_key_hash`` is set, uniqueness is
    ``(tenant_id, idempotency_key_hash)``. Concurrent unique-conflict races
    roll back and re-read; same fingerprint → replayed, different → conflict.
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not filename:
        raise ValueError("filename is required")
    if not source_path:
        raise ValueError("source_path is required")
    if idempotency_key_hash is not None and not payload_fingerprint:
        raise ValueError("payload_fingerprint is required with idempotency_key_hash")

    new_id = job_id or uuid.uuid4()
    job = IngestionJob(
        id=new_id,
        tenant_id=tenant_id,
        filename=filename,
        source_path=source_path,
        status="queued",
        celery_task_id=celery_task_id,
        idempotency_key_hash=idempotency_key_hash,
        payload_fingerprint=payload_fingerprint,
        created_at=_utc_now(),
    )

    async with _async_session() as session:
        try:
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return CreateJobOutcome(job=job, created=True)
        except IntegrityError:
            await session.rollback()
            if not idempotency_key_hash:
                raise
            result = await session.execute(
                select(IngestionJob).where(
                    IngestionJob.tenant_id == tenant_id,
                    IngestionJob.idempotency_key_hash == idempotency_key_hash,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                # Unexpected constraint race; do not invent a second row.
                raise
            if existing.payload_fingerprint != payload_fingerprint:
                raise IdempotencyConflictError("Idempotency-Key conflict") from None
            return CreateJobOutcome(job=existing, created=False)


async def mark_source_ready(
    job_id: uuid.UUID,
    tenant_id: str,
) -> IngestionJob | None:
    """Atomically set source_ready_at only for queued, not-yet-ready jobs.

    Race-safe: requires exact tenant, job, ``status == 'queued'``, and
    ``source_ready_at IS NULL``. Terminal rows (failed/completed/running)
    cannot transition. On a zero-row update, return an existing
    queued+already-ready row only for idempotent success; otherwise ``None``.
    """
    now = _utc_now()
    async with _async_session() as session:
        result = await session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status == "queued",
                IngestionJob.source_ready_at.is_(None),
            )
            .values(source_ready_at=now)
        )
        if int(getattr(result, "rowcount", 0) or 0) == 1:
            await session.commit()
            refreshed = await session.execute(
                select(IngestionJob).where(
                    IngestionJob.id == job_id,
                    IngestionJob.tenant_id == tenant_id,
                )
            )
            return refreshed.scalar_one_or_none()

        await session.rollback()
        existing_result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if (
            existing is not None
            and existing.status == "queued"
            and existing.source_ready_at is not None
        ):
            return existing
        return None


async def set_celery_task_id(
    job_id: uuid.UUID,
    tenant_id: str,
    celery_task_id: str,
) -> IngestionJob | None:
    async with _async_session() as session:
        result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.celery_task_id = celery_task_id
        await session.commit()
        await session.refresh(job)
        return job


async def mark_job_running(job_id: uuid.UUID, tenant_id: str) -> IngestionJob | None:
    async with _async_session() as session:
        result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "running"
        job.started_at = job.started_at or _utc_now()
        job.error = None
        await session.commit()
        await session.refresh(job)
        return job


async def mark_job_completed(
    job_id: uuid.UUID,
    tenant_id: str,
    result: dict[str, Any] | None = None,
) -> IngestionJob | None:
    async with _async_session() as session:
        db_result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        job = db_result.scalar_one_or_none()
        if job is None:
            return None
        if job.started_at is None:
            job.started_at = _utc_now()
        job.status = "completed"
        job.result = result
        job.error = None
        job.finished_at = _utc_now()
        await session.commit()
        await session.refresh(job)
        return job


async def mark_job_failed(
    job_id: uuid.UUID,
    tenant_id: str,
    error: str,
) -> IngestionJob | None:
    async with _async_session() as session:
        result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        if job.started_at is None:
            job.started_at = _utc_now()
        job.status = "failed"
        job.error = safe_error_message(error)
        job.finished_at = _utc_now()
        await session.commit()
        await session.refresh(job)
        return job


async def get_job_for_tenant(
    job_id: uuid.UUID,
    tenant_id: str,
) -> IngestionJob | None:
    async with _async_session() as session:
        result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()


async def get_job_for_tenant_by_identifier(
    identifier: str,
    tenant_id: str,
) -> IngestionJob | None:
    """Resolve public job UUID or stored Celery task id; always tenant-scoped."""
    job_uuid: uuid.UUID | None
    try:
        job_uuid = uuid.UUID(identifier)
    except (ValueError, AttributeError, TypeError):
        job_uuid = None

    async with _async_session() as session:
        if job_uuid is not None:
            result = await session.execute(
                select(IngestionJob).where(
                    IngestionJob.id == job_uuid,
                    IngestionJob.tenant_id == tenant_id,
                )
            )
            job = result.scalar_one_or_none()
            if job is not None:
                return job

        result = await session.execute(
            select(IngestionJob).where(
                IngestionJob.celery_task_id == identifier,
                IngestionJob.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()


# --- Synchronous worker helpers ------------------------------------------------


class JobIdentityError(LookupError):
    """Unknown or tenant-mismatched durable job identity."""


class JobOwnershipError(RuntimeError):
    """Claim/heartbeat/terminal CAS failed (lost lease, duplicate claim, etc.)."""


def sync_require_job(job_id: uuid.UUID, tenant_id: str) -> IngestionJob:
    with sync_session() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobIdentityError(f"Ingestion job {job_id} not found for tenant {tenant_id}")
        # Detach a lightweight snapshot for the caller.
        session.expunge(job)
        return job


def sync_claim_running(job_id: uuid.UUID, tenant_id: str) -> str:
    """Atomically claim a queued job for this worker; return opaque lease token.

    Fail closed on missing/wrong-tenant/non-queued rows before any vector work.
    """
    if not tenant_id or not str(tenant_id).strip():
        raise JobOwnershipError("tenant_id is required for job claim")

    token = _new_lease_token()
    now = _utc_now()
    lease_sec = _lease_duration_sec()
    expires = now + timedelta(seconds=lease_sec)

    with sync_session() as session:
        result = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status == "queued",
            )
            .values(
                status="running",
                lease_token=token,
                heartbeat_at=now,
                lease_expires_at=expires,
                started_at=now,
                error=None,
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            session.rollback()
            raise JobOwnershipError(
                f"Failed to claim ingestion job {job_id} for tenant {tenant_id}"
            )
        session.commit()
    return token


def sync_extend_lease(job_id: uuid.UUID, tenant_id: str, lease_token: str) -> bool:
    """Conditional heartbeat extension; True only when ownership matches."""
    if not lease_token:
        return False
    now = _utc_now()
    expires = now + timedelta(seconds=_lease_duration_sec())
    with sync_session() as session:
        result = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == lease_token,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=expires,
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            session.rollback()
            return False
        session.commit()
        return True


def sync_mark_completed(
    job_id: uuid.UUID,
    tenant_id: str,
    lease_token: str,
    result: dict[str, Any] | None = None,
) -> None:
    """CAS completed transition; requires exact running lease ownership."""
    now = _utc_now()
    with sync_session() as session:
        res = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == lease_token,
            )
            .values(
                status="completed",
                result=result,
                error=None,
                finished_at=now,
                lease_token=None,
                # Preserve last successful heartbeat for observability.
                lease_expires_at=None,
            )
        )
        if int(getattr(res, "rowcount", 0) or 0) != 1:
            session.rollback()
            raise JobOwnershipError(f"Lost lease completing ingestion job {job_id}")
        session.commit()


def sync_mark_failed(
    job_id: uuid.UUID,
    tenant_id: str,
    lease_token: str,
    error: str,
) -> None:
    """CAS failed transition; requires exact running lease ownership."""
    now = _utc_now()
    redacted = safe_error_message(error)
    with sync_session() as session:
        res = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == lease_token,
            )
            .values(
                status="failed",
                error=redacted,
                finished_at=now,
                lease_token=None,
                # Preserve last successful heartbeat for observability.
                lease_expires_at=None,
            )
        )
        if int(getattr(res, "rowcount", 0) or 0) != 1:
            session.rollback()
            raise JobOwnershipError(f"Lost lease failing ingestion job {job_id}")
        session.commit()


def sync_list_known_job_object_refs(tenant_id: str) -> tuple[Any, ...]:
    """Load durable ``(job_id, source_path)`` refs for one tenant (read-only).

    Returns ``KnownJobObjectRef`` instances for inventory preview (plan 2.4f).
    Blank ``source_path`` rows are skipped (cannot protect a path). Never
    mutates rows or filesystem state.
    """
    # Local import keeps jobs↔inventory coupling to this preview helper only.
    from ingestion.job_object_inventory import KnownJobObjectRef

    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id is required")
    tid = str(tenant_id).strip()

    with sync_session() as session:
        rows = session.execute(
            select(IngestionJob.id, IngestionJob.source_path)
            .where(IngestionJob.tenant_id == tid)
            .order_by(IngestionJob.created_at, IngestionJob.id)
        ).all()

    refs = []
    for job_id, source_path in rows:
        path = str(source_path or "").strip()
        if not path:
            continue
        refs.append(KnownJobObjectRef(job_id=str(job_id), source_path=path))
    return tuple(refs)


def sync_list_job_statuses_for_tenant(tenant_id: str) -> dict[str, str]:
    """Load durable ``job_id → status`` map for one tenant (read-only).

    Used by operator CLI transition ownership annotations (plan 2.4k).
    Blank/missing status values are skipped (callers treat missing keys as
    unknown). Never mutates rows or filesystem state.
    """
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id is required")
    tid = str(tenant_id).strip()

    with sync_session() as session:
        rows = session.execute(
            select(IngestionJob.id, IngestionJob.status)
            .where(IngestionJob.tenant_id == tid)
            .order_by(IngestionJob.created_at, IngestionJob.id)
        ).all()

    statuses: dict[str, str] = {}
    for job_id, status in rows:
        sid = str(job_id).strip()
        st = str(status or "").strip().lower()
        if not sid or not st:
            continue
        statuses[sid] = st
    return statuses

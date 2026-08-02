"""Durable ingestion job service (tenant-owned job_id identity).

Async helpers for API routes; narrow synchronous SQLAlchemy session for the
Celery worker so state transitions do not reuse a global async engine across
fresh ``asyncio.run`` loops.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
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

_sync_engine = None
_sync_session_factory: sessionmaker[Session] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        "meta": {
            "filename": job.filename,
        },
    }


async def create_ingestion_job(
    *,
    tenant_id: str,
    filename: str,
    source_path: str,
    job_id: uuid.UUID | None = None,
) -> IngestionJob:
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not filename:
        raise ValueError("filename is required")
    if not source_path:
        raise ValueError("source_path is required")

    job = IngestionJob(
        id=job_id or uuid.uuid4(),
        tenant_id=tenant_id,
        filename=filename,
        source_path=source_path,
        status="queued",
        created_at=_utc_now(),
    )
    async with _async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


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


def sync_require_job(job_id: uuid.UUID, tenant_id: str) -> IngestionJob:
    with sync_session() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobIdentityError(
                f"Ingestion job {job_id} not found for tenant {tenant_id}"
            )
        # Detach a lightweight snapshot for the caller.
        session.expunge(job)
        return job


def sync_mark_running(job_id: uuid.UUID, tenant_id: str) -> None:
    with sync_session() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobIdentityError(
                f"Ingestion job {job_id} not found for tenant {tenant_id}"
            )
        job.status = "running"
        job.started_at = job.started_at or _utc_now()
        job.error = None
        session.commit()


def sync_mark_completed(
    job_id: uuid.UUID,
    tenant_id: str,
    result: dict[str, Any] | None = None,
) -> None:
    with sync_session() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobIdentityError(
                f"Ingestion job {job_id} not found for tenant {tenant_id}"
            )
        if job.started_at is None:
            job.started_at = _utc_now()
        job.status = "completed"
        job.result = result
        job.error = None
        job.finished_at = _utc_now()
        session.commit()


def sync_mark_failed(job_id: uuid.UUID, tenant_id: str, error: str) -> None:
    with sync_session() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobIdentityError(
                f"Ingestion job {job_id} not found for tenant {tenant_id}"
            )
        if job.started_at is None:
            job.started_at = _utc_now()
        job.status = "failed"
        job.error = safe_error_message(error)
        job.finished_at = _utc_now()
        session.commit()

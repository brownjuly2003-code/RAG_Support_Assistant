"""Document upload and durable ingestion job endpoints."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re as _re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from api.rate_limit import limiter
from auth.dependencies import require_role
from ingestion.jobs import CreateJobOutcome
from monitoring import prometheus as prometheus_metrics
from utils.tenant_naming import physical_tenant_component

router = APIRouter()
logger = logging.getLogger(__name__)

# Optional HTTP Idempotency-Key (never reuse X-Request-Id).
_IDEMPOTENCY_KEY_RE = _re.compile(r"^[A-Za-z0-9._:~-]{16,128}$")

# Fixed internal directory under the tenant upload root for job-scoped originals.
# Kept nested so recursive=False loaders continue to see only the flat corpus view.
_JOB_OBJECTS_DIRNAME = "job-objects"
# Nested recovery tree for pre-2.4a flat-only originals (content-addressed).
_LEGACY_PREVIOUS_DIRNAME = "legacy-previous"


def _tenant_upload_directory(upload_root: Path, tenant_id: str) -> Path:
    tenant = tenant_id or "default"
    if tenant == "default":
        return upload_root
    return upload_root / physical_tenant_component(tenant, max_length=63)


def _job_immutable_path(upload_dir: Path, job_id: uuid.UUID, safe_name: str) -> Path:
    """Derive a job-scoped path that must remain under the tenant upload root."""
    candidate = upload_dir / _JOB_OBJECTS_DIRNAME / str(job_id) / safe_name
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(upload_dir.resolve(strict=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid filename") from exc
    return candidate


def _legacy_previous_path(upload_dir: Path, prior_bytes: bytes, safe_name: str) -> Path:
    """Content-addressed recovery path for a prior flat original under tenant root."""
    digest = hashlib.sha256(prior_bytes).hexdigest()
    candidate = (
        upload_dir
        / _JOB_OBJECTS_DIRNAME
        / _LEGACY_PREVIOUS_DIRNAME
        / digest
        / safe_name
    )
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(upload_dir.resolve(strict=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid filename") from exc
    return candidate


def _write_bytes_exclusive(path: Path, data: bytes) -> None:
    """Create a new file once; never overwrite an existing job object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _preserve_prior_flat_bytes(
    current_path: Path,
    upload_dir: Path,
    safe_name: str,
) -> None:
    """If a flat current file exists, keep its bytes in an immutable recovery object.

    Used for the pre-2.4a transition: a legacy flat-only original must remain
    recoverable before the flat current view is replaced. Content-addressed
    exclusive create never overwrites a different payload at the same path.
    """
    if not current_path.is_file():
        return
    prior_bytes = current_path.read_bytes()
    recovery_path = _legacy_previous_path(upload_dir, prior_bytes, safe_name)
    try:
        _write_bytes_exclusive(recovery_path, prior_bytes)
    except FileExistsError:
        # Same content digest path already present — require identical bytes.
        if recovery_path.read_bytes() != prior_bytes:
            raise OSError(
                "legacy previous recovery object exists with different bytes"
            ) from None
        return


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    """Replace the flat current corpus file without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


class UploadResponse(BaseModel):
    status: str
    filename: str
    message: str
    job_id: str
    tenant_id: str
    task_id: str | None = None
    assigned_categories: list[str] = Field(default_factory=list)
    idempotency_replayed: bool = False


class JobStatusResponse(BaseModel):
    job_id: str
    task_id: str | None = None
    tenant_id: str
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    meta: dict | None = None


# Backward-compatible alias name for OpenAPI / older imports.
TaskStatusResponse = JobStatusResponse


def _parse_idempotency_key(request: Request) -> str | None:
    """Read optional Idempotency-Key; validate present keys; never log raw value."""
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    # Reject whitespace-padded values as invalid (do not silently strip).
    if not _IDEMPOTENCY_KEY_RE.fullmatch(raw):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return raw


def _publish_retry_policy(settings: object) -> dict[str, float | int]:
    max_retries = int(getattr(settings, "ingestion_publish_max_retries", 2))
    delay = float(getattr(settings, "ingestion_publish_retry_delay_sec", 0.2))
    return {
        "max_retries": max_retries,
        "interval_start": delay,
        "interval_step": 0,
        "interval_max": delay,
    }


def _upload_response_from_job(
    job: object,
    *,
    filename: str,
    tenant_id: str,
    replayed: bool,
    assigned_categories: list[str] | None = None,
) -> UploadResponse:
    """Map durable job state to public upload response (generic messages)."""
    status = getattr(job, "status", "queued")
    task_id = getattr(job, "celery_task_id", None)
    job_id_str = str(job.id)  # type: ignore[attr-defined]
    categories = list(assigned_categories or [])

    if status in ("queued", "running"):
        message = "File uploaded. Processing in background."
        if task_id:
            message = f"File uploaded. Processing in background. task_id={task_id}"
        return UploadResponse(
            status="accepted",
            filename=filename,
            message=message,
            job_id=job_id_str,
            tenant_id=tenant_id,
            task_id=task_id,
            assigned_categories=categories,
            idempotency_replayed=replayed,
        )
    if status == "completed":
        return UploadResponse(
            status="ok",
            filename=filename,
            message="File uploaded and indexed.",
            job_id=job_id_str,
            tenant_id=tenant_id,
            task_id=task_id,
            assigned_categories=categories,
            idempotency_replayed=replayed,
        )
    # failed (and any unexpected terminal)
    return UploadResponse(
        status="partial",
        filename=filename,
        message="File saved but processing failed.",
        job_id=job_id_str,
        tenant_id=tenant_id,
        task_id=task_id,
        assigned_categories=categories,
        idempotency_replayed=replayed,
    )


async def _create_or_reuse_job_or_fail(
    *,
    tenant_id: str,
    filename: str,
    source_path: str,
    job_id: uuid.UUID | None,
    celery_task_id: str | None,
    idempotency_key_hash: str | None,
    payload_fingerprint: str | None,
) -> CreateJobOutcome:
    from ingestion.jobs import (
        IdempotencyConflictError,
        create_or_reuse_ingestion_job,
    )

    try:
        return await create_or_reuse_ingestion_job(
            tenant_id=tenant_id,
            filename=filename,
            source_path=source_path,
            job_id=job_id,
            celery_task_id=celery_task_id,
            idempotency_key_hash=idempotency_key_hash,
            payload_fingerprint=payload_fingerprint,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key conflict",
        ) from exc
    except Exception as exc:
        # Boundary log: type only — raw message may contain credentials/PII.
        logger.error(
            "Failed to create durable ingestion job error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create ingestion job",
        ) from exc


def _durable_transition_http_error(job_id: uuid.UUID, phase: str) -> HTTPException:
    """Generic 5xx when authoritative job state cannot be recorded."""
    logger.error(
        "Durable job transition failed job_id=%s phase=%s",
        job_id,
        phase,
    )
    return HTTPException(
        status_code=500,
        detail="Failed to update ingestion job state",
    )


async def _mark_failed(job_id: uuid.UUID, tenant_id: str, error: str) -> None:
    from ingestion.jobs import mark_job_failed

    try:
        job = await mark_job_failed(job_id, tenant_id, error)
    except Exception as exc:
        # No exc_info: traceback exception line carries the raw message.
        logger.error(
            "Failed to mark job %s failed (phase=failed) error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise _durable_transition_http_error(job_id, "failed") from exc
    if job is None:
        raise _durable_transition_http_error(job_id, "failed")


async def _mark_running(job_id: uuid.UUID, tenant_id: str) -> None:
    from ingestion.jobs import mark_job_running

    try:
        job = await mark_job_running(job_id, tenant_id)
    except Exception as exc:
        logger.error(
            "Failed to mark job %s running (phase=running) error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise _durable_transition_http_error(job_id, "running") from exc
    if job is None:
        raise _durable_transition_http_error(job_id, "running")


async def _mark_completed(
    job_id: uuid.UUID,
    tenant_id: str,
    result: dict | None,
) -> None:
    from ingestion.jobs import mark_job_completed

    try:
        job = await mark_job_completed(job_id, tenant_id, result)
    except Exception as exc:
        logger.error(
            "Failed to mark job %s completed (phase=completed) error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise _durable_transition_http_error(job_id, "completed") from exc
    if job is None:
        raise _durable_transition_http_error(job_id, "completed")


async def _mark_source_ready_or_fail(job_id: uuid.UUID, tenant_id: str) -> None:
    from ingestion.jobs import mark_source_ready

    try:
        job = await mark_source_ready(job_id, tenant_id)
    except Exception as exc:
        logger.error(
            "Failed to mark job %s source_ready error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise _durable_transition_http_error(job_id, "source_ready") from exc
    if job is None:
        raise _durable_transition_http_error(job_id, "source_ready")


def _publish_async_ingest(
    *,
    file_path: Path,
    job_id: uuid.UUID,
    tenant_id: str,
    settings: object,
) -> None:
    """Bounded broker publish only. Raises on failure after policy retries."""
    from tasks.ingest_task import ingest_document

    reserved = f"ingest-{job_id}"
    ingest_document.apply_async(
        args=[str(file_path), str(job_id), tenant_id],
        task_id=reserved,
        retry=True,
        retry_policy=_publish_retry_policy(settings),
    )


def _publish_unavailable(job_id: uuid.UUID, exc: BaseException) -> HTTPException:
    logger.error(
        "Ingestion broker publish failed job_id=%s phase=publish error_type=%s",
        job_id,
        type(exc).__name__,
    )
    return HTTPException(
        status_code=503,
        detail="Ingestion queue temporarily unavailable",
        headers={"X-Ingestion-Job-Id": str(job_id)},
    )


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _user: dict = Depends(require_role("agent", "admin")),
) -> UploadResponse:
    """Upload a document (PDF/DOCX/TXT/MD) and ingest it into the vector store."""
    _app = _app_module()
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".html"}
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed))}",
        )

    # Optional idempotency key — validated before any row/file mutation.
    raw_idem_key = _parse_idempotency_key(request)

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    safe_name = Path(file.filename.replace("\\", "/")).name
    safe_name = _re.sub(r"[^\w\-.]", "_", safe_name)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_root = _app.PROJECT_ROOT / "data" / "uploads"
    upload_dir = _tenant_upload_directory(upload_root, tenant)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Flat tenant corpus view used by recursive=False loaders / reindex / publish.
    current_path = upload_dir / safe_name
    settings = _app.get_settings()
    upload_limit = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)

    # 1) Buffer/validate body and compute fingerprint before DB/file write.
    try:
        content = bytearray()
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > upload_limit:
                try:
                    prometheus_metrics.record_body_size_rejection("upload_too_large")
                except Exception:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds limit of {upload_limit} bytes",
                )
        content_bytes = bytes(content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to read upload") from exc

    from ingestion.jobs import (
        compute_payload_fingerprint,
        hash_idempotency_key,
        project_relative_source_path,
        reserved_celery_task_id,
    )

    fingerprint = compute_payload_fingerprint(safe_name, content_bytes)
    key_hash = hash_idempotency_key(raw_idem_key) if raw_idem_key is not None else None

    # 2) Allocate durable identity; reserve Celery id for default async path.
    # Candidate job UUID also keys the immutable original object path.
    job_id = uuid.uuid4()
    immutable_path = _job_immutable_path(upload_dir, job_id, safe_name)
    source_path = project_relative_source_path(Path(_app.PROJECT_ROOT), immutable_path)
    celery_task_id = reserved_celery_task_id(job_id) if tenant == "default" else None

    outcome = await _create_or_reuse_job_or_fail(
        tenant_id=tenant,
        filename=safe_name,
        source_path=source_path,
        job_id=job_id,
        celery_task_id=celery_task_id,
        idempotency_key_hash=key_hash,
        payload_fingerprint=fingerprint if key_hash is not None else None,
    )
    job = outcome.job
    job_id = job.id
    job_id_str = str(job_id)
    replayed = not outcome.created

    # Replay path: never write immutable object or flat current view;
    # may republish only when source-ready+queued (flat path for loaders).
    if replayed:
        await _app.log_audit(
            actor=_user.get("sub", "anonymous"),
            action="upload",
            resource=f"document:{safe_name}",
            tenant_id=tenant,
            detail={"tenant": tenant, "job_id": job_id_str, "idempotency_replayed": True},
            ip_address=request.client.host if request.client else None,
        )
        if (
            tenant == "default"
            and job.status == "queued"
            and job.source_ready_at is not None
            and job.celery_task_id
        ):
            try:
                # Offload sync Celery client I/O so bounded broker retries
                # never block the FastAPI event loop (health/ask stay live).
                await asyncio.to_thread(
                    _publish_async_ingest,
                    file_path=current_path,
                    job_id=job_id,
                    tenant_id=tenant,
                    settings=settings,
                )
            except Exception as exc:
                raise _publish_unavailable(job_id, exc) from exc
        # running/completed/failed or not-yet-source-ready: never publish.
        return _upload_response_from_job(
            job,
            filename=safe_name,
            tenant_id=tenant,
            replayed=True,
            assigned_categories=[],
        )

    # 3) Creator writes job-scoped immutable original once, preserves any
    # pre-existing flat legacy bytes under a nested recovery object, then
    # refreshes the flat current corpus view only after both succeed.
    try:
        await asyncio.to_thread(_write_bytes_exclusive, immutable_path, content_bytes)
        await asyncio.to_thread(
            _preserve_prior_flat_bytes,
            current_path,
            upload_dir,
            safe_name,
        )
        await asyncio.to_thread(_atomic_replace_bytes, current_path, content_bytes)
    except Exception as exc:
        # Durable terminal fail; do not publish. Flat view is refreshed only
        # after immutable + prior-preserve success, so a failed step leaves it.
        try:
            await _mark_failed(job_id, tenant, "Failed to save file")
        except HTTPException:
            raise
        raise HTTPException(status_code=500, detail="Failed to save file") from exc

    await _mark_source_ready_or_fail(job_id, tenant)

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="upload",
        resource=f"document:{safe_name}",
        tenant_id=tenant,
        detail={"tenant": tenant, "job_id": job_id_str},
        ip_address=request.client.host if request.client else None,
    )

    docs = None
    assigned_categories: list[str] = []
    if _app._DocumentLoader is not None:
        try:
            from ingestion.categorizer import annotate_documents_with_categories

            loader = _app._DocumentLoader(recursive=False)
            # Document parsing and LLM categorization are blocking — keep them
            # off the event loop so concurrent /ask requests are not stalled.
            docs = await asyncio.to_thread(loader.load_documents, str(upload_dir))
            if docs:
                assigned_by_source = await asyncio.to_thread(
                    annotate_documents_with_categories, docs, tenant_id=tenant
                )
                assigned_categories = list(assigned_by_source.get(safe_name) or [])
        except Exception as exc:
            # Category providers can emit credential-bearing errors; type only.
            logger.warning(
                "Category pre-processing failed for %s error_type=%s",
                safe_name,
                type(exc).__name__,
            )

    # Default tenant: async Celery publish with reserved task id (no sync fallback).
    # Worker still receives the flat current-view path (parent = tenant corpus dir).
    if tenant == "default":
        try:
            # Offload sync Celery client I/O so bounded broker retries
            # never block the FastAPI event loop (health/ask stay live).
            await asyncio.to_thread(
                _publish_async_ingest,
                file_path=current_path,
                job_id=job_id,
                tenant_id=tenant,
                settings=settings,
            )
        except Exception as exc:
            # Leave source-ready queued row with reserved task id; return 503.
            raise _publish_unavailable(job_id, exc) from exc

        if getattr(settings, "llm_cache_enabled", False):
            deleted = _app.cache_delete_pattern(f"llm_resp:{tenant}:*")
            logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
        task_id = job.celery_task_id or reserved_celery_task_id(job_id)
        return UploadResponse(
            status="accepted",
            filename=safe_name,
            message=f"File uploaded. Processing in background. task_id={task_id}",
            job_id=job_id_str,
            tenant_id=tenant,
            task_id=task_id,
            assigned_categories=assigned_categories,
            idempotency_replayed=False,
        )

    # Non-default tenants: synchronous indexing (celery_task_id remains null).
    if _app._DocumentLoader is not None and _app._build_vector_store is not None:
        await _mark_running(job_id, tenant)
        try:
            if docs is None:
                loader = _app._DocumentLoader(recursive=False)
                docs = await asyncio.to_thread(loader.load_documents, str(upload_dir))
            if docs:
                # Full re-embedding of the tenant corpus — minutes of CPU work.
                # Must not run on the event loop (it would freeze every /ask
                # and health probe for the duration of the rebuild).
                success = await asyncio.to_thread(
                    _app._rebuild_vector_store_from_docs, docs, tenant_id=tenant
                )
                if success:
                    if getattr(settings, "llm_cache_enabled", False):
                        deleted = _app.cache_delete_pattern(f"llm_resp:{tenant}:*")
                        logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
                    result_payload = {
                        "status": "ok",
                        "docs_count": len(docs),
                        "message": f"Indexed {len(docs)} document(s)",
                    }
                    await _mark_completed(job_id, tenant, result_payload)
                    return UploadResponse(
                        status="ok",
                        filename=safe_name,
                        message=f"File uploaded and indexed. {len(docs)} document(s) processed.",
                        job_id=job_id_str,
                        tenant_id=tenant,
                        assigned_categories=assigned_categories,
                        idempotency_replayed=False,
                    )
                await _mark_failed(job_id, tenant, "File saved but indexing failed")
                return UploadResponse(
                    status="partial",
                    filename=safe_name,
                    message="File saved but indexing failed. Check server logs.",
                    job_id=job_id_str,
                    tenant_id=tenant,
                    assigned_categories=assigned_categories,
                    idempotency_replayed=False,
                )
            await _mark_failed(job_id, tenant, "No text content could be extracted")
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message="File saved but no text content could be extracted.",
                job_id=job_id_str,
                tenant_id=tenant,
                assigned_categories=assigned_categories,
                idempotency_replayed=False,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Ingestion error for job %s tenant %s phase=ingest error_type=%s",
                job_id_str,
                tenant,
                type(exc).__name__,
            )
            await _mark_failed(job_id, tenant, "Document ingestion failed")
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message="File saved but ingestion failed.",
                job_id=job_id_str,
                tenant_id=tenant,
                assigned_categories=assigned_categories,
                idempotency_replayed=False,
            )

    await _mark_failed(
        job_id,
        tenant,
        "Document loader or vector store builder not available for indexing",
    )
    return UploadResponse(
        status="partial",
        filename=safe_name,
        message="File saved. Document loader or vector store builder not available for indexing.",
        job_id=job_id_str,
        tenant_id=tenant,
        assigned_categories=assigned_categories,
        idempotency_replayed=False,
    )


async def _job_status_response(identifier: str, tenant_id: str) -> JobStatusResponse:
    from ingestion.jobs import get_job_for_tenant_by_identifier, job_public_dict

    job = await get_job_for_tenant_by_identifier(identifier, tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = job_public_dict(job)
    return JobStatusResponse(**payload)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JobStatusResponse:
    """Canonical durable ingestion job status (ORM/PostgreSQL only)."""
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return await _job_status_response(job_id, tenant)


@router.get("/tasks/{task_id}", response_model=JobStatusResponse)
async def get_task_status(
    task_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JobStatusResponse:
    """Compatibility alias: resolve public job UUID or stored Celery task id."""
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return await _job_status_response(task_id, tenant)

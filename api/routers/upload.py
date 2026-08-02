"""Document upload and durable ingestion job endpoints."""
from __future__ import annotations

import asyncio
import logging
import re as _re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from api.rate_limit import limiter
from auth.dependencies import require_role
from monitoring import prometheus as prometheus_metrics

router = APIRouter()
logger = logging.getLogger(__name__)


class UploadResponse(BaseModel):
    status: str
    filename: str
    message: str
    job_id: str
    tenant_id: str
    task_id: str | None = None
    assigned_categories: list[str] = Field(default_factory=list)


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


async def _create_job_or_fail(
    *,
    tenant_id: str,
    filename: str,
    source_path: str,
) -> uuid.UUID:
    from ingestion.jobs import create_ingestion_job

    try:
        job = await create_ingestion_job(
            tenant_id=tenant_id,
            filename=filename,
            source_path=source_path,
        )
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
    return job.id


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

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    safe_name = Path(file.filename.replace("\\", "/")).name
    safe_name = _re.sub(r"[^\w\-.]", "_", safe_name)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_root = _app.PROJECT_ROOT / "data" / "uploads"
    if tenant == "default":
        upload_dir = upload_root
    else:
        upload_dir = upload_root / _re.sub(r"[^A-Za-z0-9_\-]", "_", tenant)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / safe_name
    settings = _app.get_settings()
    upload_limit = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)
    docs = None
    assigned_categories: list[str] = []
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
        await asyncio.to_thread(file_path.write_bytes, bytes(content))
    except HTTPException:
        raise
    except Exception as exc:
        # Generic detail only — OSError often embeds absolute host paths.
        raise HTTPException(status_code=500, detail="Failed to save file") from exc

    from ingestion.jobs import project_relative_source_path

    source_path = project_relative_source_path(Path(_app.PROJECT_ROOT), file_path)
    job_id = await _create_job_or_fail(
        tenant_id=tenant,
        filename=safe_name,
        source_path=source_path,
    )
    job_id_str = str(job_id)

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="upload",
        resource=f"document:{safe_name}",
        tenant_id=tenant,
        detail={"tenant": tenant, "job_id": job_id_str},
        ip_address=request.client.host if request.client else None,
    )

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

    if tenant == "default":
        try:
            from ingestion.jobs import set_celery_task_id
            from tasks.ingest_task import ingest_document

            task = ingest_document.delay(str(file_path), job_id_str, tenant)
        except Exception as exc:
            logger.info("Celery async upload unavailable, falling back to sync: %s", type(exc).__name__)
        else:
            # Fail closed: never return accepted with a task alias the DB cannot resolve.
            try:
                linked = await set_celery_task_id(job_id, tenant, task.id)
            except Exception as exc:
                logger.error(
                    "Failed to store celery_task_id for job %s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to record background task identity",
                ) from exc
            if linked is None:
                logger.error(
                    "Failed to store celery_task_id for job %s: row missing",
                    job_id,
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to record background task identity",
                )
            if getattr(settings, "llm_cache_enabled", False):
                deleted = _app.cache_delete_pattern(f"llm_resp:{tenant}:*")
                logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
            return UploadResponse(
                status="accepted",
                filename=safe_name,
                message=f"File uploaded. Processing in background. task_id={task.id}",
                job_id=job_id_str,
                tenant_id=tenant,
                task_id=task.id,
                assigned_categories=assigned_categories,
            )

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
                    )
                await _mark_failed(job_id, tenant, "File saved but indexing failed")
                return UploadResponse(
                    status="partial",
                    filename=safe_name,
                    message="File saved but indexing failed. Check server logs.",
                    job_id=job_id_str,
                    tenant_id=tenant,
                    assigned_categories=assigned_categories,
                )
            await _mark_failed(job_id, tenant, "No text content could be extracted")
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message="File saved but no text content could be extracted.",
                job_id=job_id_str,
                tenant_id=tenant,
                assigned_categories=assigned_categories,
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

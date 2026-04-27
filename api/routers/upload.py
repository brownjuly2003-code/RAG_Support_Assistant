"""Document upload and background task endpoints."""
from __future__ import annotations

import logging
import re as _re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

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
    tenant_id: str = "default"
    assigned_categories: list[str] = Field(default_factory=list)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    meta: dict | None = None


def _app_module():
    from api import app as _app  # noqa: PLC0415

    return _app


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
        file_path.write_bytes(bytes(content))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="upload",
        resource=f"document:{safe_name}",
        detail={"tenant": tenant},
        ip_address=request.client.host if request.client else None,
    )

    if _app._DocumentLoader is not None:
        try:
            from ingestion.categorizer import annotate_documents_with_categories

            loader = _app._DocumentLoader(recursive=False)
            docs = loader.load_documents(str(upload_dir))
            if docs:
                assigned_by_source = annotate_documents_with_categories(docs, tenant_id=tenant)
                assigned_categories = list(assigned_by_source.get(safe_name) or [])
        except Exception as exc:
            logger.warning("Category pre-processing failed for %s: %s", safe_name, exc)

    if tenant == "default":
        try:
            from tasks.ingest_task import ingest_document

            task = ingest_document.delay(str(file_path))
            if getattr(settings, "llm_cache_enabled", False):
                deleted = _app.cache_delete_pattern(f"llm_resp:{tenant}:*")
                logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
            return UploadResponse(
                status="accepted",
                filename=safe_name,
                message=f"File uploaded. Processing in background. task_id={task.id}",
                assigned_categories=assigned_categories,
            )
        except Exception as exc:
            logger.info("Celery async upload unavailable, falling back to sync: %s", exc)

    if _app._DocumentLoader is not None and _app._build_vector_store is not None:
        try:
            if docs is None:
                loader = _app._DocumentLoader(recursive=False)
                docs = loader.load_documents(str(upload_dir))
            if docs:
                success = _app._rebuild_vector_store_from_docs(docs, tenant_id=tenant)
                if success:
                    if getattr(settings, "llm_cache_enabled", False):
                        deleted = _app.cache_delete_pattern(f"llm_resp:{tenant}:*")
                        logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
                    return UploadResponse(
                        status="ok",
                        filename=safe_name,
                        message=f"File uploaded and indexed. {len(docs)} document(s) processed.",
                        assigned_categories=assigned_categories,
                    )
                else:
                    return UploadResponse(
                        status="partial",
                        filename=safe_name,
                        message="File saved but indexing failed. Check server logs.",
                        assigned_categories=assigned_categories,
                    )
            else:
                return UploadResponse(
                    status="partial",
                    filename=safe_name,
                    message="File saved but no text content could be extracted.",
                    assigned_categories=assigned_categories,
                )
        except Exception as exc:
            logger.error("Ingestion error for %s: %s", file.filename, exc, exc_info=True)
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message=f"File saved but ingestion failed: {exc}",
                assigned_categories=assigned_categories,
            )
    else:
        return UploadResponse(
            status="partial",
            filename=safe_name,
            message="File saved. Document loader or vector store builder not available for indexing.",
            assigned_categories=assigned_categories,
        )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> TaskStatusResponse:
    """Check background task status."""
    _app = _app_module()
    try:
        from tasks.celery_app import celery_app

        result = celery_app.AsyncResult(task_id)
        result_payload: dict | None = None
        meta_payload: dict | None = None

        if result.ready():
            if isinstance(result.result, dict):
                result_payload = result.result
            elif result.result is not None:
                result_payload = {"detail": str(result.result)}
            if result.status == "SUCCESS" and result_payload and result_payload.get("status") == "ok":
                _app.initialize_vector_store()
        elif isinstance(result.info, dict):
            meta_payload = result.info
        elif result.info is not None:
            meta_payload = {"detail": str(result.info)}

        return TaskStatusResponse(
            task_id=task_id,
            status=result.status,
            result=result_payload,
            meta=meta_payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Task backend error: {exc}")

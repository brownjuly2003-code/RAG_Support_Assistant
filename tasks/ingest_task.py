"""Background task: ingest document into vector store with durable job state."""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from celery import Task

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Phase-level terminal messages for durable/public surfaces (no raw exc details).
_MSG_FILE_NOT_FOUND = "File not found"
_MSG_LOADING_FAILED = "Document loading failed"
_MSG_NO_CONTENT = "No text content extracted"
_MSG_INDEXING_FAILED = "Vector indexing failed"
_MSG_LEASE_LOST = "Ingestion job lease lost"


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(job_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid job_id: {job_id!r}") from exc


def _best_effort_progress(task: Task, *, state: str, meta: dict[str, Any]) -> None:
    """Celery result-backend progress is non-authoritative; never block durable work."""
    try:
        task.update_state(state=state, meta=meta)
    except Exception as exc:
        logger.warning(
            "Celery progress update failed job_id=%s step=%s error_type=%s",
            meta.get("job_id"),
            meta.get("step"),
            type(exc).__name__,
        )


def _safe_terminal_failed(
    *,
    mark_failed: Callable[[uuid.UUID, str, str, str], None],
    job_uuid: uuid.UUID,
    tenant_id: str,
    lease_token: str,
    message: str,
) -> None:
    """Best-effort CAS fail; lost lease must not raise over the original error."""
    try:
        mark_failed(job_uuid, tenant_id, lease_token, message)
    except Exception as exc:
        logger.warning(
            "Durable failed transition skipped job_id=%s phase=terminal error_type=%s",
            job_uuid,
            type(exc).__name__,
        )


@celery_app.task(bind=True, name="tasks.ingest_document")
def ingest_document(self: Task, file_path: str, job_id: str, tenant_id: str) -> dict:
    """Load and index documents; durable DB row is the source of truth."""
    from ingestion.jobs import (
        JobIdentityError,
        JobOwnershipError,
        sync_claim_running,
        sync_mark_completed,
        sync_mark_failed,
        sync_require_job,
    )
    from ingestion.liveness import JobLeaseHeartbeat, heartbeat_interval_sec

    job_uuid = _parse_job_id(job_id)
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id is required")

    # Fail closed before any vector-store mutation on unknown/foreign identity.
    try:
        sync_require_job(job_uuid, tenant_id)
    except JobIdentityError:
        logger.error(
            "Rejecting ingest for unknown/mismatched job_id=%s tenant_id=%s",
            job_id,
            tenant_id,
        )
        raise

    # Atomic queued→running claim with lease; duplicate/lost claim fails closed.
    try:
        lease_token = sync_claim_running(job_uuid, tenant_id)
    except JobOwnershipError:
        logger.error(
            "Rejecting ingest claim job_id=%s tenant_id=%s phase=claim",
            job_id,
            tenant_id,
        )
        raise

    heartbeat = JobLeaseHeartbeat(
        job_id=job_uuid,
        tenant_id=tenant_id,
        lease_token=lease_token,
        interval_sec=heartbeat_interval_sec(),
    )
    heartbeat.start()

    try:
        _best_effort_progress(
            self,
            state="PROCESSING",
            meta={"step": "loading", "job_id": str(job_uuid)},
        )

        if heartbeat.ownership_lost:
            logger.warning(
                "Ingestion lease lost job_id=%s phase=pre_load",
                job_id,
            )
            raise JobOwnershipError(_MSG_LEASE_LOST)

        path = Path(file_path)
        if not path.exists():
            _safe_terminal_failed(
                mark_failed=sync_mark_failed,
                job_uuid=job_uuid,
                tenant_id=tenant_id,
                lease_token=lease_token,
                message=_MSG_FILE_NOT_FOUND,
            )
            raise FileNotFoundError(_MSG_FILE_NOT_FOUND)

        try:
            from ingestion.loader import DocumentLoader

            loader = DocumentLoader(recursive=False)
            docs = loader.load_documents(str(path.parent))
        except Exception as exc:
            # Boundary log: type only — no exc_info (traceback carries raw message).
            logger.error(
                "Loading failed job_id=%s tenant_id=%s phase=loading error_type=%s",
                job_id,
                tenant_id,
                type(exc).__name__,
            )
            _safe_terminal_failed(
                mark_failed=sync_mark_failed,
                job_uuid=job_uuid,
                tenant_id=tenant_id,
                lease_token=lease_token,
                message=_MSG_LOADING_FAILED,
            )
            raise RuntimeError(_MSG_LOADING_FAILED) from exc

        if not docs:
            _safe_terminal_failed(
                mark_failed=sync_mark_failed,
                job_uuid=job_uuid,
                tenant_id=tenant_id,
                lease_token=lease_token,
                message=_MSG_NO_CONTENT,
            )
            raise RuntimeError(_MSG_NO_CONTENT)

        if heartbeat.ownership_lost:
            logger.warning(
                "Ingestion lease lost job_id=%s phase=pre_index",
                job_id,
            )
            raise JobOwnershipError(_MSG_LEASE_LOST)

        _best_effort_progress(
            self,
            state="PROCESSING",
            meta={"step": "indexing", "docs_count": len(docs), "job_id": str(job_uuid)},
        )

        try:
            from config.settings import get_settings
            from vectordb.manager import build_vector_store, get_embeddings

            settings = get_settings()
            chunk_config = {
                "chunk_size": getattr(settings, "chunk_size", 800),
                "chunk_overlap": getattr(settings, "chunk_overlap", 200),
            }
            embeddings = get_embeddings()
            build_vector_store(
                docs,
                chunk_config,
                embeddings=embeddings,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.error(
                "Indexing failed job_id=%s tenant_id=%s phase=indexing error_type=%s",
                job_id,
                tenant_id,
                type(exc).__name__,
            )
            _safe_terminal_failed(
                mark_failed=sync_mark_failed,
                job_uuid=job_uuid,
                tenant_id=tenant_id,
                lease_token=lease_token,
                message=_MSG_INDEXING_FAILED,
            )
            raise RuntimeError(_MSG_INDEXING_FAILED) from exc

        if heartbeat.ownership_lost:
            logger.warning(
                "Ingestion lease lost job_id=%s phase=pre_complete",
                job_id,
            )
            # Do not overwrite reaper terminal state.
            raise JobOwnershipError(_MSG_LEASE_LOST)

        result = {
            "status": "ok",
            "docs_count": len(docs),
            "message": f"Indexed {len(docs)} document(s) from {path.name}",
            "job_id": str(job_uuid),
            "tenant_id": tenant_id,
        }
        try:
            sync_mark_completed(job_uuid, tenant_id, lease_token, result)
        except JobOwnershipError:
            logger.warning(
                "Ingestion lease lost job_id=%s phase=complete",
                job_id,
            )
            raise
        return result
    finally:
        heartbeat.stop()

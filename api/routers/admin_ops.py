"""Admin operational endpoints: circuit breaker, audit log, and traces."""

from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from auth.dependencies import require_role
from db import engine as _db_engine
from monitoring import prometheus as prometheus_metrics

router = APIRouter()


class IndexRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_generation: int = Field(strict=True)
    target_collection: str = Field(strict=True)


class IndexRetentionExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_generation: int = Field(strict=True)
    expected_candidates: tuple[StrictStr, ...]


def _async_session() -> Any:
    return _db_engine.async_session()


async def _log_audit(**kwargs: Any) -> Any:
    return await _app_module().log_audit(**kwargs)


@router.post("/admin/circuit-breaker/reset")
async def admin_reset_circuit_breaker(
    request: Request,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from agent.graph import get_default_breaker

    breaker = get_default_breaker()
    if breaker is None:
        return JSONResponse(
            status_code=409,
            content={
                "status": "disabled",
                "detail": "circuit breaker disabled via CIRCUIT_BREAKER_ENABLED=false",
            },
        )

    previous = breaker.snapshot()
    breaker.reset()
    current = breaker.snapshot()

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="circuit_breaker_reset",
        resource=f"breaker/{breaker.name}",
        tenant_id=tenant,
        detail={
            "tenant": tenant,
            "previous_state": previous["state"],
            "previous_consecutive_failures": previous["consecutive_failures"],
        },
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "reset",
            "breaker": breaker.name,
            "previous": previous,
            "current": current,
        },
    )


@router.get("/admin/audit")
async def admin_list_audit(
    limit: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    limit = (
        getattr(_app_module().get_settings(), "api_default_page_size", 50)
        if limit is None
        else limit
    )
    limit = max(1, min(500, limit))
    tenant = _user.get("tenant") or get_current_tenant() or "default"

    try:
        from sqlalchemy import select  # noqa: PLC0415

        from db.models import AuditLog  # noqa: PLC0415

        async with _async_session() as db:
            stmt = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant)
                .order_by(AuditLog.ts.desc())
                .limit(limit)
            )
            if actor:
                stmt = stmt.where(AuditLog.actor == actor)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            result = await db.execute(stmt)
            rows = result.scalars().all()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"audit_log unavailable: {exc}"},
        )

    return JSONResponse(
        content={
            "entries": [
                {
                    "id": row.id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "actor": row.actor,
                    "action": row.action,
                    "resource": row.resource,
                    "detail": row.detail,
                    "ip_address": row.ip_address,
                }
                for row in rows
            ]
        }
    )


@router.get("/admin/traces")
async def admin_list_traces(
    limit: int | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from tracing.sqlite_trace import list_recent_traces  # noqa: PLC0415

    limit = (
        getattr(_app_module().get_settings(), "api_default_page_size", 50)
        if limit is None
        else limit
    )
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    trace_params = inspect.signature(list_recent_traces).parameters
    if "tenant_id" in trace_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in trace_params.values()
    ):
        traces = await asyncio.to_thread(list_recent_traces, limit, tenant_id=tenant)
    else:
        traces = await asyncio.to_thread(list_recent_traces, limit)
    return JSONResponse(content={"traces": traces})


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(
    trace_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")

    from tracing.sqlite_trace import get_trace_detail  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    detail_params = inspect.signature(get_trace_detail).parameters
    if "tenant_id" in detail_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in detail_params.values()
    ):
        trace = await asyncio.to_thread(get_trace_detail, trace_id, tenant_id=tenant)
    else:
        trace = await asyncio.to_thread(get_trace_detail, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(content=trace)


@router.delete("/admin/traces")
async def admin_purge_traces(
    request: Request,
    older_than_days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    from tracing.sqlite_trace import purge_old_traces

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    purge_params = inspect.signature(purge_old_traces).parameters
    if "tenant_id" in purge_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in purge_params.values()
    ):
        result = await asyncio.to_thread(
            purge_old_traces,
            older_than_days,
            tenant_id=tenant,
        )
    else:
        result = await asyncio.to_thread(purge_old_traces, older_than_days)

    for table, count in (
        ("traces", result["traces_deleted"]),
        ("trace_steps", result["steps_deleted"]),
        ("feedback", result["feedback_deleted"]),
    ):
        prometheus_metrics.record_traces_purged(table, count)

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="trace_purge",
        resource=f"traces/older_than={older_than_days}d",
        tenant_id=tenant,
        detail=(result if tenant == "default" else {**result, "tenant": tenant}),
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content=result)


@router.delete("/admin/audit-log")
async def admin_purge_audit(
    request: Request,
    older_than_days: int = 90,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    from db.audit import purge_old_audit

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    audit_params = inspect.signature(purge_old_audit).parameters
    if "tenant_id" in audit_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in audit_params.values()
    ):
        deleted = await purge_old_audit(older_than_days, tenant_id=tenant)
    else:
        deleted = await purge_old_audit(older_than_days)
    try:
        prometheus_metrics.record_audit_purged(deleted)
    except Exception:
        pass

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="audit_purge",
        resource=f"audit_log/older_than={older_than_days}d",
        tenant_id=tenant,
        detail={
            "deleted": deleted,
            "tenant": tenant,
        },
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content={"deleted": deleted})


async def _audit_index_retention_preview(
    *,
    request: Request,
    user: dict[str, Any],
    tenant_id: str,
    detail: dict[str, Any],
) -> None:
    await _log_audit(
        actor=user.get("sub", "anonymous"),
        action="index_retention_preview",
        resource="index/retention-preview",
        tenant_id=tenant_id,
        detail=detail,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/admin/index/retention-preview")
async def admin_index_retention_preview(
    request: Request,
    max_versions: int | None = None,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Read-only bounded retention preview for the authenticated tenant."""
    from vectordb.index_manifest import IndexManifestCorrupt  # noqa: PLC0415
    from vectordb.index_operator import preview_index_retention  # noqa: PLC0415
    from vectordb.index_retention import (  # noqa: PLC0415
        IndexRetentionCorrupt,
        IndexRetentionValidationError,
    )
    from vectordb.tenant_lock import TenantIndexLockError  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    settings = _app_module().get_settings()
    resolved_max_versions = (
        settings.vectordb_retention_max_versions if max_versions is None else max_versions
    )
    chroma_directory = settings.vectordb_chroma_dir

    try:
        preview = await asyncio.to_thread(
            preview_index_retention,
            tenant,
            max_versions=resolved_max_versions,
            chroma_directory=chroma_directory,
        )
    except IndexRetentionValidationError as exc:
        await _audit_index_retention_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "rejected",
                "max_versions": resolved_max_versions,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="invalid retention preview budget",
        ) from None
    except (IndexRetentionCorrupt, IndexManifestCorrupt) as exc:
        await _audit_index_retention_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "metadata_corrupt",
                "max_versions": resolved_max_versions,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index retention metadata is corrupt",
        ) from None
    except TenantIndexLockError as exc:
        await _audit_index_retention_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "lock_unavailable",
                "max_versions": resolved_max_versions,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="index retention preview is temporarily unavailable",
        ) from None

    await _audit_index_retention_preview(
        request=request,
        user=_user,
        tenant_id=tenant,
        detail={
            "tenant": tenant,
            "outcome": "success",
            "max_versions": preview.max_versions,
            "manifest_generation": preview.manifest_generation,
            "active_collection": preview.active_collection,
            "previous_collection": preview.previous_collection,
            "inventory_count": len(preview.inventory_collections),
            "deletion_candidates": list(preview.deletion_candidates),
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "tenant_id": preview.tenant_id,
            "max_versions": preview.max_versions,
            "manifest_generation": preview.manifest_generation,
            "active_collection": preview.active_collection,
            "previous_collection": preview.previous_collection,
            "inventory_collections": list(preview.inventory_collections),
            "deletion_candidates": list(preview.deletion_candidates),
        },
    )


async def _audit_job_object_inventory_preview(
    *,
    request: Request,
    user: dict[str, Any],
    tenant_id: str,
    detail: dict[str, Any],
) -> None:
    await _log_audit(
        actor=user.get("sub", "anonymous"),
        action="job_object_inventory_preview",
        resource="job-objects/inventory",
        tenant_id=tenant_id,
        detail=detail,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/admin/job-objects/inventory")
async def admin_job_object_inventory_preview(
    request: Request,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Read-only job-object inventory + transition annotations for JWT tenant.

    Plan 2.5a: operator surface only. Never executes retention or mutates
    filesystem state. Tenant always comes from the authenticated principal;
    foreign tenant query params are ignored by design (not accepted).
    """
    from pathlib import Path  # noqa: PLC0415

    from ingestion.job_object_inventory import (  # noqa: PLC0415
        JobObjectInventoryValidationError,
    )
    from ingestion.job_object_operator import (  # noqa: PLC0415
        load_and_run_operator_preview,
        report_to_jsonable,
    )
    from ingestion.job_object_orphans import (  # noqa: PLC0415
        JobObjectOrphanValidationError,
    )
    from ingestion.job_object_retention import (  # noqa: PLC0415
        JobObjectRetentionError,
    )

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    app = _app_module()
    project_root = Path(getattr(app, "PROJECT_ROOT", None) or Path.cwd())
    upload_root = project_root / "data" / "uploads"

    try:
        report = await asyncio.to_thread(
            load_and_run_operator_preview,
            tenant_id=tenant,
            project_root=project_root,
            upload_root=upload_root,
            execute=False,
        )
    except ValueError as exc:
        await _audit_job_object_inventory_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "rejected",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="invalid job-object inventory request",
        ) from None
    except (
        JobObjectInventoryValidationError,
        JobObjectRetentionError,
        JobObjectOrphanValidationError,
    ) as exc:
        await _audit_job_object_inventory_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "rejected",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="invalid job-object inventory preview",
        ) from None
    except OSError as exc:
        await _audit_job_object_inventory_preview(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "unavailable",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="job-object inventory preview is temporarily unavailable",
        ) from None

    payload = report_to_jsonable(report)
    # Admin surface is read-only: never expose an execute/no-op block.
    payload.pop("execution", None)

    await _audit_job_object_inventory_preview(
        request=request,
        user=_user,
        tenant_id=tenant,
        detail={
            "tenant": tenant,
            "outcome": "success",
            "known_job_count": report.known_job_count,
            "inventory_count": len(report.inventory_entries),
            "auto_delete_candidates": list(report.assessment.auto_delete_candidates),
            "annotation_count": len(report.transition_annotations),
        },
    )
    return JSONResponse(status_code=200, content=payload)


async def _audit_index_rollback(
    *,
    request: Request,
    user: dict[str, Any],
    tenant_id: str,
    detail: dict[str, Any],
) -> None:
    await _log_audit(
        actor=user.get("sub", "anonymous"),
        action="index_rollback",
        resource="index/rollback",
        tenant_id=tenant_id,
        detail=detail,
        ip_address=request.client.host if request.client else None,
    )


@router.post("/admin/index/rollback")
async def admin_index_rollback(
    request: Request,
    payload: IndexRollbackRequest,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Apply idempotent validated runtime index rollback for the tenant."""
    from vectordb.index_manifest import (  # noqa: PLC0415
        IndexManifestCorrupt,
        IndexManifestRollbackUnavailable,
    )
    from vectordb.index_operator import (  # noqa: PLC0415
        IndexRollbackConflict,
        IndexRollbackValidationError,
    )
    from vectordb.index_staging import IndexStagingValidationError  # noqa: PLC0415
    from vectordb.manager import rollback_vector_store  # noqa: PLC0415
    from vectordb.tenant_lock import TenantIndexLockError  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"

    try:
        await asyncio.to_thread(
            rollback_vector_store,
            tenant,
            expected_generation=payload.expected_generation,
            target_collection=payload.target_collection,
        )
    except IndexRollbackValidationError as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "rejected",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="invalid index rollback command",
        ) from None
    except IndexRollbackConflict as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "conflict",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index rollback conflicts with current state",
        ) from None
    except IndexManifestRollbackUnavailable as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "unavailable",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index rollback is unavailable",
        ) from None
    except IndexManifestCorrupt as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "metadata_corrupt",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index manifest is corrupt",
        ) from None
    except IndexStagingValidationError as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "target_invalid",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index rollback target validation failed",
        ) from None
    except TenantIndexLockError as exc:
        await _audit_index_rollback(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "lock_unavailable",
                "expected_generation": payload.expected_generation,
                "target_collection": payload.target_collection,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="index rollback is temporarily unavailable",
        ) from None

    await _audit_index_rollback(
        request=request,
        user=_user,
        tenant_id=tenant,
        detail={
            "tenant": tenant,
            "outcome": "success",
            "expected_generation": payload.expected_generation,
            "target_collection": payload.target_collection,
            "manifest_generation": payload.expected_generation + 1,
            "active_collection": payload.target_collection,
            "status": "active",
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "active",
            "tenant_id": tenant,
            "expected_generation": payload.expected_generation,
            "target_collection": payload.target_collection,
            "manifest_generation": payload.expected_generation + 1,
            "active_collection": payload.target_collection,
        },
    )


async def _audit_index_retention(
    *,
    request: Request,
    user: dict[str, Any],
    tenant_id: str,
    detail: dict[str, Any],
) -> None:
    await _log_audit(
        actor=user.get("sub", "anonymous"),
        action="index_retention",
        resource="index/retention",
        tenant_id=tenant_id,
        detail=detail,
        ip_address=request.client.host if request.client else None,
    )


@router.post("/admin/index/retention")
async def admin_index_retention(
    request: Request,
    payload: IndexRetentionExecutionRequest,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Apply guarded idempotent retention execution for the tenant."""
    from vectordb.index_manifest import IndexManifestCorrupt  # noqa: PLC0415
    from vectordb.index_operator import (  # noqa: PLC0415
        IndexRetentionExecutionConflict,
        IndexRetentionExecutionValidationError,
    )
    from vectordb.index_retention import (  # noqa: PLC0415
        IndexRetentionCorrupt,
        IndexRetentionDeletionError,
        IndexRetentionMetadataUpdateError,
        IndexRetentionValidationError,
    )
    from vectordb.index_staging import IndexStagingValidationError  # noqa: PLC0415
    from vectordb.manager import execute_vector_store_retention  # noqa: PLC0415
    from vectordb.tenant_lock import TenantIndexLockError  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    expected_candidates = payload.expected_candidates
    expected_candidates_list = list(expected_candidates)

    try:
        result = await asyncio.to_thread(
            execute_vector_store_retention,
            tenant,
            expected_generation=payload.expected_generation,
            expected_candidates=expected_candidates,
        )
    except (
        IndexRetentionExecutionValidationError,
        IndexRetentionValidationError,
    ) as exc:
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "rejected",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="invalid index retention command",
        ) from None
    except IndexRetentionExecutionConflict as exc:
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "conflict",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index retention conflicts with current state",
        ) from None
    except (IndexRetentionCorrupt, IndexManifestCorrupt) as exc:
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "metadata_corrupt",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index retention metadata is corrupt",
        ) from None
    except IndexStagingValidationError as exc:
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "unavailable",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=409,
            detail="index retention is unavailable",
        ) from None
    except TenantIndexLockError as exc:
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "lock_unavailable",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="index retention is temporarily unavailable",
        ) from None
    except IndexRetentionDeletionError as exc:
        deleted_collections = list(exc.deleted_collections)
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "deletion_failed",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
                "failed_collection": exc.failed_collection,
                "deleted_collections": deleted_collections,
            },
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "index retention deletion failed",
                "failed_collection": exc.failed_collection,
                "deleted_collections": deleted_collections,
            },
        )
    except IndexRetentionMetadataUpdateError as exc:
        deleted_collections = list(exc.deleted_collections)
        await _audit_index_retention(
            request=request,
            user=_user,
            tenant_id=tenant,
            detail={
                "tenant": tenant,
                "outcome": "metadata_update_failed",
                "expected_generation": payload.expected_generation,
                "expected_candidates": expected_candidates_list,
                "error_type": type(exc).__name__,
                "deleted_collection": exc.deleted_collection,
                "deleted_collections": deleted_collections,
            },
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "index retention metadata update failed",
                "deleted_collection": exc.deleted_collection,
                "deleted_collections": deleted_collections,
            },
        )

    await _audit_index_retention(
        request=request,
        user=_user,
        tenant_id=tenant,
        detail={
            "tenant": tenant,
            "outcome": "success",
            "expected_generation": result.expected_generation,
            "expected_candidates": list(result.expected_candidates),
            "max_versions": result.max_versions,
            "deleted_collections": list(result.deleted_collections),
            "deleted_count": len(result.deleted_collections),
            "status": "complete",
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "complete",
            "tenant_id": result.tenant_id,
            "max_versions": result.max_versions,
            "expected_generation": result.expected_generation,
            "expected_candidates": list(result.expected_candidates),
            "deleted_collections": list(result.deleted_collections),
        },
    )

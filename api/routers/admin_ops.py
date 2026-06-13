"""Admin operational endpoints: circuit breaker, audit log, and traces."""
from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from auth.dependencies import require_role
from db import engine as _db_engine
from monitoring import prometheus as prometheus_metrics

router = APIRouter()


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

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="circuit_breaker_reset",
        resource=f"breaker/{breaker.name}",
        detail={
            "tenant": _user.get("tenant", "default"),
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
    limit = getattr(_app_module().get_settings(), "api_default_page_size", 50) if limit is None else limit
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

    limit = getattr(_app_module().get_settings(), "api_default_page_size", 50) if limit is None else limit
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
        detail=(
            result
            if _user.get("tenant", "default") == "default"
            else {**result, "tenant": _user.get("tenant", "default")}
        ),
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
        detail={
            "deleted": deleted,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content={"deleted": deleted})

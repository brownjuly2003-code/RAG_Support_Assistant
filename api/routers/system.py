"""System endpoints: liveness probe + Prometheus-style metrics snapshot.

Extracted from api.app on 2026-04-26 as the first proof-of-concept split.
These two endpoints are dependency-light (no module-global state from
api.app), which makes them safe candidates for the initial extraction.

The remaining health endpoints (/health, /health/ready) require module-globals
(_shutting_down, _vector_store, _sessions, _run_qa_pipeline, the _probe_*
helpers) and are kept in api.app until those globals are factored out into
api._shared. See DEPRECATIONS.md for the full plan.
"""
from __future__ import annotations

import inspect
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.correlation import get_current_tenant
from auth.dependencies import require_role

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health/live")
async def health_liveness() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"status": "alive", "service": "rag-support-assistant"},
    )


@router.get("/metrics")
async def get_metrics(
    _user: dict = Depends(require_role("admin")),
) -> dict:
    """Aggregated JSON snapshot of system health metrics."""
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        from sqlite_trace import get_metrics_snapshot  # noqa: PLC0415

        metrics_params = inspect.signature(get_metrics_snapshot).parameters
        if "tenant_id" in metrics_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in metrics_params.values()
        ):
            return get_metrics_snapshot(tenant_id=tenant)
        return get_metrics_snapshot()
    except Exception as exc:
        logger.warning("Failed to get metrics: %s", exc)
        return {"error": str(exc), "generated_at": ""}

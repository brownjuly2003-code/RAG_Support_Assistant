"""Root-level HTML, redirect, and Prometheus endpoints."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from auth.dependencies import require_role

router = APIRouter()


def _app_module():
    from api import app as _app  # noqa: PLC0415

    return _app


@router.get("/agent", response_class=HTMLResponse)
async def agent_dashboard(
    _user: dict = Depends(require_role("agent", "admin")),
) -> HTMLResponse:
    agent_path = _app_module().PROJECT_ROOT / "static" / "agent.html"
    if not agent_path.exists():
        raise HTTPException(status_code=404, detail="agent dashboard not found")
    return HTMLResponse(agent_path.read_text(encoding="utf-8"))


@router.get("/admin/traces/{trace_id}")
async def admin_trace_detail_redirect(trace_id: str) -> RedirectResponse:
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")
    return RedirectResponse(url=f"/traces-ui/{trace_id}", status_code=307)


@router.get("/metrics")
async def prometheus_metrics_endpoint(request: Request) -> Response:
    """Prometheus pull endpoint.

    The /metrics path is intentionally unauthenticated by Prometheus
    convention; most scrape configs do not support per-target auth.
    Production deployments MUST restrict access at network level (Service
    network policy, ingress whitelist, sidecar). The authenticated
    alternative is `/api/metrics`, which returns the same JSON snapshot.

    Optional opt-in: set PROMETHEUS_METRICS_REQUIRE_AUTH=1 to require an
    `Authorization: Bearer <admin-token>` header even on /metrics. This is
    useful when the cluster does not provide a private scrape network.

    Refs: Codex audit 2026-04-27 P1 section 4.
    """
    if os.getenv("PROMETHEUS_METRICS_REQUIRE_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        try:
            require_role("admin")(request)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Unauthorized")

    _app = _app_module()
    if not getattr(_app.prometheus_metrics, "PROMETHEUS_AVAILABLE", False):
        return JSONResponse(
            status_code=501,
            content={"detail": "prometheus-client is not installed"},
        )

    _app.prometheus_metrics.ACTIVE_SESSIONS.set(len(_app._sessions))
    return Response(
        content=_app.prometheus_metrics.generate_latest(_app.prometheus_metrics.REGISTRY),
        media_type=_app.prometheus_metrics.CONTENT_TYPE_LATEST,
    )

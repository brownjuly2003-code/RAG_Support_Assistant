"""System endpoints: liveness/readiness probes + metrics snapshot.

Extracted from api.app on 2026-04-26 as the first proof-of-concept split.
The dependency-aware health endpoints use late-bound api.app access so tests
that monkeypatch module globals keep working after the split.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from auth.dependencies import require_role
from config.provider_schema import load_provider_registry

logger = logging.getLogger(__name__)

router = APIRouter()


class ComponentStatus(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    components: dict[str, ComponentStatus]
    vector_store_loaded: bool
    sessions_count: int
    pipeline_available: bool
    circuit_breakers: list[dict[str, Any]] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)


def _shutdown_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "status": "shutting_down",
            "detail": "process is draining - stop sending traffic",
        },
    )


@router.get("/health/live")
async def health_liveness() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"status": "alive", "service": "rag-support-assistant"},
    )


@router.get("/health/ready", response_model=HealthResponse)
async def health_readiness() -> JSONResponse:
    if _app_module()._shutting_down:
        return _shutdown_response()
    return await health_check()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> JSONResponse:
    _app = _app_module()
    if _app._shutting_down:
        return _shutdown_response()
    settings = _app.get_settings()

    provider_statuses: dict[str, ComponentStatus] = {}
    active_provider_ids: set[str] = set()
    provider_registry_status: ComponentStatus | None = None
    try:
        provider_registry = load_provider_registry(getattr(settings, "provider_registry_path", None))
        profile_name = str(
            getattr(settings, "llm_provider_profile", provider_registry.default_profile)
            or provider_registry.default_profile
        )
        active_profile = provider_registry.get_profile(profile_name)
        active_provider_ids = {active_profile.fast.provider, active_profile.strong.provider}
    except Exception as exc:
        provider_registry_status = ComponentStatus(status="error", detail=str(exc))

    provider_probe_names: list[str] = []
    provider_probe_calls: list[Any] = []
    if "ollama" in active_provider_ids:
        provider_probe_names.append("ollama")
        provider_probe_calls.append(_app._probe_ollama(settings.ollama_base_url))
    if "gracekelly" in active_provider_ids:
        provider_probe_names.append("gracekelly")
        provider_probe_calls.append(
            _app._probe_gracekelly(
                str(getattr(settings, "gracekelly_base_url", "http://127.0.0.1:8011")),
                float(getattr(settings, "gracekelly_health_check_timeout_sec", 2.0)),
            )
        )
    if provider_probe_calls:
        provider_statuses.update(
            zip(provider_probe_names, await asyncio.gather(*provider_probe_calls))
        )

    chroma_status, sqlite_status, postgres_status, redis_status = await asyncio.gather(
        _app._probe_chromadb(settings.vectordb_chroma_dir),
        _app._probe_sqlite(settings.tracing_db_path),
        _app._probe_postgres(),
        _app._probe_redis(),
    )
    try:
        for provider_name, provider_status in provider_statuses.items():
            _app.prometheus_metrics.record_component_health(provider_name, provider_status.status)
        if provider_registry_status is not None:
            _app.prometheus_metrics.record_component_health("provider_registry", provider_registry_status.status)
        _app.prometheus_metrics.record_component_health("chromadb", chroma_status.status)
        _app.prometheus_metrics.record_component_health("sqlite", sqlite_status.status)
        _app.prometheus_metrics.record_component_health("postgres", postgres_status.status)
        _app.prometheus_metrics.record_component_health("redis", redis_status.status)
    except Exception:
        pass

    critical_down = (
        chroma_status.status == "error"
        or any(status.status == "error" for status in provider_statuses.values())
        or (provider_registry_status is not None and provider_registry_status.status == "error")
    )
    non_critical_error = (
        sqlite_status.status == "error"
        or postgres_status.status == "error"
        or redis_status.status == "error"
    )
    overall = "unhealthy" if critical_down else ("degraded" if non_critical_error else "ok")
    breakers_snap: list[dict[str, Any]] = []
    try:
        from agent.graph import get_default_breaker
    except ImportError:
        get_default_breaker = None  # type: ignore[assignment]

    if get_default_breaker is not None:
        breaker = get_default_breaker()
        if breaker is not None:
            breakers_snap.append(breaker.snapshot())

    components = {
        **provider_statuses,
        "chromadb": chroma_status,
        "sqlite": sqlite_status,
        "postgres": postgres_status,
        "redis": redis_status,
    }
    if provider_registry_status is not None:
        components["provider_registry"] = provider_registry_status

    response = HealthResponse(
        status=overall,
        components=components,
        vector_store_loaded=_app._vector_store is not None,
        sessions_count=len(_app._sessions),
        pipeline_available=_app._run_qa_pipeline is not None,
        circuit_breakers=breakers_snap,
        features={
            "streaming_enabled": bool(getattr(settings, "streaming_enabled", False)),
        },
    )

    status_code = 503 if critical_down else 200
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@router.get("/metrics")
async def get_metrics(
    _user: dict = Depends(require_role("admin")),
) -> dict:
    """Aggregated JSON snapshot of system health metrics."""
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        from tracing.sqlite_trace import get_metrics_snapshot  # noqa: PLC0415

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

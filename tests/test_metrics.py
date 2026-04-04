from __future__ import annotations

import importlib
import inspect
import sys
import time
import types
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _install_slowapi_stub() -> None:
    if "slowapi" in sys.modules:
        return

    class RateLimitExceeded(Exception):
        pass

    class _MemoryStorage:
        def __init__(self) -> None:
            self._hits: dict[tuple[str, str, int], int] = {}

        def reset(self) -> None:
            self._hits.clear()

    class Limiter:
        def __init__(self, key_func):
            self.key_func = key_func
            self._storage = _MemoryStorage()

        def limit(self, value: str):
            limit_value, period = value.split("/", maxsplit=1)
            max_requests = int(limit_value)
            window_seconds = 60 if period.startswith("minute") else 1

            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    request = kwargs.get("request")
                    if request is None:
                        for arg in args:
                            if hasattr(arg, "client") and hasattr(arg, "url"):
                                request = arg
                                break

                    key = self.key_func(request) if request is not None else "global"
                    bucket = int(time.time() // window_seconds)
                    storage_key = (func.__name__, key, bucket)
                    hits = self._storage._hits.get(storage_key, 0) + 1
                    self._storage._hits[storage_key] = hits
                    if hits > max_requests:
                        raise RateLimitExceeded("Rate limit exceeded")
                    return await func(*args, **kwargs)

                wrapper.__signature__ = inspect.signature(func)
                return wrapper

            return decorator

    def _rate_limit_exceeded_handler(request, exc):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    def get_remote_address(request) -> str:
        if request is None or request.client is None:
            return "testclient"
        return request.client.host

    slowapi_module = types.ModuleType("slowapi")
    slowapi_module.Limiter = Limiter
    slowapi_module._rate_limit_exceeded_handler = _rate_limit_exceeded_handler

    errors_module = types.ModuleType("slowapi.errors")
    errors_module.RateLimitExceeded = RateLimitExceeded

    util_module = types.ModuleType("slowapi.util")
    util_module.get_remote_address = get_remote_address

    sys.modules["slowapi"] = slowapi_module
    sys.modules["slowapi.errors"] = errors_module
    sys.modules["slowapi.util"] = util_module


def _install_sqlite_trace_stub() -> None:
    module = sys.modules.get("sqlite_trace")
    if module is None:
        module = types.ModuleType("sqlite_trace")
        sys.modules["sqlite_trace"] = module

    module.start_trace = getattr(module, "start_trace", lambda: "trace-stub")
    module.log_step = getattr(module, "log_step", lambda *args, **kwargs: None)
    module.finish_trace = getattr(module, "finish_trace", lambda *args, **kwargs: None)
    module.get_metrics_snapshot = getattr(module, "get_metrics_snapshot", lambda: {})


_install_slowapi_stub()
_install_sqlite_trace_stub()
api_app = importlib.import_module("api.app")


MOCK_SNAPSHOT = {
    "latency": {"p50_sec": 1.5, "p95_sec": 8.2, "p99_sec": 14.0, "window": "24h"},
    "escalation": {"total_traces": 100, "escalated": 15, "rate_pct": 15.0, "window": "24h"},
    "quality": {"scored_traces": 90, "avg_quality": 78.5, "low_quality_share_pct": 10.0, "window": "7d"},
    "errors": {"total_started": 100, "likely_failed": 2, "likely_failure_rate_pct": 2.0, "window": "24h"},
    "feedback": {"total": 60, "thumbs_down": 8, "thumbs_down_rate_pct": 13.3, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}

EMPTY_SNAPSHOT = {
    "latency": {"p50_sec": None, "p95_sec": None, "p99_sec": None, "window": "24h"},
    "escalation": {"total_traces": 0, "escalated": 0, "rate_pct": None, "window": "24h"},
    "quality": {"scored_traces": 0, "avg_quality": None, "low_quality_share_pct": None, "window": "7d"},
    "errors": {"total_started": 0, "likely_failed": 0, "likely_failure_rate_pct": None, "window": "24h"},
    "feedback": {"total": 0, "thumbs_down": 0, "thumbs_down_rate_pct": None, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = SimpleNamespace(
        ensure_dirs=lambda: None,
        validate=lambda: None,
        ollama_base_url="http://ollama.test",
        vectordb_chroma_dir=Path("data/vectordb/chroma"),
        tracing_db_path=Path("data/tracing/traces.db"),
        api_key="",
    )

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "initialize_vector_store", lambda: None)
    api_app._sessions.clear()
    api_app._session_last_access.clear()
    api_app._vector_store = None

    limiter_storage = getattr(api_app.app.state.limiter, "_storage", None)
    if limiter_storage is not None and hasattr(limiter_storage, "reset"):
        limiter_storage.reset()

    with TestClient(api_app.app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_metrics_returns_200(client: TestClient) -> None:
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    assert response.status_code == 200


def test_metrics_has_required_keys(client: TestClient) -> None:
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    data = response.json()
    for key in ("latency", "escalation", "quality", "errors", "feedback", "generated_at"):
        assert key in data


def test_metrics_latency_fields(client: TestClient) -> None:
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    latency = response.json()["latency"]
    assert latency["p50_sec"] == 1.5
    assert latency["p95_sec"] == 8.2
    assert latency["window"] == "24h"


def test_metrics_empty_snapshot_returns_200(client: TestClient) -> None:
    with patch("sqlite_trace.get_metrics_snapshot", return_value=EMPTY_SNAPSHOT):
        response = client.get("/api/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["latency"]["p50_sec"] is None
    assert data["escalation"]["total_traces"] == 0


def test_metrics_error_fallback(client: TestClient) -> None:
    with patch("sqlite_trace.get_metrics_snapshot", side_effect=RuntimeError("db locked")):
        response = client.get("/api/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "db locked"
    assert data["generated_at"] == ""

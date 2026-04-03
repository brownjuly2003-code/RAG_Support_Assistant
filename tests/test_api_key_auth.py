import importlib
import inspect
import sys
import time
import types
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

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
    if "sqlite_trace" in sys.modules:
        return

    sqlite_trace_module = types.ModuleType("sqlite_trace")
    sqlite_trace_module.start_trace = lambda: "trace-stub"
    sqlite_trace_module.log_step = lambda *args, **kwargs: None
    sqlite_trace_module.finish_trace = lambda *args, **kwargs: None
    sys.modules["sqlite_trace"] = sqlite_trace_module


_install_slowapi_stub()
_install_sqlite_trace_stub()
api_app = importlib.import_module("api.app")


@pytest.fixture
def client_with_key(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("API_KEY", "secret123")

    settings = SimpleNamespace(
        ensure_dirs=lambda: None,
        validate=lambda: None,
        ollama_base_url="http://ollama.test",
        vectordb_chroma_dir=Path("data/vectordb/chroma"),
        tracing_db_path=Path("data/tracing/traces.db"),
        api_key="secret123",
    )

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "initialize_vector_store", lambda: None)
    api_app._sessions.clear()
    api_app._vector_store = None

    limiter_storage = getattr(api_app.app.state.limiter, "_storage", None)
    if limiter_storage is not None and hasattr(limiter_storage, "reset"):
        limiter_storage.reset()

    with TestClient(api_app.app) as test_client:
        yield test_client


def test_ask_without_key_returns_401(client_with_key: TestClient) -> None:
    resp = client_with_key.post("/api/ask", json={"question": "test"})
    assert resp.status_code == 401


def test_ask_with_wrong_key_returns_403(client_with_key: TestClient) -> None:
    resp = client_with_key.post(
        "/api/ask",
        json={"question": "test"},
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 403


def test_ask_with_correct_key_passes_auth(client_with_key: TestClient) -> None:
    resp = client_with_key.post(
        "/api/ask",
        json={"question": "test"},
        headers={"X-API-Key": "secret123"},
    )
    assert resp.status_code not in (401, 403)

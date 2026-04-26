"""Shared test fixtures for RAG Support Assistant."""
from __future__ import annotations

import importlib
import inspect
import sys
import types
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

_TMP_PATH_SENTINEL = "__tmp_path__"


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
                    storage_key = (func.__name__, key, window_seconds)
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

    module.start_trace = getattr(module, "start_trace", lambda *args, **kwargs: kwargs.get("trace_id") or "trace-stub")
    module.log_step = getattr(module, "log_step", lambda *args, **kwargs: None)
    module.finish_trace = getattr(module, "finish_trace", lambda *args, **kwargs: None)
    module.get_metrics_snapshot = getattr(module, "get_metrics_snapshot", lambda: {})
    module.save_feedback = getattr(module, "save_feedback", lambda *args, **kwargs: None)


def _resolve_tmp_path(value: object, tmp_path: Path) -> object:
    if value == _TMP_PATH_SENTINEL:
        return tmp_path
    return value


def _build_test_client(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
    prefix: str,
    default_api_key: str,
) -> TestClient:
    settings_overrides = {
        key: _resolve_tmp_path(value, tmp_path)
        for key, value in getattr(request.module, f"{prefix}_SETTINGS_OVERRIDES", {}).items()
    }
    patches = {
        key: _resolve_tmp_path(value, tmp_path)
        for key, value in getattr(request.module, f"{prefix}_PATCHES", {}).items()
    }

    settings_overrides.setdefault("api_key", default_api_key)
    settings = settings_factory(**settings_overrides)

    for env_name in getattr(request.module, f"{prefix}_DELETE_ENV", ()):
        monkeypatch.delenv(env_name, raising=False)

    if settings.api_key:
        monkeypatch.setenv("API_KEY", settings.api_key)
        monkeypatch.delenv("ALLOW_ANONYMOUS_ADMIN", raising=False)
    else:
        monkeypatch.delenv("API_KEY", raising=False)
        # Tests using the no-key client fixture rely on the anonymous-admin
        # fallback. In production this fallback is gated by an explicit env;
        # we opt in here to preserve test semantics.
        monkeypatch.setenv("ALLOW_ANONYMOUS_ADMIN", "1")

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "initialize_vector_store", lambda: None)

    for attr_name, value in patches.items():
        monkeypatch.setattr(api_app, attr_name, value)

    return TestClient(
        api_app.app,
        raise_server_exceptions=getattr(request.module, f"{prefix}_RAISE_SERVER_EXCEPTIONS", True),
    )


def _clear_api_state() -> None:
    api_app._sessions.clear()
    api_app._session_last_access.clear()
    api_app._vector_store = None
    api_app._chunks = []
    api_app._retriever = None
    api_app._llm = None
    api_app._db_retry_after = 0.0
    api_app._pipeline_semaphore = None
    api_app.app.state.settings = None

    limiter_storage = getattr(api_app.app.state.limiter, "_storage", None)
    if limiter_storage is not None and hasattr(limiter_storage, "reset"):
        limiter_storage.reset()
    elif limiter_storage is not None and hasattr(limiter_storage, "storage"):
        limiter_storage.storage.clear()
    elif limiter_storage is not None and hasattr(limiter_storage, "_storage"):
        limiter_storage._storage.clear()


_install_slowapi_stub()
_install_sqlite_trace_stub()
api_app = importlib.import_module("api.app")


@pytest.fixture(autouse=True)
def _reset_settings():
    import config.settings as settings_module

    settings_module._settings = None
    api_app._pipeline_semaphore = None
    yield
    settings_module._settings = None
    api_app._pipeline_semaphore = None


@pytest.fixture(autouse=True)
def _reset_api_state():
    _clear_api_state()
    yield
    _clear_api_state()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter_storage = getattr(api_app.app.state.limiter, "_storage", None)
    if limiter_storage is not None and hasattr(limiter_storage, "reset"):
        limiter_storage.reset()
    elif limiter_storage is not None and hasattr(limiter_storage, "storage"):
        limiter_storage.storage.clear()
    elif limiter_storage is not None and hasattr(limiter_storage, "_storage"):
        limiter_storage._storage.clear()
    yield


@pytest.fixture
def settings_factory(tmp_path: Path):
    def _make_settings(**overrides):
        project_root = overrides.pop("project_root", tmp_path)
        data_dir = overrides.pop("data_dir", project_root / "data")

        settings = SimpleNamespace(
            ensure_dirs=lambda: None,
            validate=lambda: None,
            project_root=project_root,
            data_dir=data_dir,
            vectordb_chroma_dir=overrides.pop("vectordb_chroma_dir", data_dir / "vectordb" / "chroma"),
            tracing_db_path=overrides.pop("tracing_db_path", data_dir / "tracing" / "traces.db"),
            inbox_file=overrides.pop("inbox_file", data_dir / "inbox" / "support_inbox.jsonl"),
            chunking_config_path=overrides.pop(
                "chunking_config_path",
                data_dir / "chunking" / "best_chunk_config.json",
            ),
            ollama_base_url=overrides.pop("ollama_base_url", "http://ollama.test"),
            ollama_model_name=overrides.pop("ollama_model_name", "test-model"),
            session_ttl_seconds=overrides.pop("session_ttl_seconds", 7200),
            api_key=overrides.pop("api_key", ""),
            require_ollama=overrides.pop("require_ollama", False),
            cors_origins=overrides.pop("cors_origins", ["*"]),
        )

        for key, value in overrides.items():
            setattr(settings, key, value)

        return settings

    return _make_settings


@pytest.fixture
def client(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
):
    with _build_test_client(request, monkeypatch, settings_factory, tmp_path, "CLIENT", "") as test_client:
        yield test_client


@pytest.fixture
def client_with_key(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
):
    with _build_test_client(
        request,
        monkeypatch,
        settings_factory,
        tmp_path,
        "CLIENT_WITH_KEY",
        "secret123",
    ) as test_client:
        yield test_client


@pytest.fixture
def mock_pipeline(monkeypatch: pytest.MonkeyPatch):
    mock_result = {
        "answer": "Тестовый ответ",
        "quality_score": 75,
        "route": "auto",
        "sources": [],
        "trace_id": "test-trace-id",
    }
    mock_fn = MagicMock(return_value=mock_result)
    monkeypatch.setattr(api_app, "_run_qa_pipeline", mock_fn, raising=False)
    return mock_fn


@pytest.fixture
def temp_upload_dir(tmp_path: Path) -> Path:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return upload_dir

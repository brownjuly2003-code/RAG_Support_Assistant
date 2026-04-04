import importlib
import inspect
import sys
import time
import types
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    module.save_feedback = getattr(module, "save_feedback", lambda *args, **kwargs: None)


_install_slowapi_stub()
_install_sqlite_trace_stub()
api_app = importlib.import_module("api.app")


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
    api_app._retriever = None
    api_app._llm = None

    limiter_storage = getattr(api_app.app.state.limiter, "_storage", None)
    if limiter_storage is not None and hasattr(limiter_storage, "reset"):
        limiter_storage.reset()

    with TestClient(api_app.app) as test_client:
        yield test_client


def test_feedback_up(client: TestClient) -> None:
    resp = client.post(
        "/api/feedback",
        json={
            "trace_id": "test-trace-001",
            "session_id": "test-session-001",
            "rating": "up",
        },
    )
    assert resp.status_code == 204


def test_feedback_invalid_rating(client: TestClient) -> None:
    resp = client.post(
        "/api/feedback",
        json={
            "trace_id": "test-trace-001",
            "session_id": "test-session-001",
            "rating": "meh",
        },
    )
    assert resp.status_code == 422


def test_feedback_down(client: TestClient) -> None:
    resp = client.post(
        "/api/feedback",
        json={
            "trace_id": "t2",
            "session_id": "s2",
            "rating": "down",
            "reason": "wrong answer",
        },
    )
    assert resp.status_code == 204


def test_sessions_list_empty(client: TestClient) -> None:
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sessions_list_after_ask(client: TestClient) -> None:
    ask_resp = client.post("/api/ask", json={"question": "test question"})

    assert ask_resp.status_code == 200
    session_id = ask_resp.json()["session_id"]

    sessions_resp = client.get("/api/sessions")

    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()
    assert any(item["session_id"] == session_id for item in sessions)


def test_ask_stream_content_type(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSession:
        def ask(self, question: str) -> dict:
            _ = question
            return {
                "answer": "streamed answer",
                "quality_score": 80,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-123",
            }

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: (session_id or "session-123", _FakeSession()),
    )

    resp = client.post(
        "/api/ask/stream",
        json={"question": "test", "session_id": None},
        headers={"Accept": "text/event-stream"},
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_state_has_hyde_query() -> None:
    from state import create_initial_state

    state = create_initial_state("question")
    assert "hyde_query" in state
    assert state["hyde_query"] is None


def test_hyde_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_HYDE", raising=False)

    from config.settings import Settings

    settings = Settings()
    assert settings.hyde is False


def test_parent_child_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_PARENT_CHILD", raising=False)

    from config.settings import Settings

    settings = Settings()
    assert settings.parent_child is False


def test_build_retriever_default_returns_hybrid_when_parent_child_false() -> None:
    from langchain_core.documents import Document
    from manager import HybridRetriever, build_retriever

    doc = Document(page_content="test content", metadata={})
    vector_store = MagicMock()

    with patch("config.settings.get_settings") as mock_settings:
        mock_settings.return_value.parent_child = False
        mock_settings.return_value.hybrid_search = True
        mock_settings.return_value.retrieval_top_k = 5
        mock_settings.return_value.rerank_top_k = 3
        mock_settings.return_value.reranker_model = ""
        mock_settings.return_value.semantic_chunking = False

        retriever = build_retriever(
            docs=[doc],
            embeddings=MagicMock(),
            vector_store=vector_store,
            chunks=[doc],
        )

    assert isinstance(retriever, HybridRetriever)

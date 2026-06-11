import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


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
        def ask(self, question: str, *args, **kwargs) -> dict:
            _ = question, args, kwargs
            return {
                "answer": "streamed answer",
                "quality_score": 80,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-123",
            }

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-123", _FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    resp = client.post(
        "/api/ask/stream",
        json={"question": "test", "session_id": None},
        headers={"Accept": "text/event-stream"},
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_state_has_hyde_query() -> None:
    from agent.state import create_initial_state

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


def test_streaming_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STREAMING_ENABLED", raising=False)

    from config.settings import Settings

    settings = Settings()
    assert settings.streaming_enabled is False


def test_build_retriever_default_returns_hybrid_when_parent_child_false() -> None:
    from langchain_core.documents import Document

    from vectordb._base_manager import HybridRetriever, build_retriever

    doc = Document(page_content="test content", metadata={})
    vector_store = MagicMock()

    with patch("config.settings.get_settings") as mock_settings:
        mock_settings.return_value.parent_child = False
        mock_settings.return_value.hybrid_search = True
        mock_settings.return_value.retrieval_top_k = 5
        mock_settings.return_value.rerank_top_k = 3
        mock_settings.return_value.reranker_model = ""
        mock_settings.return_value.semantic_chunking = False
        mock_settings.return_value.parent_expansion = False
        mock_settings.return_value.parent_expansion_window = 2
        mock_settings.return_value.parent_expansion_max_chars = 3600

        retriever = build_retriever(
            docs=[doc],
            embeddings=MagicMock(),
            vector_store=vector_store,
            chunks=[doc],
        )

    assert isinstance(retriever, HybridRetriever)

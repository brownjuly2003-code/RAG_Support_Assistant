from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")

CLIENT_SETTINGS_OVERRIDES = {
    "streaming_enabled": True,
}


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for chunk in payload.split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk[6:]))
    return events


def test_chat_alias_returns_sync_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSession:
        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default") -> dict:
            _ = question, trace_id, tenant_id
            return {
                "answer": "chat alias answer",
                "quality_score": 81,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-chat-1",
            }

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id, tenant_id="default": (session_id or "session-chat-1", _FakeSession()),
    )

    response = client.post("/api/chat", json={"question": "test question"})

    assert response.status_code == 200
    assert response.json()["answer"] == "chat alias answer"


def test_chat_stream_uses_provider_streaming_llm(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeRetriever:
        def get_relevant_documents(self, question: str):
            _ = question
            return [
                SimpleNamespace(
                    page_content="Сброс пароля доступен через Reset Password.",
                    metadata={"source": "policy.md", "doc_id": "reset-1", "title": "Сброс пароля"},
                )
            ]

    class _StreamingLLM:
        supports_streaming = True

        async def generate_stream(self, messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            for token in ("Сброс ", "пароля"):
                yield token

    class _FakeSession:
        def __init__(self) -> None:
            self._retriever = _FakeRetriever()
            self._llm = _StreamingLLM()
            self.history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default") -> dict:
            _ = question, trace_id, tenant_id
            return {
                "answer": "fallback",
                "quality_score": 50,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-chat-stream-fallback",
            }

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id, tenant_id="default": (session_id or "session-chat-stream", _FakeSession()),
    )

    response = client.post(
        "/api/chat/stream",
        json={"question": "Как восстановить доступ?"},
        headers={"Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert [event["token"] for event in events if event.get("type") == "token"] == ["Сброс ", "пароля"]
    result = next(event for event in events if event.get("type") == "result")
    assert result["answer"] == "Сброс пароля"
    assert captured["messages"]


def test_health_exposes_streaming_feature_flag(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=1.0)

    monkeypatch.setattr(api_app, "_probe_ollama", _ok)
    monkeypatch.setattr(api_app, "_probe_gracekelly", _ok, raising=False)
    monkeypatch.setattr(api_app, "_probe_chromadb", _ok)
    monkeypatch.setattr(api_app, "_probe_sqlite", _ok)
    monkeypatch.setattr(api_app, "_probe_postgres", _ok, raising=False)
    monkeypatch.setattr(api_app, "_probe_redis", _ok, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["features"]["streaming_enabled"] is True

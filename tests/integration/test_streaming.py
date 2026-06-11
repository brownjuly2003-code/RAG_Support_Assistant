from __future__ import annotations

import types
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_streaming_endpoint_emits_tokens_and_final_result(
    monkeypatch: pytest.MonkeyPatch,
    integration_api_app,
    integration_client,
    integration_headers,
    integration_store,
    parse_sse_events,
) -> None:
    class FakeRetriever:
        def get_relevant_documents(self, question: str):
            _ = question
            return [
                types.SimpleNamespace(
                    page_content="Сброс пароля доступен через ссылку Reset Password.",
                    metadata={"source": "policy.md", "doc_id": "reset-1", "title": "Сброс пароля"},
                )
            ]

    class FakeQuestionLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            return "- Как сменить пароль?\n- Где включить MFA?"

    class FakeSession:
        def __init__(self, tenant_id: str) -> None:
            self._tenant_id = tenant_id
            self._history: list[dict[str, str]] = []
            self._retriever = FakeRetriever()
            self._llm = FakeQuestionLLM()

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default", **kwargs) -> dict:
            _ = question, trace_id, tenant_id
            return {"answer": "fallback", "quality_score": 50, "route": "auto", "graded_docs": []}

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        normalized = session_id or uuid.uuid4().hex
        key = (tenant_id, normalized)
        sessions = integration_store["sessions"]
        if key not in sessions:
            sessions[key] = FakeSession(tenant_id)
        return normalized, sessions[key]

    async def _fake_stream_ollama(prompt: str, model_name: str, base_url: str):
        _ = prompt, model_name, base_url
        for token in ("Сброс ", "пароля"):
            yield token

    monkeypatch.setattr(integration_api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(integration_api_app, "_stream_ollama", _fake_stream_ollama)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)

    response = integration_client.post(
        "/api/ask/stream",
        json={"question": "Как восстановить доступ?"},
        headers={**integration_headers("acme", "admin"), "Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    assert events[0] == {"type": "status", "node": "processing"}
    assert any(event == {"type": "token_start"} for event in events)
    assert [event["token"] for event in events if event.get("type") == "token"] == ["Сброс ", "пароля"]

    result = next(event for event in events if event.get("type") == "result")
    assert result["answer"] == "Сброс пароля"
    assert result["sources"][0]["source"] == "policy.md"
    assert result["citations"][0]["doc_id"] == "reset-1"
    assert len(result["suggested_questions"]) == 2

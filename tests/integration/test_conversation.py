from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_multi_turn_conversation_persists_history(
    monkeypatch: pytest.MonkeyPatch,
    integration_api_app,
    integration_client,
    integration_headers,
    integration_store,
) -> None:
    class FakeSession:
        def __init__(self, tenant_id: str) -> None:
            self._tenant_id = tenant_id
            self._history: list[dict[str, str]] = []

        @property
        def history(self) -> list[dict[str, str]]:
            return self._history

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default", **kwargs) -> dict:
            _ = trace_id, tenant_id
            turn = len(self._history) // 2 + 1
            previous = self._history[-1]["content"] if self._history else "нет истории"
            answer = f"turn={turn}; prev={previous}; q={question}"
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": answer})
            return {
                "answer": answer,
                "quality_score": 90,
                "route": "auto",
                "graded_docs": [],
                "trace_id": f"trace-turn-{turn}",
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        normalized = session_id or uuid.uuid4().hex
        key = (tenant_id, normalized)
        sessions = integration_store["sessions"]
        if key not in sessions:
            sessions[key] = FakeSession(tenant_id)
        integration_api_app._sessions[normalized] = sessions[key]
        return normalized, sessions[key]

    monkeypatch.setattr(integration_api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)

    first = integration_client.post(
        "/api/ask",
        json={"question": "Первый вопрос"},
        headers=integration_headers("acme", "admin"),
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = integration_client.post(
        "/api/ask",
        json={"question": "Второй вопрос", "session_id": session_id},
        headers=integration_headers("acme", "admin"),
    )
    third = integration_client.post(
        "/api/ask",
        json={"question": "Третий вопрос", "session_id": session_id},
        headers=integration_headers("acme", "admin"),
    )

    assert second.status_code == 200
    assert third.status_code == 200
    assert "turn=2" in second.json()["answer"]
    assert "turn=3" in third.json()["answer"]

    history = integration_client.get(
        f"/api/sessions/{session_id}/history",
        headers=integration_headers("acme", "admin"),
    )
    sessions = integration_client.get(
        "/api/sessions",
        headers=integration_headers("acme", "admin"),
    )

    assert history.status_code == 200
    assert len(history.json()["messages"]) == 6
    assert sessions.status_code == 200
    assert any(
        item["session_id"] == session_id and item["message_count"] == 6
        for item in sessions.json()
    )

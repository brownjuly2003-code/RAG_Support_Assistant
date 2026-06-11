from __future__ import annotations

import json
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_low_quality_answer_can_be_escalated_to_ticket_and_inbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    integration_api_app,
    integration_client,
    integration_headers,
    integration_store,
) -> None:
    class FakeSession:
        def __init__(self, tenant_id: str) -> None:
            self._tenant_id = tenant_id
            self._history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default", **kwargs) -> dict:
            _ = question, trace_id, tenant_id
            return {
                "answer": "Недостаточно данных для автоматического ответа.",
                "quality_score": 10,
                "route": "human",
                "graded_docs": [],
                "trace_id": "trace-escalate-1",
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        normalized = session_id or uuid.uuid4().hex
        key = (tenant_id, normalized)
        sessions = integration_store["sessions"]
        if key not in sessions:
            sessions[key] = FakeSession(tenant_id)
        return normalized, sessions[key]

    class FakeAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def add(self, item) -> None:
            if item.__class__.__name__ == "EscalatedTicket":
                integration_store["tickets"].append(item)

        async def commit(self) -> None:
            return None

    monkeypatch.setattr(integration_api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(integration_api_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("db.engine.async_session", lambda: FakeAsyncSession())

    ask_response = integration_client.post(
        "/api/ask",
        json={"question": "Нужна помощь оператора"},
        headers=integration_headers("acme", "admin"),
    )

    assert ask_response.status_code == 200
    assert ask_response.json()["route"] == "human"
    session_id = ask_response.json()["session_id"]

    escalate_response = integration_client.post(
        "/api/escalate",
        json={
            "session_id": session_id,
            "question": "Нужна помощь оператора",
            "reason": "low_quality",
        },
        headers=integration_headers("acme", "admin"),
    )

    assert escalate_response.status_code == 200
    assert integration_store["tickets"]
    ticket = integration_store["tickets"][0]
    assert ticket.tenant_id == "acme"
    assert ticket.status == "open"

    inbox_file = tmp_path / "data" / "inbox" / "support_inbox.jsonl"
    record = json.loads(inbox_file.read_text(encoding="utf-8").strip())
    assert record["question"] == "Нужна помощь оператора"
    assert record["reason"] == "low_quality"

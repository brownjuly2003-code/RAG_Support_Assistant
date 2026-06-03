"""Pipeline exception must persist an EscalatedTicket (Codex H2).

Before this fix /api/ask told the user "ваш вопрос передан оператору"
on a generic pipeline exception, but no ticket / inbox row was created
— operators could miss the request entirely.
"""

from __future__ import annotations

from typing import ClassVar

import importlib

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


def _auth(tenant: str = "tenant-x") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u1', 'admin', tenant)}"}


def test_pipeline_exception_persists_escalated_ticket(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    captured_tickets: list[dict] = []

    class _BrokenSession:
        _tenant_id = "tenant-x"
        _history: ClassVar[list[dict[str, str]]] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            raise RuntimeError("simulated provider outage")

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("sess-broken", _BrokenSession())

    class _FakeAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def add(self, item):
            if item.__class__.__name__ == "EscalatedTicket":
                captured_tickets.append(
                    {
                        "tenant_id": getattr(item, "tenant_id", None),
                        "session_id": getattr(item, "session_id", None),
                        "user_question": getattr(item, "user_question", None),
                        "status": getattr(item, "status", None),
                    }
                )

        async def commit(self):
            return None

    async def _fake_log_audit(**kwargs):
        return None

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    response = client.post(
        "/api/ask",
        json={"question": "сломайся пожалуйста"},
        headers=_auth("tenant-x"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "human"
    assert "оператор" in body["answer"].lower()

    assert captured_tickets, (
        "pipeline exception must produce an EscalatedTicket — operator "
        "would otherwise miss this request silently"
    )
    ticket = captured_tickets[0]
    assert ticket["tenant_id"] == "tenant-x"
    assert ticket["status"] == "open"
    assert "сломайся" in (ticket["user_question"] or "")

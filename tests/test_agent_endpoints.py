from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


def _token(tenant: str = "default", role: str = "agent") -> dict[str, str]:
    token = create_access_token("agent-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_agent_page_requires_agent_role(client_with_key: TestClient) -> None:
    forbidden = client_with_key.get("/agent", headers=_token("acme", "viewer"))
    allowed = client_with_key.get("/agent", headers=_token("acme", "agent"))

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_agent_tickets_list_filters_by_tenant_and_status(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, str] = {}

    class _Ticket:
        id = uuid.UUID("00000000-0000-0000-0000-000000000106")
        tenant_id = "acme"
        session_id = "session-106"
        user_question = "Нужен оператор"
        ai_draft = "Черновик"
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _ScalarResult:
        def all(self):
            return [_Ticket()]

    class _Result:
        def scalars(self):
            return _ScalarResult()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get(
        "/api/agent/tickets?status=open",
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    assert "escalated_tickets.tenant_id" in captured["sql"]
    assert "escalated_tickets.status" in captured["sql"]
    assert response.json()["tickets"][0]["tenant_id"] == "acme"


def test_agent_ticket_respond_marks_ticket_resolved(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    ticket_id = uuid.UUID("00000000-0000-0000-0000-000000000107")
    captured: dict[str, object] = {}

    class _Ticket:
        id = ticket_id
        tenant_id = "acme"
        session_id = "session-107"
        user_question = "Вопрос"
        ai_draft = "Черновик"
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, model, lookup_id):
            captured["model"] = getattr(model, "__name__", str(model))
            captured["lookup_id"] = lookup_id
            return _Ticket() if lookup_id == ticket_id else None

        async def commit(self):
            captured["committed"] = True

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client_with_key.post(
        f"/api/agent/tickets/{ticket_id}/respond",
        json={"response": "Готово, берём в работу"},
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    assert captured["lookup_id"] == ticket_id
    assert captured["committed"] is True
    assert response.json()["ticket"]["status"] == "resolved"
    assert response.json()["ticket"]["operator_response"] == "Готово, берём в работу"


def test_viewer_cannot_access_agent_ticket_endpoints(client_with_key: TestClient) -> None:
    response = client_with_key.get("/api/agent/tickets", headers=_token("acme", "viewer"))

    assert response.status_code == 403


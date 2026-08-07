"""4.4 — auto-escalate terminal human/error on normal /api/ask success path.

Plan residual after 4.3: exception/manual/handle_error already call
``services.escalation.create_escalation``. Normal pipeline success with
``route=human`` (low quality / budget) still only bumped metrics and never
created a durable ticket.

Contract:
- successful ask with ``route=human`` (or terminal error) → one durable
  escalation with ``source=human_route``;
- response carries ``ticket_id`` + ``delivery_state``;
- ``route=auto`` does not create a ticket;
- graph-provided ticket fields are passed through (no second insert);
- no false operator claim in answer when durable insert fails.
"""

from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


def _auth(tenant: str = "tenant-h") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u1', 'admin', tenant)}"}


class _FakeResult:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _FakeAsyncSession:
    store: ClassVar[list[Any]] = []

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def __aenter__(self) -> _FakeAsyncSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def add(self, item: Any) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid.uuid4()
        self.added.append(item)
        _FakeAsyncSession.store.append(item)

    async def commit(self) -> None:
        return None

    async def execute(self, stmt: Any) -> _FakeResult:  # noqa: ANN401
        text = str(stmt).lower()
        if _FakeAsyncSession.store and (
            "idempotency_key" in text or "escalated_tickets" in text
        ):
            return _FakeResult(_FakeAsyncSession.store[0])
        return _FakeResult(None)


@pytest.fixture(autouse=True)
def _reset_escalation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncSession.store = []
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())
    monkeypatch.setattr(
        "integrations.mock_inbox.get_support_sink",
        lambda: (_ for _ in ()).throw(ImportError("no sink")),
        raising=False,
    )


def _patch_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict[str, Any],
) -> None:
    class _Session:
        _tenant_id = "tenant-h"
        _history: ClassVar[list[dict[str, str]]] = []

        def ask(self, question, trace_id=None, tenant_id="default", **kwargs):
            return dict(result)

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("sess-human-4-4", _Session())

    async def _fake_log_audit(**kwargs):
        return None

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "PROJECT_ROOT", Path("."))


def test_human_route_creates_durable_ticket(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    _patch_session(
        monkeypatch,
        result={
            "answer": "Черновик: похоже, нужен оператор.",
            "quality_score": 40,
            "route": "human",
            "graded_docs": [],
            "citations": [],
            "trace_id": "tr-human-1",
            "suggested_questions": [],
        },
    )

    response = client.post(
        "/api/ask",
        json={"question": "подключите живого специалиста"},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "human"
    assert body.get("ticket_id"), "terminal human must return durable ticket_id"
    assert body.get("delivery_state") in {"delivered", "pending", "failed", "duplicate"}
    # Keep AI draft; do not force-overwrite with operator copy when durable ok.
    assert "Черновик" in body["answer"] or "тикет" in body["answer"].lower()

    tickets = [
        t
        for t in _FakeAsyncSession.store
        if t.__class__.__name__ == "EscalatedTicket"
        or getattr(t, "user_question", None)
    ]
    assert tickets, "route=human success path must insert EscalatedTicket"
    ticket = tickets[0]
    assert getattr(ticket, "tenant_id", None) == "tenant-h"
    assert getattr(ticket, "source", None) == "human_route"
    assert "специалист" in (getattr(ticket, "user_question", "") or "")


def test_auto_route_does_not_escalate(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    _patch_session(
        monkeypatch,
        result={
            "answer": "Ответ из базы знаний.",
            "quality_score": 92,
            "route": "auto",
            "graded_docs": [],
            "citations": [],
            "trace_id": "tr-auto-1",
            "suggested_questions": [],
        },
    )

    response = client.post(
        "/api/ask",
        json={"question": "что такое SLA?"},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "auto"
    assert body.get("ticket_id") in (None, "")
    assert body.get("delivery_state") in (None, "")
    assert not _FakeAsyncSession.store


def test_existing_ticket_fields_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Graph handle_error already escalated — do not create a second ticket."""
    existing_id = str(uuid.uuid4())
    _patch_session(
        monkeypatch,
        result={
            "answer": "Обращение зарегистрировано (тикет #deadbeef).",
            "quality_score": 0,
            "route": "error_escalation",
            "graded_docs": [],
            "citations": [],
            "trace_id": "tr-err-1",
            "suggested_questions": [],
            "ticket_id": existing_id,
            "delivery_state": "delivered",
        },
    )

    response = client.post(
        "/api/ask",
        json={"question": "ошибка уже эскалирована"},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticket_id"] == existing_id
    assert body["delivery_state"] == "delivered"
    assert not _FakeAsyncSession.store, "must not re-insert when ticket already present"


def test_no_operator_claim_when_human_route_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr("db.engine.async_session", lambda: _Boom())
    _patch_session(
        monkeypatch,
        result={
            "answer": "Черновик без эскалации.",
            "quality_score": 30,
            "route": "human",
            "graded_docs": [],
            "citations": [],
            "trace_id": "tr-fail-1",
            "suggested_questions": [],
        },
    )

    response = client.post(
        "/api/ask",
        json={"question": "нужен человек"},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "human"
    assert body.get("ticket_id") in (None, "")
    assert body.get("delivery_state") == "failed"
    # Never claim operator handoff without durable ticket.
    assert "передан оператору" not in (body.get("answer") or "").lower()
    # Keep useful draft rather than blanking the response.
    assert "Черновик" in body["answer"]

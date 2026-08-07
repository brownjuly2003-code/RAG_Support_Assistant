"""4.3 — idempotent durable escalation service."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest

from services import escalation as esc


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
        # Bound params rarely appear in str(stmt); for unit tests, any prior
        # insert is treated as the idempotent match / id refresh target.
        text = str(stmt).lower()
        if _FakeAsyncSession.store and (
            "idempotency_key" in text or "escalated_tickets" in text
        ):
            return _FakeResult(_FakeAsyncSession.store[0])
        return _FakeResult(None)


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _FakeAsyncSession.store = []
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())
    monkeypatch.setattr(esc, "async_session", lambda: _FakeAsyncSession(), raising=False)
    # Force JSONL path (no mock sink required).
    monkeypatch.setattr(
        "integrations.mock_inbox.get_support_sink",
        lambda: (_ for _ in ()).throw(ImportError("no sink")),
        raising=False,
    )


@pytest.mark.asyncio
async def test_create_escalation_durable_and_delivers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    outcome = await esc.create_escalation(
        tenant_id="acme",
        session_id="sess-1",
        question="нужен оператор",
        source="manual",
        reason="user_request",
        project_root=tmp_path,
    )
    assert outcome.durable is True
    assert outcome.ticket_id
    assert outcome.delivery_state == "delivered"
    assert "оператор" in outcome.user_message.lower() or "тикет" in outcome.user_message.lower()
    inbox = tmp_path / "data" / "inbox" / "support_inbox.jsonl"
    assert inbox.exists()
    assert "нужен оператор" in inbox.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_escalation_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    first = await esc.create_escalation(
        tenant_id="acme",
        session_id="sess-dup",
        question="same q",
        source="manual",
        reason="r",
        project_root=tmp_path,
    )
    assert first.ticket_id
    assert len(_FakeAsyncSession.store) == 1

    second = await esc.create_escalation(
        tenant_id="acme",
        session_id="sess-dup",
        question="same q",
        source="manual",
        reason="r",
        project_root=tmp_path,
    )
    assert second.already_existed is True
    assert second.delivery_state == "duplicate"
    assert second.ticket_id == first.ticket_id
    assert len(_FakeAsyncSession.store) == 1


@pytest.mark.asyncio
async def test_no_operator_claim_when_ticket_insert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr("db.engine.async_session", lambda: _Boom())

    outcome = await esc.create_escalation(
        tenant_id="acme",
        session_id="s",
        question="q",
        source="pipeline_error",
        project_root=tmp_path,
    )
    assert outcome.durable is False
    assert outcome.ticket_id is None
    assert "не удалось" in outcome.user_message.lower()
    assert "передан оператору" not in outcome.user_message.lower()


def test_make_idempotency_key_stable() -> None:
    a = esc.make_idempotency_key(
        tenant_id="t", session_id="s", source="manual", question="hello", reason="r"
    )
    b = esc.make_idempotency_key(
        tenant_id="t", session_id="s", source="manual", question="hello", reason="r"
    )
    c = esc.make_idempotency_key(
        tenant_id="t", session_id="s", source="manual", question="other", reason="r"
    )
    assert a == b
    assert a != c

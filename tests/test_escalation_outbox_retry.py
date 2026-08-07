"""4.5 — outbox retry for failed escalation deliveries.

Contract:
- select durable tickets with ``delivery_state=failed`` (optionally pending);
- re-attempt inbox delivery **without** creating a second ticket;
- update ``delivery_state`` / ``delivery_error`` honestly;
- skip already ``delivered`` / ``duplicate``;
- batch API returns counts for operator / worker wiring.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest

from services import escalation as esc


class _Ticket:
    """Minimal EscalatedTicket stand-in for unit tests."""

    def __init__(
        self,
        *,
        ticket_id: uuid.UUID | None = None,
        tenant_id: str = "acme",
        session_id: str = "sess-1",
        user_question: str = "нужен оператор",
        ai_draft: str | None = "draft",
        source: str = "human_route",
        trace_id: str | None = "tr-1",
        delivery_state: str = "failed",
        delivery_error: str | None = "disk full",
        status: str = "open",
    ) -> None:
        self.id = ticket_id or uuid.uuid4()
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.user_question = user_question
        self.ai_draft = ai_draft
        self.source = source
        self.trace_id = trace_id
        self.delivery_state = delivery_state
        self.delivery_error = delivery_error
        self.status = status


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None, row: Any = None) -> None:
        self._rows = rows if rows is not None else ([row] if row is not None else [])

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeAsyncSession:
    store: ClassVar[list[_Ticket]] = []

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def __aenter__(self) -> _FakeAsyncSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def add(self, item: Any) -> None:
        # Retry must never create new tickets.
        self.added.append(item)
        if item not in _FakeAsyncSession.store:
            _FakeAsyncSession.store.append(item)

    async def commit(self) -> None:
        return None

    async def execute(self, stmt: Any) -> _FakeResult:  # noqa: ANN401
        text = str(stmt).lower()
        # Batch list of failed/pending (retry_failed_deliveries).
        if "delivery_state" in text and "in (" in text:
            wanted = {"failed", "pending"}
            rows = [t for t in _FakeAsyncSession.store if t.delivery_state in wanted]
            rows.sort(key=lambda t: (0 if t.delivery_state == "failed" else 1, str(t.id)))
            return _FakeResult(rows=rows)
        # Prefer exact id match when store has multiple tickets.
        for ticket in _FakeAsyncSession.store:
            if str(ticket.id) in text or repr(ticket.id) in text:
                return _FakeResult(row=ticket)
        if _FakeAsyncSession.store and "escalated" in text:
            # Single-ticket tests: return the only / first retryable row.
            retryable = [t for t in _FakeAsyncSession.store if t.delivery_state in {"failed", "pending"}]
            if len(_FakeAsyncSession.store) == 1:
                return _FakeResult(row=_FakeAsyncSession.store[0])
            if retryable:
                return _FakeResult(row=retryable[0])
            return _FakeResult(row=_FakeAsyncSession.store[0])
        return _FakeResult()


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncSession.store = []
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())
    monkeypatch.setattr(esc, "async_session", lambda: _FakeAsyncSession(), raising=False)
    monkeypatch.setattr(
        "integrations.mock_inbox.get_support_sink",
        lambda: (_ for _ in ()).throw(ImportError("no sink")),
        raising=False,
    )


@pytest.mark.asyncio
async def test_retry_failed_delivery_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticket = _Ticket(delivery_state="failed", delivery_error="boom")
    _FakeAsyncSession.store = [ticket]
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    result = await esc.retry_escalation_delivery(
        str(ticket.id),
        project_root=tmp_path,
    )
    assert result.retried is True
    assert result.skipped is False
    assert result.delivery_state == "delivered"
    assert result.ticket_id == str(ticket.id)
    assert ticket.delivery_state == "delivered"
    assert ticket.delivery_error in (None, "")
    inbox = tmp_path / "data" / "inbox" / "support_inbox.jsonl"
    assert inbox.exists()
    body = inbox.read_text(encoding="utf-8")
    assert str(ticket.id) in body
    assert "нужен оператор" in body
    # No second ticket row.
    assert len(_FakeAsyncSession.store) == 1


@pytest.mark.asyncio
async def test_retry_skips_already_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticket = _Ticket(delivery_state="delivered", delivery_error=None)
    _FakeAsyncSession.store = [ticket]
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    result = await esc.retry_escalation_delivery(
        str(ticket.id),
        project_root=tmp_path,
    )
    assert result.skipped is True
    assert result.retried is False
    assert result.delivery_state == "delivered"
    assert "already" in result.skip_reason.lower() or "delivered" in result.skip_reason.lower()
    inbox = tmp_path / "data" / "inbox" / "support_inbox.jsonl"
    assert not inbox.exists()


@pytest.mark.asyncio
async def test_retry_batch_processes_failed_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = _Ticket(
        ticket_id=uuid.uuid4(),
        delivery_state="failed",
        user_question="failed one",
    )
    delivered = _Ticket(
        ticket_id=uuid.uuid4(),
        delivery_state="delivered",
        user_question="already ok",
    )
    _FakeAsyncSession.store = [failed, delivered]
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    batch = await esc.retry_failed_deliveries(limit=10, project_root=tmp_path)
    assert batch.attempted >= 1
    assert batch.delivered == 1
    assert batch.failed == 0
    assert failed.delivery_state == "delivered"
    assert delivered.delivery_state == "delivered"
    assert len(_FakeAsyncSession.store) == 2  # no new tickets


@pytest.mark.asyncio
async def test_retry_records_failure_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticket = _Ticket(delivery_state="failed", delivery_error="old")
    _FakeAsyncSession.store = [ticket]
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    def _boom(**kwargs: Any) -> tuple[str, str]:
        return "failed", "still broken"

    monkeypatch.setattr(esc, "_deliver_inbox", _boom)

    result = await esc.retry_escalation_delivery(
        str(ticket.id),
        project_root=tmp_path,
    )
    assert result.retried is True
    assert result.delivery_state == "failed"
    assert "still broken" in result.delivery_error
    assert ticket.delivery_state == "failed"
    assert ticket.delivery_error == "still broken"
    assert len(_FakeAsyncSession.store) == 1


@pytest.mark.asyncio
async def test_retry_missing_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeAsyncSession.store = []
    monkeypatch.setattr("db.engine.async_session", lambda: _FakeAsyncSession())

    result = await esc.retry_escalation_delivery(
        str(uuid.uuid4()),
        project_root=tmp_path,
    )
    assert result.skipped is True
    assert result.retried is False
    assert result.ticket_id

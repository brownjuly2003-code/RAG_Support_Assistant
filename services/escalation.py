"""Idempotent durable escalation service (plan §4.3–4.5).

Unifies DB ticket + inbox delivery behind one API:
- durable insert first (or reuse by idempotency_key);
- inbox/outbox delivery second with explicit ``delivery_state``;
- user-facing copy never claims "передано оператору" without a durable ticket;
- §4.5: retry failed (or pending) inbox delivery without a second ticket.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

DeliveryState = Literal["pending", "delivered", "failed", "duplicate"]
EscalationSource = Literal[
    "manual",
    "pipeline_error",
    "handle_error",
    "agentic",
    "human_route",
]

# States eligible for outbox re-delivery (never re-send delivered/duplicate).
_RETRYABLE_DELIVERY_STATES = frozenset({"failed", "pending"})


@dataclass(frozen=True, slots=True)
class EscalationOutcome:
    """Result of one escalation attempt."""

    ticket_id: str | None
    delivery_state: DeliveryState
    durable: bool
    already_existed: bool
    user_message: str
    source: str
    delivery_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "delivery_state": self.delivery_state,
            "durable": self.durable,
            "already_existed": self.already_existed,
            "user_message": self.user_message,
            "source": self.source,
            "delivery_error": self.delivery_error,
        }


def make_idempotency_key(
    *,
    tenant_id: str,
    session_id: str,
    source: str,
    question: str,
    trace_id: str = "",
    reason: str = "",
) -> str:
    """Stable key so disconnect/retry does not create duplicate open tickets."""
    q_hash = hashlib.sha256((question or "").encode("utf-8")).hexdigest()[:24]
    raw = "|".join(
        [
            (tenant_id or "default").strip(),
            (session_id or "").strip(),
            (source or "manual").strip(),
            (trace_id or "").strip(),
            (reason or "").strip(),
            q_hash,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _user_message(
    *,
    durable: bool,
    delivery_state: DeliveryState,
    ticket_id: str | None,
    already_existed: bool,
) -> str:
    if not durable or not ticket_id:
        return (
            "Не удалось зарегистрировать обращение. "
            "Повторите попытку или свяжитесь с поддержкой другим каналом."
        )
    short = ticket_id if len(ticket_id) <= 12 else ticket_id[:8]
    if already_existed or delivery_state == "duplicate":
        return (
            f"Обращение уже зарегистрировано (тикет #{short}). "
            "Оператор увидит его в очереди."
        )
    if delivery_state == "delivered":
        return (
            f"Ваш вопрос передан оператору (тикет #{short}). "
            "Мы ответим в ближайшее время."
        )
    if delivery_state == "failed":
        return (
            f"Обращение зарегистрировано (тикет #{short}), "
            "но доставка в inbox временно не удалась — оператор получит его после повтора."
        )
    # pending
    return (
        f"Обращение зарегистрировано (тикет #{short}). "
        "Ожидается доставка оператору."
    )


def _record_escalation_delivery(outcome: str) -> None:
    """Record one inbox delivery attempt without changing delivery semantics."""
    try:
        from monitoring.prometheus import (  # noqa: PLC0415
            record_escalation_delivery,
        )

        record_escalation_delivery(outcome)
    except Exception:
        logger.debug("Escalation delivery metric failed", exc_info=True)


def _deliver_inbox(
    *,
    project_root: Path,
    record: dict[str, Any],
) -> tuple[DeliveryState, str]:
    """Best-effort outbox delivery after durable ticket insert.

    The default ``local`` backend is the JSONL outbox under ``project_root``
    (full record, honours the configured root). An external sink
    (``SUPPORT_SINK_BACKEND`` other than ``local``) is tried first and the
    JSONL outbox remains the fallback. Routing the local backend through
    ``LocalFileSupportSink`` (ad5e435) wrote to a hardcoded repo path and
    dropped fields such as ``reason``/``ticket_id``; the integration test
    ``test_low_quality_answer_can_be_escalated_to_ticket_and_inbox`` caught it.
    """
    backend = os.getenv("SUPPORT_SINK_BACKEND", "local").strip().lower()
    if backend != "local":
        try:
            from integrations.mock_inbox import get_support_sink  # noqa: PLC0415

            entity_id = str(record.get("entity_id") or record.get("ticket_id") or "unknown")
            get_support_sink().send(entity_id, json.dumps(record, ensure_ascii=False))
            _record_escalation_delivery("delivered")
            return "delivered", ""
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Support sink delivery failed: %s", exc)

    try:
        inbox_path = project_root / "data" / "inbox" / "support_inbox.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        _record_escalation_delivery("delivered")
        return "delivered", ""
    except Exception as exc:
        logger.error("Inbox JSONL delivery failed: %s", exc)
        _record_escalation_delivery("failed")
        return "failed", str(exc)


# ---------------------------------------------------------------------------
# Plan §4.5 — outbox delivery retry (no second ticket)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeliveryRetryResult:
    """Result of re-attempting inbox delivery for one durable ticket."""

    ticket_id: str
    previous_state: str
    delivery_state: DeliveryState | str
    retried: bool
    skipped: bool
    skip_reason: str = ""
    delivery_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "previous_state": self.previous_state,
            "delivery_state": self.delivery_state,
            "retried": self.retried,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "delivery_error": self.delivery_error,
        }


@dataclass(frozen=True, slots=True)
class DeliveryRetryBatchResult:
    """Aggregate result of one outbox retry worker pass."""

    attempted: int
    delivered: int
    failed: int
    skipped: int
    results: list[DeliveryRetryResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "delivered": self.delivered,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.as_dict() for r in self.results],
        }


def _inbox_record_from_ticket(ticket: Any) -> dict[str, Any]:
    """Build the outbox payload from a durable EscalatedTicket row."""
    ticket_id = str(getattr(ticket, "id", "") or "")
    session_id = str(getattr(ticket, "session_id", "") or ticket_id)
    return {
        "entity_id": session_id,
        "ticket_id": ticket_id,
        "tenant_id": str(getattr(ticket, "tenant_id", "") or "default"),
        "session_id": session_id,
        "question": str(getattr(ticket, "user_question", "") or ""),
        "route": str(getattr(ticket, "source", "") or "retry"),
        "reason": "outbox_retry",
        "trace_id": str(getattr(ticket, "trace_id", "") or ""),
        "ts": datetime.now(timezone.utc).isoformat(),
        "retry": True,
    }


class EscalationService:
    """Single owner of the durable escalation ticket + outbox lifecycle."""

    async def create_escalation(
        self,
        *,
        tenant_id: str,
        session_id: str,
        question: str,
        source: EscalationSource | str = "manual",
        ai_draft: str | None = None,
        reason: str = "",
        trace_id: str = "",
        project_root: Path | None = None,
        deliver_inbox: bool = True,
        idempotency_key: str | None = None,
    ) -> EscalationOutcome:
        """Create (or reuse) a durable ticket, then deliver to inbox outbox."""
        from sqlalchemy import select  # noqa: PLC0415

        from db.engine import async_session  # noqa: PLC0415
        from db.models import EscalatedTicket  # noqa: PLC0415

        tenant = (tenant_id or "default").strip() or "default"
        session = (session_id or "").strip() or str(uuid.uuid4())
        q = (question or "").strip() or "(пустое обращение)"
        src = (source or "manual").strip() or "manual"
        key = idempotency_key or make_idempotency_key(
            tenant_id=tenant,
            session_id=session,
            source=src,
            question=q,
            trace_id=trace_id or "",
            reason=reason or "",
        )
        root = project_root or Path(__file__).resolve().parent.parent

        ticket_id: str | None = None
        durable = False
        already_existed = False
        delivery_state: DeliveryState = "pending"
        delivery_error = ""

        try:
            async with async_session() as db:
                existing = None
                try:
                    result = await db.execute(
                        select(EscalatedTicket).where(EscalatedTicket.idempotency_key == key)
                    )
                    existing = result.scalar_one_or_none()
                except Exception as lookup_exc:
                    # Pre-migration DBs or fakes without execute/columns.
                    logger.debug("Idempotency lookup skipped: %s", lookup_exc)
                    existing = None

                if existing is not None:
                    ticket_id = str(existing.id)
                    durable = True
                    already_existed = True
                    prior = str(getattr(existing, "delivery_state", "") or "pending")
                    delivery_state = (
                        "duplicate"
                        if prior in {"delivered", "duplicate", "pending", "failed"}
                        else "duplicate"
                    )
                    return EscalationOutcome(
                        ticket_id=ticket_id,
                        delivery_state="duplicate",
                        durable=True,
                        already_existed=True,
                        user_message=_user_message(
                            durable=True,
                            delivery_state="duplicate",
                            ticket_id=ticket_id,
                            already_existed=True,
                        ),
                        source=src,
                        delivery_error="",
                    )

                ticket = EscalatedTicket(
                    tenant_id=tenant,
                    session_id=session,
                    user_question=q,
                    ai_draft=ai_draft,
                    status="open",
                    idempotency_key=key,
                    source=src,
                    trace_id=(trace_id or None) or None,
                    delivery_state="pending",
                )
                db.add(ticket)
                await db.commit()
                ticket_id = str(ticket.id)
                durable = True
        except Exception as exc:
            logger.error("Durable escalation ticket insert failed: %s", exc, exc_info=True)
            return EscalationOutcome(
                ticket_id=None,
                delivery_state="failed",
                durable=False,
                already_existed=False,
                user_message=_user_message(
                    durable=False,
                    delivery_state="failed",
                    ticket_id=None,
                    already_existed=False,
                ),
                source=src,
                delivery_error=str(exc),
            )

        if deliver_inbox and ticket_id:
            record = {
                "entity_id": session,
                "ticket_id": ticket_id,
                "tenant_id": tenant,
                "session_id": session,
                "question": q,
                "route": src,
                "reason": reason or src,
                "trace_id": trace_id or "",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            delivery_state, delivery_error = _deliver_inbox(project_root=root, record=record)
            # Best-effort update delivery_state on the ticket row.
            try:
                async with async_session() as db:
                    result = await db.execute(
                        select(EscalatedTicket).where(EscalatedTicket.id == uuid.UUID(ticket_id))
                    )
                    row = result.scalar_one_or_none()
                    if row is not None:
                        row.delivery_state = delivery_state
                        row.delivery_error = delivery_error or None
                        await db.commit()
            except Exception as upd_exc:
                logger.debug("Could not update delivery_state: %s", upd_exc)

        return EscalationOutcome(
            ticket_id=ticket_id,
            delivery_state=delivery_state,
            durable=durable,
            already_existed=already_existed,
            user_message=_user_message(
                durable=durable,
                delivery_state=delivery_state,
                ticket_id=ticket_id,
                already_existed=already_existed,
            ),
            source=src,
            delivery_error=delivery_error,
        )

    def create_escalation_sync(self, **kwargs: Any) -> EscalationOutcome:
        """Sync wrapper for graph nodes and tools (thread-safe if loop already running)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.create_escalation(**kwargs))

        # Already inside an event loop — run on a worker thread with its own loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(self.create_escalation(**kwargs)))
            return future.result(timeout=60)

    async def retry_escalation_delivery(
        self,
        ticket_id: str,
        *,
        project_root: Path | None = None,
        allow_states: frozenset[str] | set[str] | None = None,
    ) -> DeliveryRetryResult:
        """Re-attempt inbox delivery for one durable ticket (no second insert).

        Skips tickets that are already ``delivered`` / ``duplicate`` or missing.
        Updates ``delivery_state`` / ``delivery_error`` on the existing row only.
        """
        from sqlalchemy import select  # noqa: PLC0415

        from db.engine import async_session  # noqa: PLC0415
        from db.models import EscalatedTicket  # noqa: PLC0415

        root = project_root or Path(__file__).resolve().parent.parent
        allowed = (
            frozenset(allow_states) if allow_states is not None else _RETRYABLE_DELIVERY_STATES
        )
        tid = (ticket_id or "").strip()
        if not tid:
            return DeliveryRetryResult(
                ticket_id="",
                previous_state="",
                delivery_state="failed",
                retried=False,
                skipped=True,
                skip_reason="empty ticket_id",
            )

        try:
            ticket_uuid = uuid.UUID(tid)
        except (TypeError, ValueError):
            return DeliveryRetryResult(
                ticket_id=tid,
                previous_state="",
                delivery_state="failed",
                retried=False,
                skipped=True,
                skip_reason="invalid ticket_id",
            )

        try:
            async with async_session() as db:
                result = await db.execute(
                    select(EscalatedTicket).where(EscalatedTicket.id == ticket_uuid)
                )
                ticket = result.scalar_one_or_none()
                if ticket is None:
                    return DeliveryRetryResult(
                        ticket_id=tid,
                        previous_state="",
                        delivery_state="failed",
                        retried=False,
                        skipped=True,
                        skip_reason="ticket not found",
                    )

                previous = str(getattr(ticket, "delivery_state", "") or "pending")
                if previous not in allowed:
                    return DeliveryRetryResult(
                        ticket_id=tid,
                        previous_state=previous,
                        delivery_state=previous,
                        retried=False,
                        skipped=True,
                        skip_reason=f"already {previous}",
                    )

                record = _inbox_record_from_ticket(ticket)
                new_state, delivery_error = _deliver_inbox(project_root=root, record=record)
                ticket.delivery_state = new_state
                ticket.delivery_error = delivery_error or None
                await db.commit()

                return DeliveryRetryResult(
                    ticket_id=tid,
                    previous_state=previous,
                    delivery_state=new_state,
                    retried=True,
                    skipped=False,
                    delivery_error=delivery_error,
                )
        except Exception as exc:
            logger.error("Outbox retry failed for ticket_id=%s: %s", tid, exc, exc_info=True)
            return DeliveryRetryResult(
                ticket_id=tid,
                previous_state="",
                delivery_state="failed",
                retried=False,
                skipped=True,
                skip_reason=f"retry error: {exc}",
                delivery_error=str(exc),
            )

    async def retry_failed_deliveries(
        self,
        *,
        limit: int = 50,
        project_root: Path | None = None,
        states: Sequence[str] = ("failed",),
        tenant_id: str | None = None,
    ) -> DeliveryRetryBatchResult:
        """One worker pass: re-deliver durable tickets with failed (or listed) state.

        Never creates new tickets. Bound by ``limit`` for safe cron / operator runs.
        """
        from sqlalchemy import select  # noqa: PLC0415

        from db.engine import async_session  # noqa: PLC0415
        from db.models import EscalatedTicket  # noqa: PLC0415

        root = project_root or Path(__file__).resolve().parent.parent
        cap = max(1, min(int(limit or 50), 500))
        wanted = tuple(
            s.strip()
            for s in states
            if isinstance(s, str) and s.strip() in _RETRYABLE_DELIVERY_STATES
        ) or ("failed",)

        ticket_ids: list[str] = []
        try:
            async with async_session() as db:
                stmt = select(EscalatedTicket).where(EscalatedTicket.delivery_state.in_(wanted))
                if tenant_id:
                    stmt = stmt.where(EscalatedTicket.tenant_id == tenant_id.strip())
                # Prefer older open failures first when column is available.
                try:
                    stmt = stmt.order_by(EscalatedTicket.created_at.asc())
                except Exception:
                    pass
                stmt = stmt.limit(cap)
                result = await db.execute(stmt)
                rows = list(result.scalars().all())
                ticket_ids = [str(row.id) for row in rows]
        except Exception as exc:
            logger.error("Outbox retry batch listing failed: %s", exc, exc_info=True)
            return DeliveryRetryBatchResult(
                attempted=0, delivered=0, failed=0, skipped=0, results=[]
            )

        results: list[DeliveryRetryResult] = []
        delivered = 0
        failed = 0
        skipped = 0
        for tid in ticket_ids:
            item = await self.retry_escalation_delivery(
                tid,
                project_root=root,
                allow_states=frozenset(wanted),
            )
            results.append(item)
            if item.skipped:
                skipped += 1
            elif item.delivery_state == "delivered":
                delivered += 1
            else:
                failed += 1

        return DeliveryRetryBatchResult(
            attempted=len(results),
            delivered=delivered,
            failed=failed,
            skipped=skipped,
            results=results,
        )

    def retry_failed_deliveries_sync(self, **kwargs: Any) -> DeliveryRetryBatchResult:
        """Sync wrapper for cron / CLI / future Celery worker entrypoints."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.retry_failed_deliveries(**kwargs))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(self.retry_failed_deliveries(**kwargs)))
            return future.result(timeout=120)


escalation_service = EscalationService()


async def create_escalation(
    *,
    tenant_id: str,
    session_id: str,
    question: str,
    source: EscalationSource | str = "manual",
    ai_draft: str | None = None,
    reason: str = "",
    trace_id: str = "",
    project_root: Path | None = None,
    deliver_inbox: bool = True,
    idempotency_key: str | None = None,
) -> EscalationOutcome:
    """Create (or reuse) a durable ticket, then deliver to inbox outbox."""
    return await escalation_service.create_escalation(
        tenant_id=tenant_id,
        session_id=session_id,
        question=question,
        source=source,
        ai_draft=ai_draft,
        reason=reason,
        trace_id=trace_id,
        project_root=project_root,
        deliver_inbox=deliver_inbox,
        idempotency_key=idempotency_key,
    )


def create_escalation_sync(**kwargs: Any) -> EscalationOutcome:
    """Sync wrapper for graph nodes and tools (thread-safe if loop already running)."""
    return escalation_service.create_escalation_sync(**kwargs)


async def retry_escalation_delivery(
    ticket_id: str,
    *,
    project_root: Path | None = None,
    allow_states: frozenset[str] | set[str] | None = None,
) -> DeliveryRetryResult:
    """Re-attempt inbox delivery for one durable ticket (no second insert).

    Skips tickets that are already ``delivered`` / ``duplicate`` or missing.
    Updates ``delivery_state`` / ``delivery_error`` on the existing row only.
    """
    return await escalation_service.retry_escalation_delivery(
        ticket_id,
        project_root=project_root,
        allow_states=allow_states,
    )


async def retry_failed_deliveries(
    *,
    limit: int = 50,
    project_root: Path | None = None,
    states: Sequence[str] = ("failed",),
    tenant_id: str | None = None,
) -> DeliveryRetryBatchResult:
    """One worker pass: re-deliver durable tickets with failed (or listed) state.

    Never creates new tickets. Bound by ``limit`` for safe cron / operator runs.
    """
    return await escalation_service.retry_failed_deliveries(
        limit=limit,
        project_root=project_root,
        states=states,
        tenant_id=tenant_id,
    )


def retry_failed_deliveries_sync(**kwargs: Any) -> DeliveryRetryBatchResult:
    """Sync wrapper for cron / CLI / future Celery worker entrypoints."""
    return escalation_service.retry_failed_deliveries_sync(**kwargs)

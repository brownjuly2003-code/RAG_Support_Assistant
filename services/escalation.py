"""Idempotent durable escalation service (plan §4.3).

Unifies DB ticket + inbox delivery behind one API:
- durable insert first (or reuse by idempotency_key);
- inbox/outbox delivery second with explicit ``delivery_state``;
- user-facing copy never claims "передано оператору" without a durable ticket.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
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


def _deliver_inbox(
    *,
    project_root: Path,
    record: dict[str, Any],
) -> tuple[DeliveryState, str]:
    """Best-effort outbox delivery after durable ticket insert."""
    try:
        from integrations.mock_inbox import get_support_sink  # noqa: PLC0415

        entity_id = str(record.get("entity_id") or record.get("ticket_id") or "unknown")
        get_support_sink().send(entity_id, json.dumps(record, ensure_ascii=False))
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
        return "delivered", ""
    except Exception as exc:
        logger.error("Inbox JSONL delivery failed: %s", exc)
        return "failed", str(exc)


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
                delivery_state = "duplicate" if prior in {"delivered", "duplicate", "pending", "failed"} else "duplicate"
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


def create_escalation_sync(**kwargs: Any) -> EscalationOutcome:
    """Sync wrapper for graph nodes and tools (thread-safe if loop already running)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(create_escalation(**kwargs))

    # Already inside an event loop — run on a worker thread with its own loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: asyncio.run(create_escalation(**kwargs)))
        return future.result(timeout=60)

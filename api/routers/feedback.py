"""Feedback and escalation endpoints."""
from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api._shared import app_module as _app_module
from auth.dependencies import get_current_user, require_role
from monitoring import prometheus as prometheus_metrics

router = APIRouter()
logger = logging.getLogger(__name__)


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., max_length=100)
    session_id: str = Field(..., max_length=100)
    rating: str = Field(..., pattern=r"^(up|down)$")
    reason: Optional[str] = Field(default="", max_length=500)


class EscalateRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    question: str = Field(default="", max_length=2000)
    reason: str = Field(default="user_request", max_length=200)


async def _log_audit(**kwargs: Any) -> None:
    await _app_module().log_audit(**kwargs)


@router.post("/feedback", status_code=204)
async def post_feedback(
    request: Request,
    body: FeedbackRequest,
    _user: dict = Depends(get_current_user),
) -> None:
    """Save user feedback for an answer."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating must be 'up' or 'down'")
    prometheus_metrics.FEEDBACK_COUNT.labels(rating=body.rating).inc()
    try:
        from tracing.sqlite_trace import save_feedback  # noqa: PLC0415

        save_feedback(
            trace_id=body.trace_id,
            session_id=body.session_id,
            rating=body.rating,
            reason=body.reason or "",
            tenant_id=_user.get("tenant", "default") or "default",
        )
    except Exception as exc:
        logger.warning("Failed to save feedback: %s", exc)

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="feedback",
        resource=f"trace:{body.trace_id}",
        detail={
            "rating": body.rating,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )


@router.post("/escalate")
async def escalate_to_human(
    request: Request,
    body: EscalateRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Ручная эскалация: пользователь хочет оператора."""
    record = {
        "entity_id": body.session_id,
        "question": body.question,
        "route": "human_request",
        "reason": body.reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        inbox_path = _app_module().PROJECT_ROOT / "data" / "inbox" / "support_inbox.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write escalation: %s", exc)
        raise HTTPException(status_code=500, detail="Escalation failed") from exc

    try:
        from db.engine import async_session  # noqa: PLC0415
        from db.models import EscalatedTicket  # noqa: PLC0415

        draft = None
        question_text = (body.question or "").strip()
        if question_text:
            draft = (
                f"Запрос пользователя: {question_text}\n\n"
                "Черновик ответа: Спасибо за обращение. Мы получили ваш запрос и передали его оператору. "
                "Проверим детали и вернёмся с решением."
            )

        async with async_session() as db:
            db.add(
                EscalatedTicket(
                    tenant_id=_user.get("tenant", "default"),
                    session_id=body.session_id,
                    user_question=question_text or "(пользователь запросил оператора)",
                    ai_draft=draft,
                    status="open",
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist escalated ticket: %s", exc)

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="escalate",
        resource=f"session:{body.session_id}",
        detail={
            "reason": body.reason,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )

    return {
        "status": "ok",
        "message": "Ваш запрос передан оператору. Мы ответим в ближайшее время.",
    }


@router.get("/feedback/stats")
async def feedback_stats(
    days: int = 30,
    _user: dict = Depends(require_role("agent", "admin")),
) -> dict:
    """Feedback stats for the last N days, scoped to caller's tenant.

    Admin может посмотреть глобальный snapshot через role=admin
    (исторический поведение), agent видит только свой tenant.
    """
    try:
        from tracing.sqlite_trace import get_feedback_stats  # noqa: PLC0415

        role = _user.get("role", "viewer")
        tenant_id = _user.get("tenant", "default") or "default"
        scope_tenant = None if role == "admin" else tenant_id
        return get_feedback_stats(days=days, tenant_id=scope_tenant)
    except Exception as exc:
        logger.warning("Failed to get feedback stats: %s", exc)
        return {
            "total": 0,
            "up": 0,
            "down": 0,
            "up_pct": 0.0,
            "by_route": {},
            "period_days": days,
        }

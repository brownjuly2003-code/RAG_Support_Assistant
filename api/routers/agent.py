"""Agent copilot endpoints — ticket queue, ticket detail, respond, similar.

Extracted from api.app on 2026-04-26 (Phase 2c). All four endpoints are
self-contained: they only depend on db.engine session + db.models.EscalatedTicket
and the cross-cutting auth/tenant helpers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from auth.dependencies import require_role
from db import engine as _db_engine
from db.models import EscalatedTicket, Message

router = APIRouter()


def _async_session():
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


async def _log_audit(**kwargs):
    """Indirection so test monkeypatch on api.app.log_audit takes effect."""
    _app = _app_module()
    return await _app.log_audit(**kwargs)


class AgentRespondRequest(BaseModel):
    response: str = Field(..., min_length=1, max_length=5000)


@router.get("/agent/tickets")
async def agent_list_tickets(
    status: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        stmt = (
            select(EscalatedTicket)
            .where(EscalatedTicket.tenant_id == tenant)
            .order_by(EscalatedTicket.created_at.desc())
        )
        if status:
            stmt = stmt.where(EscalatedTicket.status == status)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "tickets": [
                {
                    "id": str(row.id),
                    "tenant_id": row.tenant_id,
                    "session_id": row.session_id,
                    "user_question": row.user_question,
                    "ai_draft": row.ai_draft,
                    "operator_response": row.operator_response,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )


@router.get("/agent/tickets/{ticket_id}")
async def agent_get_ticket(
    ticket_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with _async_session() as db:
        ticket = await db.get(EscalatedTicket, ticket_uuid)
        if ticket is None or ticket.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="ticket not found")

        messages: list[dict[str, str | None]] = []
        try:
            session_uuid = uuid.UUID(ticket.session_id)
            message_result = await db.execute(
                select(Message)
                .where(Message.session_id == session_uuid)
                .order_by(Message.created_at)
            )
            messages = [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
                for message in message_result.scalars().all()
            ]
        except Exception:
            messages = []

        similar_result = await db.execute(
            select(EscalatedTicket)
            .where(
                EscalatedTicket.tenant_id == tenant,
                EscalatedTicket.status == "resolved",
                EscalatedTicket.id != ticket_uuid,
            )
            .order_by(EscalatedTicket.resolved_at.desc(), EscalatedTicket.created_at.desc())
            .limit(3)
        )
        similar_rows = similar_result.scalars().all()

    return JSONResponse(
        content={
            "ticket": {
                "id": str(ticket.id),
                "tenant_id": ticket.tenant_id,
                "session_id": ticket.session_id,
                "user_question": ticket.user_question,
                "ai_draft": ticket.ai_draft,
                "operator_response": ticket.operator_response,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            },
            "messages": messages,
            "retrieved_docs": [],
            "quality_scores": {},
            "similar_tickets": [
                {
                    "id": str(row.id),
                    "user_question": row.user_question,
                    "operator_response": row.operator_response,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in similar_rows
            ],
        }
    )


@router.post("/agent/tickets/{ticket_id}/respond")
async def agent_respond_to_ticket(
    request: Request,
    ticket_id: str,
    body: AgentRespondRequest,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with _async_session() as db:
        ticket = await db.get(EscalatedTicket, ticket_uuid)
        if ticket is None or ticket.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="ticket not found")

        ticket.operator_response = body.response.strip()
        ticket.status = "resolved"
        ticket.resolved_at = datetime.now(timezone.utc)
        await db.commit()

    await _log_audit(
        actor=_user.get("sub", "anonymous"),
        action="agent_respond",
        resource=f"ticket:{ticket_id}",
        detail={"tenant": tenant},
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(
        content={
            "status": "ok",
            "ticket": {
                "id": str(ticket.id),
                "tenant_id": ticket.tenant_id,
                "session_id": ticket.session_id,
                "user_question": ticket.user_question,
                "ai_draft": ticket.ai_draft,
                "operator_response": ticket.operator_response,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            },
        }
    )


@router.get("/agent/similar")
async def agent_similar_tickets(
    ticket_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with _async_session() as db:
        result = await db.execute(
            select(EscalatedTicket)
            .where(
                EscalatedTicket.tenant_id == tenant,
                EscalatedTicket.status == "resolved",
                EscalatedTicket.id != ticket_uuid,
            )
            .order_by(EscalatedTicket.resolved_at.desc(), EscalatedTicket.created_at.desc())
            .limit(3)
        )
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "tickets": [
                {
                    "id": str(row.id),
                    "user_question": row.user_question,
                    "operator_response": row.operator_response,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )

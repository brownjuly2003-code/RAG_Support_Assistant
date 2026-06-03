"""Agent copilot endpoints — ticket queue, ticket detail, respond, similar.

Extracted from api.app on 2026-04-26 (Phase 2c). All four endpoints are
self-contained: they only depend on db.engine session + db.models.EscalatedTicket
and the cross-cutting auth/tenant helpers.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any

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

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _async_session():
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


async def _log_audit(**kwargs):
    """Indirection so test monkeypatch on api.app.log_audit takes effect."""
    _app = _app_module()
    return await _app.log_audit(**kwargs)


def _term_set(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in _WORD_RE.findall(text.lower()):
        if len(raw) <= 2:
            continue
        terms.add(raw)
        trimmed = raw.rstrip("ьяеиыуюойомамах")
        if len(trimmed) > 2:
            terms.add(trimmed)
        for suffix in (
            "иями",
            "ями",
            "ами",
            "ого",
            "ему",
            "ить",
            "ать",
            "ять",
            "ия",
            "ый",
            "ой",
            "ая",
            "ое",
            "ые",
            "ых",
            "ую",
            "ом",
            "ам",
            "ах",
            "ов",
            "ев",
            "ей",
            "ий",
            "ия",
            "ие",
            "а",
            "я",
            "ы",
            "и",
            "е",
            "у",
            "ю",
            "ь",
        ):
            if raw.endswith(suffix) and len(raw) > len(suffix) + 2:
                terms.add(raw[: -len(suffix)].rstrip("ь"))
    return terms


def _similarity_score(query_terms: set[str], row: EscalatedTicket) -> tuple[int, float]:
    candidate_terms = _term_set(
        " ".join(
            [
                str(getattr(row, "user_question", "") or ""),
                str(getattr(row, "operator_response", "") or ""),
                str(getattr(row, "ai_draft", "") or ""),
            ]
        )
    )
    if not query_terms or not candidate_terms:
        return (0, 0.0)
    overlap = len(query_terms & candidate_terms)
    return (overlap, overlap / len(query_terms | candidate_terms))


def _sort_similar_tickets(ticket: EscalatedTicket, rows: list[EscalatedTicket]) -> list[EscalatedTicket]:
    query_terms = _term_set(
        " ".join(
            [
                str(ticket.user_question or ""),
                str(ticket.ai_draft or ""),
            ]
        )
    )
    scored_rows = [
        (score, row)
        for row in rows
        if (score := _similarity_score(query_terms, row))[0] > 0
    ]
    return [
        row
        for _score, row in sorted(
            scored_rows,
            key=lambda item: (
                item[0],
                getattr(item[1], "resolved_at", None)
                or getattr(item[1], "created_at", None)
                or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )[:3]
    ]


def _format_retrieved_docs(docs: list[Any]) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for doc in docs[:5]:
        if not isinstance(doc, dict):
            continue
        metadata = doc.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        title = doc.get("title") or metadata.get("title") or metadata.get("source") or "Document"
        source = doc.get("source") or metadata.get("source") or metadata.get("file_name") or ""
        excerpt = doc.get("excerpt") or doc.get("page_content") or doc.get("content") or ""
        formatted.append(
            {
                "title": str(title),
                "source": str(source),
                "excerpt": str(excerpt)[:300],
            }
        )
    return formatted


def _trace_context_for_ticket(ticket: EscalatedTicket, tenant: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    try:
        from tracing import sqlite_trace

        fallback: tuple[list[dict[str, str]], dict[str, Any]] | None = None
        ticket_session_id = str(getattr(ticket, "session_id", "") or "").strip()
        traces = sqlite_trace.list_recent_traces(limit=50, tenant_id=tenant)
        for trace in traces:
            detail = sqlite_trace.get_trace_detail(str(trace.get("trace_id")), tenant_id=tenant)
            if not detail:
                continue
            trace_session_id = str(trace.get("session_id") or "").strip()
            detail_session_id = str(detail.get("session_id") or "").strip()
            states: list[dict[str, Any]] = []
            for step in detail.get("steps", []):
                if not isinstance(step, dict):
                    continue
                state = step.get("state")
                if isinstance(state, dict):
                    states.append(state)
            for state in reversed(states):
                if str(state.get("question") or "").strip() != str(ticket.user_question or "").strip():
                    continue
                docs = state.get("graded_docs") or state.get("context_docs") or state.get("retrieved_docs") or []
                quality_scores = {
                    key: state[key]
                    for key in ("quality_score", "factuality_score", "relevance_score", "route")
                    if state.get(key) is not None and state.get(key) != ""
                }
                context = (_format_retrieved_docs(docs if isinstance(docs, list) else []), quality_scores)
                state_session_id = str(state.get("session_id") or "").strip()
                candidate_session_ids = {
                    session_id
                    for session_id in (trace_session_id, detail_session_id, state_session_id)
                    if session_id
                }
                if ticket_session_id and ticket_session_id in candidate_session_ids:
                    return context
                if fallback is None and (not ticket_session_id or not candidate_session_ids):
                    fallback = context
        if fallback is not None:
            return fallback
    except Exception:
        return [], {}
    return [], {}


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid ticket_id") from exc

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
        )
        similar_rows = _sort_similar_tickets(ticket, similar_result.scalars().all())

    retrieved_docs, quality_scores = await asyncio.to_thread(
        _trace_context_for_ticket,
        ticket,
        tenant,
    )

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
            "retrieved_docs": retrieved_docs,
            "quality_scores": quality_scores,
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid ticket_id") from exc

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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid ticket_id") from exc

    async with _async_session() as db:
        ticket = await db.get(EscalatedTicket, ticket_uuid)
        if ticket is None or ticket.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="ticket not found")

        result = await db.execute(
            select(EscalatedTicket)
            .where(
                EscalatedTicket.tenant_id == tenant,
                EscalatedTicket.status == "resolved",
                EscalatedTicket.id != ticket_uuid,
            )
            .order_by(EscalatedTicket.resolved_at.desc(), EscalatedTicket.created_at.desc())
        )
        rows = _sort_similar_tickets(ticket, result.scalars().all())

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

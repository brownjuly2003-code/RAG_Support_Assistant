from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Callable, TypeVar

from db.engine import async_session
from db.models import EscalatedTicket
from vectordb.manager import get_retriever


_ToolFunc = TypeVar("_ToolFunc", bound=Callable[..., Any])


def tool(func: _ToolFunc) -> _ToolFunc:
    return func


def _load_docs(query: str, tenant_id: str, retriever: Any | None = None) -> list[Any]:
    active_retriever = retriever or get_retriever(tenant_id=tenant_id)
    if hasattr(active_retriever, "invoke"):
        docs = active_retriever.invoke(query)
    elif hasattr(active_retriever, "get_relevant_documents"):
        docs = active_retriever.get_relevant_documents(query)
    elif callable(active_retriever):
        docs = active_retriever(query)
    else:
        docs = []
    return list(docs or [])[:3]


@tool
def search_kb(query: str, tenant_id: str, retriever: Any | None = None) -> str:
    """Search the knowledge base for document excerpts relevant to the query."""
    docs = _load_docs(query, tenant_id=tenant_id, retriever=retriever)
    if not docs:
        return "По базе знаний ничего не найдено."

    chunks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        if isinstance(doc, dict):
            content = str(doc.get("page_content", ""))
        else:
            content = str(getattr(doc, "page_content", ""))
        chunks.append(f"[{index}] {content[:240]}")
    return "\n\n".join(chunks)


@tool
def check_order_status(order_id: str, tenant_id: str) -> str:
    """Check a mock order-status backend and return a customer-facing status."""
    normalized = re.sub(r"\D+", "", order_id) or order_id
    status_map = {
        "42": "Заказ #42: статус 'в пути', доставка ожидается в течение 2 дней.",
        "7": "Заказ #7: статус 'собирается на складе'.",
    }
    status = status_map.get(
        normalized,
        f"Заказ #{normalized}: статус 'в обработке' (мок для tenant {tenant_id}).",
    )
    return status


async def _persist_ticket(
    summary: str,
    priority: str,
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> str:
    async with async_session() as db:
        ticket = EscalatedTicket(
            tenant_id=tenant_id,
            session_id=session_id or user_id or str(uuid.uuid4()),
            user_question=summary,
            ai_draft=f"priority={priority}",
            status="open",
        )
        db.add(ticket)
        await db.commit()
        return str(ticket.id)


@tool
def create_ticket(
    summary: str,
    priority: str,
    tenant_id: str,
    user_id: str,
    session_id: str = "",
) -> str:
    """Create an escalation ticket. This action is irreversible and requires confirmation."""
    ticket_id = asyncio.run(
        _persist_ticket(
            summary=summary,
            priority=priority,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
    )
    return f"Создан тикет #{ticket_id} с приоритетом {priority}."

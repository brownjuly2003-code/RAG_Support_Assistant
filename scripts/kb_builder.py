# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.engine import async_session
from db.models import EscalatedTicket, KbDraft
from utils.pii import redact_pii

KB_DRAFT_PROMPT = """Based on these resolved support tickets, write a KB article
that would answer the original questions. Use clear headings, short
paragraphs, and neutral tone. Do NOT include PII.

Output as JSON: {{"topic": "...", "content": "# Heading\\n\\nBody..."}}

Tickets:
{tickets_json}
"""


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{3,}", text.lower()))


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    universe = len(left_tokens | right_tokens)
    return overlap / universe if universe else 0.0


def cluster_resolved_tickets(
    rows: list[dict[str, Any]],
    min_cluster_size: int = 3,
) -> list[list[dict[str, Any]]]:
    by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_tenant[str(row.get("tenant_id") or "default")].append(row)

    clusters: list[list[dict[str, Any]]] = []
    for tenant_rows in by_tenant.values():
        visited: set[int] = set()
        for index, row in enumerate(tenant_rows):
            if index in visited:
                continue
            component = [row]
            visited.add(index)
            for candidate_index in range(index + 1, len(tenant_rows)):
                if candidate_index in visited:
                    continue
                candidate = tenant_rows[candidate_index]
                if _similarity(
                    str(row.get("user_question", "")),
                    str(candidate.get("user_question", "")),
                ) >= 0.2:
                    visited.add(candidate_index)
                    component.append(candidate)
            if len(component) >= min_cluster_size:
                clusters.append(component)
    return clusters


def _invoke_llm(llm: Any, prompt: str) -> str:
    if hasattr(llm, "invoke"):
        response = llm.invoke(prompt)
    elif callable(llm):
        response = llm(prompt)
    else:
        raise TypeError("LLM object does not support invoke()")
    if hasattr(response, "content"):
        return str(response.content)
    return str(response)


def _default_llm() -> Any:
    from agent.graph import LocalOllamaLLM
    from config.settings import get_settings

    settings = get_settings()
    return LocalOllamaLLM(model_name=settings.ollama_model_name)


def generate_kb_draft(
    cluster: list[dict[str, Any]],
    llm: Any | None = None,
) -> dict[str, str]:
    llm = llm or _default_llm()
    tickets_json = json.dumps(cluster, ensure_ascii=False, default=str)
    raw = _invoke_llm(llm, KB_DRAFT_PROMPT.format(tickets_json=tickets_json))
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {
            "topic": str(cluster[0].get("user_question") or "Авто-draft")[:120],
            "content": raw,
        }
    topic = redact_pii(str(payload.get("topic") or "Авто-draft"))
    content = redact_pii(str(payload.get("content") or ""))
    return {"topic": topic, "content": content}


def build_draft_records(
    rows: list[dict[str, Any]],
    llm: Any | None = None,
    min_cluster_size: int = 3,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for cluster in cluster_resolved_tickets(rows, min_cluster_size=min_cluster_size):
        draft = generate_kb_draft(cluster, llm=llm)
        records.append(
            {
                "tenant_id": str(cluster[0].get("tenant_id") or "default"),
                "topic": draft["topic"],
                "draft_content": draft["content"],
                "source_ticket_ids": [str(row.get("id")) for row in cluster if row.get("id") is not None],
                "status": "pending",
            }
        )
    return records


async def run_once(
    session_factory: Any = async_session,
    llm: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    since = current_time - timedelta(days=7)
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(EscalatedTicket).where(
                EscalatedTicket.status == "resolved",
                EscalatedTicket.resolved_at >= since,
            )
        )
        rows = result.scalars().all()
        records = build_draft_records(
            [
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_question": row.user_question,
                    "operator_response": row.operator_response,
                }
                for row in rows
            ],
            llm=llm,
        )
        for record in records:
            session.add(KbDraft(**record))
        if records:
            await session.commit()

    return {"status": "ok", "drafts_created": len(records)}


async def main() -> int:
    result = await run_once()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

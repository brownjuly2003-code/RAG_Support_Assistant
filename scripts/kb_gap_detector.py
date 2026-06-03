# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.engine import async_session
from db.models import KnowledgeGap
from tracing import sqlite_trace

_STOP_WORDS = {
    "как",
    "где",
    "что",
    "это",
    "для",
    "или",
    "про",
    "мой",
    "моя",
    "мои",
    "когда",
    "если",
    "надо",
    "могу",
    "хочу",
    "нужно",
}


def _normalize_question(question: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", question.lower())
    normalized: list[str] = []
    for token in tokens:
        if len(token) < 3 or token in _STOP_WORDS:
            continue
        stem = token
        for suffix in (
            "иями",
            "ями",
            "ами",
            "ого",
            "ему",
            "ому",
            "иях",
            "иях",
            "ах",
            "ях",
            "ов",
            "ев",
            "ий",
            "ый",
            "ой",
            "ая",
            "яя",
            "ое",
            "ее",
            "ть",
            "ти",
            "а",
            "я",
            "ы",
            "и",
            "е",
            "о",
            "у",
            "ю",
        ):
            if len(stem) > 4 and stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        normalized.append(stem)
    return normalized


def _question_similarity(left: str, right: str) -> float:
    left_tokens = set(_normalize_question(left))
    right_tokens = set(_normalize_question(right))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _summarize_cluster(rows: list[dict[str, Any]]) -> str:
    token_counts: Counter[str] = Counter()
    for row in rows:
        token_counts.update(_normalize_question(str(row.get("question", ""))))
    common = [token for token, _count in token_counts.most_common(3)]
    if common:
        return f"Недостающая тема: {', '.join(common)}"
    return "Недостающая тема в базе знаний"


def build_gap_records(
    rows: list[dict[str, Any]],
    min_cluster_size: int = 5,
) -> list[dict[str, Any]]:
    grouped_by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_by_tenant[row.get("tenant_id") or "default"].append(row)

    gap_records: list[dict[str, Any]] = []
    for tenant_id, tenant_rows in grouped_by_tenant.items():
        remaining = list(range(len(tenant_rows)))
        visited: set[int] = set()
        clusters: list[list[dict[str, Any]]] = []

        for index in remaining:
            if index in visited:
                continue
            queue = [index]
            component: list[dict[str, Any]] = []
            visited.add(index)

            while queue:
                current = queue.pop()
                component.append(tenant_rows[current])
                for candidate in remaining:
                    if candidate in visited:
                        continue
                    if _question_similarity(
                        str(tenant_rows[current].get("question", "")),
                        str(tenant_rows[candidate].get("question", "")),
                    ) >= 0.25:
                        visited.add(candidate)
                        queue.append(candidate)

            clusters.append(component)

        for cluster in clusters:
            if len(cluster) < min_cluster_size:
                continue
            sample_questions = [str(row.get("question", "")) for row in cluster[:3]]
            cluster_seed = "||".join(sorted(sample_questions))
            gap_records.append(
                {
                    "tenant_id": tenant_id,
                    "cluster_id": hashlib.sha1(cluster_seed.encode("utf-8")).hexdigest()[:12],
                    "topic_summary": _summarize_cluster(cluster),
                    "sample_questions": sample_questions,
                    "question_count": len(cluster),
                }
            )

    return gap_records


async def load_gap_questions(since: datetime) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with sqlite_trace._get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT trace_id, tenant_id
            FROM traces
            WHERE started_at >= ?
            ORDER BY started_at DESC
            """,
            (since.isoformat(),),
        )
        for trace_id, tenant_id in cur.fetchall():
            cur.execute(
                """
                SELECT state_json
                FROM trace_steps
                WHERE trace_id = ?
                ORDER BY step_order DESC
                LIMIT 1
                """,
                (trace_id,),
            )
            row = cur.fetchone()
            if row is None or not row[0]:
                continue
            try:
                state = json.loads(row[0])
            except (TypeError, ValueError):
                continue
            if not state.get("knowledge_gap"):
                continue
            question = str(state.get("question", "")).strip()
            if not question:
                continue
            records.append(
                {
                    "tenant_id": tenant_id or "default",
                    "trace_id": trace_id,
                    "question": question,
                }
            )
    return records


async def run_once(
    session_factory: Any = async_session,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    since = current_time - timedelta(days=7)
    questions = await load_gap_questions(since)
    gap_records = build_gap_records(questions)

    async with session_factory() as session:
        for gap in gap_records:
            session.add(
                KnowledgeGap(
                    tenant_id=gap["tenant_id"],
                    cluster_id=gap["cluster_id"],
                    topic_summary=gap["topic_summary"],
                    sample_questions=gap["sample_questions"],
                    question_count=gap["question_count"],
                )
            )
        if gap_records:
            await session.commit()

    return {
        "status": "ok",
        "questions": len(questions),
        "gaps_created": len(gap_records),
    }


async def main() -> int:
    result = await run_once()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

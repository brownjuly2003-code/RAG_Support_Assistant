# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from db.engine import async_session


def _parse_state(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_retrieved_docs(raw_docs: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_docs, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw_docs:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {}) or {}
        title = str(
            metadata.get("title")
            or metadata.get("source")
            or metadata.get("file_name")
            or metadata.get("doc_id")
            or "document"
        )
        excerpt = str(item.get("page_content") or item.get("excerpt") or "")[:500]
        source = str(
            metadata.get("source")
            or metadata.get("doc_id")
            or metadata.get("file_name")
            or title
        )
        normalized.append({"title": title, "excerpt": excerpt, "source": source})
    return normalized


def _normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw_tool_calls:
        if isinstance(item, dict):
            tool_name = str(item.get("tool") or item.get("name") or "").strip()
            if not tool_name:
                continue
            normalized.append({"tool": tool_name, "args": item.get("args")})
            continue
        tool_name = str(item).strip()
        if tool_name:
            normalized.append({"tool": tool_name, "args": None})
    return normalized


def _normalize_citations(raw_citations: Any) -> list[str]:
    if not isinstance(raw_citations, list):
        return []
    normalized: list[str] = []
    for index, item in enumerate(raw_citations, start=1):
        if isinstance(item, dict):
            value = item.get("index") or item.get("label") or index
        else:
            value = item or index
        label = str(value).strip()
        if not label:
            label = str(index)
        if not label.startswith("["):
            label = f"[{label}]"
        normalized.append(label)
    return normalized


def _load_trace_details(trace_ids: list[str], db_path: Path) -> dict[str, dict[str, Any]]:
    if not trace_ids or not db_path.exists():
        return {}

    unique_trace_ids = list(dict.fromkeys(trace_ids))
    placeholders = ", ".join("?" for _ in unique_trace_ids)
    details: dict[str, dict[str, Any]] = {
        trace_id: {
            "query": "",
            "answer": "",
            "final_route": None,
            "final_quality": None,
            "fact_score": None,
            "duration_ms": None,
            "retrieved_docs": [],
            "tool_calls": [],
            "citations": [],
        }
        for trace_id in unique_trace_ids
    }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_rows = conn.execute(
            f"""
            SELECT trace_id, final_route, final_quality
            FROM traces
            WHERE trace_id IN ({placeholders})
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in trace_rows:
            trace_id = str(row["trace_id"])
            details[trace_id]["final_route"] = row["final_route"]
            details[trace_id]["final_quality"] = (
                int(float(row["final_quality"]))
                if row["final_quality"] is not None
                else None
            )

        step_rows = conn.execute(
            f"""
            SELECT trace_id, state_json
            FROM trace_steps
            WHERE trace_id IN ({placeholders})
            ORDER BY trace_id ASC, step_order ASC, id ASC
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in step_rows:
            trace_id = str(row["trace_id"])
            state = _parse_state(row["state_json"])
            if not state:
                continue

            query = str(state.get("question") or state.get("query") or "").strip()
            if query:
                details[trace_id]["query"] = query

            answer = str(state.get("answer") or "").strip()
            if answer:
                details[trace_id]["answer"] = answer

            route = state.get("route")
            if route:
                details[trace_id]["final_route"] = str(route)

            quality = state.get("quality_score")
            if quality is not None and details[trace_id]["final_quality"] is None:
                try:
                    details[trace_id]["final_quality"] = int(float(quality))
                except (TypeError, ValueError):
                    pass

            fact_score = state.get("factuality_score", state.get("fact_score"))
            if fact_score is not None:
                try:
                    details[trace_id]["fact_score"] = int(float(fact_score))
                except (TypeError, ValueError):
                    pass

            duration_ms = state.get("duration_ms")
            if duration_ms is not None:
                try:
                    parsed_duration = int(float(duration_ms))
                except (TypeError, ValueError):
                    parsed_duration = None
                if parsed_duration is not None:
                    current_duration = details[trace_id]["duration_ms"]
                    details[trace_id]["duration_ms"] = (
                        parsed_duration
                        if current_duration is None
                        else max(int(current_duration), parsed_duration)
                    )

            docs = state.get("graded_docs") or state.get("context_docs")
            normalized_docs = _normalize_retrieved_docs(docs)
            if normalized_docs:
                details[trace_id]["retrieved_docs"] = normalized_docs

            tool_calls = _normalize_tool_calls(state.get("tool_calls"))
            if tool_calls:
                details[trace_id]["tool_calls"] = tool_calls

            citations = _normalize_citations(state.get("citations"))
            if citations:
                details[trace_id]["citations"] = citations

    return details


def _build_export_row(
    review_row: dict[str, Any],
    trace_details: dict[str, Any],
    *,
    exported_at: str,
) -> dict[str, Any]:
    return {
        "review_id": review_row["id"],
        "trace_id": review_row["trace_id"],
        "tenant_id": review_row["tenant_id"],
        "reason": review_row["reason"],
        "exported_at": exported_at,
        "query": trace_details.get("query") or "",
        "answer": trace_details.get("answer") or "",
        "final_route": trace_details.get("final_route"),
        "final_quality": trace_details.get("final_quality"),
        "fact_score": trace_details.get("fact_score"),
        "duration_ms": trace_details.get("duration_ms"),
        "retrieved_docs": trace_details.get("retrieved_docs") or [],
        "tool_calls": trace_details.get("tool_calls") or [],
        "citations": trace_details.get("citations") or [],
        "review": {"verdict": None, "notes": "", "fix_hint": "", "tags": []},
    }


def _default_output_path(now: datetime) -> Path:
    directory = PROJECT_ROOT / ".review_local"
    return directory / f"review_batch_{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl"


async def run_once(
    *,
    status: str,
    tenant: str,
    limit: int,
    out: Path | None = None,
    session_factory: Any = async_session,
    settings: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    output_path = Path(out) if out is not None else _default_output_path(current_time)
    exported_at = current_time.isoformat()

    query = """
        SELECT id, trace_id, tenant_id, reason, status, created_at
        FROM review_queue
        WHERE 1 = 1
    """
    params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
    if status not in {"", "*", "all"}:
        query += " AND status = :status"
        params["status"] = status
    if tenant not in {"", "*", "all"}:
        query += " AND tenant_id = :tenant_id"
        params["tenant_id"] = tenant
    query += " ORDER BY created_at DESC LIMIT :limit"

    async with session_factory() as session:
        rows = (await session.execute(text(query), params)).mappings().all()

    trace_db_path = Path(getattr(settings, "tracing_db_path", ""))
    trace_map = _load_trace_details([str(row["trace_id"]) for row in rows], trace_db_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"# review_batch exported {exported_at} - fill `review` object per line, "
            f"then: python scripts/review_import.py {output_path.name}\n"
        )
        for row in rows:
            payload = _build_export_row(
                row,
                trace_map.get(str(row["trace_id"]), {}),
                exported_at=exported_at,
            )
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return {
        "status": "ok",
        "count": len(rows),
        "out": str(output_path.resolve()),
        "exported_at": exported_at,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="pending")
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = await run_once(
        status=str(args.status or "pending"),
        tenant=str(args.tenant or "all"),
        limit=max(1, int(args.limit)),
        out=Path(args.out) if args.out else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

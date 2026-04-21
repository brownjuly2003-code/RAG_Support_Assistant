# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from db.engine import async_session

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "как",
    "в",
    "во",
    "и",
    "из",
    "или",
    "на",
    "не",
    "но",
    "по",
    "с",
    "что",
    "это",
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_since(value: str | date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(value)
    if len(value) == 10:
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=timezone.utc)
    return _as_utc(parsed)


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return _as_utc(raw_value)
    try:
        return _as_utc(datetime.fromisoformat(str(raw_value)))
    except ValueError:
        return None


def _parse_state_blob(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_context_hint(raw_state: dict[str, Any]) -> str:
    explicit_hint = str(raw_state.get("context_hint") or "").strip()
    if explicit_hint:
        return explicit_hint

    docs = (
        raw_state.get("retrieved_docs")
        or raw_state.get("graded_docs")
        or raw_state.get("context_docs")
        or []
    )
    if not isinstance(docs, list):
        return ""

    parts: list[str] = []
    for item in docs[:3]:
        if isinstance(item, dict):
            label = item.get("title") or item.get("source") or item.get("doc_id") or item.get("id")
        else:
            label = item
        text_value = str(label or "").strip()
        if text_value:
            parts.append(text_value[:80])
    return " | ".join(parts)


def _load_trace_details(trace_ids: list[str], db_path: Path) -> dict[str, dict[str, Any]]:
    if not trace_ids or not db_path.exists():
        return {}

    unique_trace_ids = list(dict.fromkeys(trace_ids))
    placeholders = ", ".join("?" for _ in unique_trace_ids)
    details: dict[str, dict[str, Any]] = {
        trace_id: {
            "tenant_id": None,
            "query": "",
            "answer": "",
            "context_hint": "",
            "channel": "web",
            "route": None,
            "quality": None,
            "factuality": None,
            "citations_count": 0,
        }
        for trace_id in unique_trace_ids
    }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_rows = conn.execute(
            f"""
            SELECT trace_id, tenant_id, final_route, final_quality
            FROM traces
            WHERE trace_id IN ({placeholders})
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in trace_rows:
            trace_id = str(row["trace_id"])
            details[trace_id]["tenant_id"] = str(row["tenant_id"] or "")
            details[trace_id]["route"] = str(row["final_route"] or "") or None
            if row["final_quality"] is not None:
                details[trace_id]["quality"] = int(float(row["final_quality"]))

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
            state = _parse_state_blob(row["state_json"])
            if not state:
                continue

            query = str(state.get("question") or state.get("query") or "").strip()
            if query:
                details[trace_id]["query"] = query

            answer = str(
                state.get("answer")
                or state.get("final_answer")
                or state.get("response")
                or ""
            ).strip()
            if answer:
                details[trace_id]["answer"] = answer

            context_hint = _extract_context_hint(state)
            if context_hint:
                details[trace_id]["context_hint"] = context_hint

            channel = str(state.get("channel") or "").strip().lower()
            if channel:
                details[trace_id]["channel"] = channel

            route = str(state.get("route") or "").strip()
            if route:
                details[trace_id]["route"] = route

            raw_quality = state.get("quality_score", state.get("final_quality"))
            if raw_quality is not None:
                try:
                    details[trace_id]["quality"] = int(float(raw_quality))
                except (TypeError, ValueError):
                    pass

            raw_factuality = state.get("factuality_score", state.get("fact_score"))
            if raw_factuality is not None:
                try:
                    details[trace_id]["factuality"] = int(float(raw_factuality))
                except (TypeError, ValueError):
                    pass

            citations = state.get("citations") or []
            if isinstance(citations, list):
                details[trace_id]["citations_count"] = max(
                    int(details[trace_id]["citations_count"] or 0),
                    len(citations),
                )

    return details


def _parse_marked_list(notes: str, labels: tuple[str, ...]) -> list[str]:
    if not notes.strip():
        return []

    for label in labels:
        match = re.search(
            rf"(?:^|[\n;])\s*{re.escape(label)}\s*:\s*([^\n]+)",
            notes,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        values = [item.strip() for item in re.split(r"[|,;]", match.group(1)) if item.strip()]
        if values:
            return values
    return []


def _heuristic_answer_contains(answer: str) -> list[str]:
    tokens = [
        token.lower()
        for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", answer)
        if len(token) > 1
    ]
    phrases: list[str] = []
    seen: set[str] = set()

    for size in (3, 2):
        for index in range(len(tokens) - size + 1):
            chunk = tokens[index:index + size]
            if all(token in _STOPWORDS for token in chunk):
                continue
            phrase = " ".join(chunk)
            if phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
            if len(phrases) >= 5:
                return phrases
    return phrases


def _case_id(trace_id: str) -> str:
    return trace_id if trace_id.startswith("trace-") else f"trace-{trace_id}"


def _load_existing_records(out_path: Path) -> dict[str, dict[str, Any]]:
    if not out_path.exists():
        return {}

    records: dict[str, dict[str, Any]] = {}
    with out_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            case_id = str(record.get("case_id") or "").strip()
            if case_id:
                records[case_id] = record
    return records


def _build_record(
    row: dict[str, Any],
    trace_details: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    trace_id = str(row["trace_id"])
    human_verdict = "good" if row["status"] == "confirmed_good" else "bad"
    reviewer_notes = str(row.get("reviewer_notes") or "").strip()

    answer_contains = _parse_marked_list(
        reviewer_notes,
        ("answer_contains", "must_include", "include"),
    )
    answer_not_contains = _parse_marked_list(
        reviewer_notes,
        ("answer_not_contains", "must_not_include", "exclude"),
    )
    if human_verdict == "good" and not answer_contains:
        answer_contains = _heuristic_answer_contains(str(trace_details.get("answer") or ""))
    if human_verdict == "bad":
        answer_contains = []
        answer_not_contains = []

    created_at = _parse_datetime(row.get("created_at")) or now
    citations_count = int(trace_details.get("citations_count") or 0)
    route = str(trace_details.get("route") or "auto") or "auto"

    return {
        "case_id": _case_id(trace_id),
        "tenant_id": str(trace_details.get("tenant_id") or row["tenant_id"] or "default"),
        "input": {
            "query": str(trace_details.get("query") or ""),
            "context_hint": str(trace_details.get("context_hint") or ""),
            "channel": str(trace_details.get("channel") or "web"),
        },
        "expected": {
            "answer_contains": answer_contains,
            "answer_not_contains": answer_not_contains,
            "route": route,
            "min_quality": 70,
            "min_factuality": 70,
            "citations_min_count": max(1, citations_count) if human_verdict == "good" else citations_count,
        },
        "human_verdict": human_verdict,
        "reviewer_notes": reviewer_notes,
        "source_trace_id": trace_id,
        "created_at": created_at.isoformat(),
    }


async def run_once(
    *,
    tenant: str,
    since: str | date | datetime | None,
    out: Path,
    include_bad: bool,
    session_factory: Any = async_session,
    settings: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    since_dt = _normalize_since(since)

    query = """
        SELECT trace_id, tenant_id, status, reviewer_notes, created_at, reviewed_at
        FROM review_queue
        WHERE status IN ('confirmed_good'
    """
    if include_bad:
        query += ", 'confirmed_bad'"
    query += ")"

    params: dict[str, Any] = {}
    if tenant != "all":
        query += " AND tenant_id = :tenant_id"
        params["tenant_id"] = tenant
    query += " ORDER BY created_at ASC"

    async with session_factory() as session:
        rows = (await session.execute(text(query), params)).mappings().all()

    filtered_rows = []
    for row in rows:
        created_at = _parse_datetime(row.get("created_at"))
        if since_dt is not None and created_at is not None and created_at < since_dt:
            continue
        filtered_rows.append(dict(row))

    trace_ids = [str(row["trace_id"]) for row in filtered_rows]
    trace_details = _load_trace_details(trace_ids, Path(getattr(settings, "tracing_db_path")))

    records = _load_existing_records(out)
    written = 0
    for row in filtered_rows:
        record = _build_record(
            row,
            trace_details.get(str(row["trace_id"]), {}),
            current_time,
        )
        records[record["case_id"]] = record
        written += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    ordered_records = [records[key] for key in sorted(records)]
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in ordered_records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

    return {
        "status": "ok",
        "selected": len(filtered_rows),
        "written": written,
        "total": len(ordered_records),
        "out": str(out),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--since", default=None)
    parser.add_argument("--out", default="evaluation/curated_cases.jsonl")
    parser.add_argument("--include-bad", action="store_true")
    args = parser.parse_args()

    result = await run_once(
        tenant=args.tenant,
        since=args.since,
        out=Path(args.out),
        include_bad=args.include_bad,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from db.engine import async_session
from db.models import DocumentStats, EvalResult, KnowledgeGap

MIN_PRIORITY = 3.0
PRIORITY_BANDS = (
    ("Priority 1", "Critical", 7.0),
    ("Priority 2", "High", 5.0),
    ("Priority 3", "Medium", 3.0),
)
WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


def parse_week_spec(week: str) -> tuple[datetime, datetime]:
    match = WEEK_RE.fullmatch(week.strip())
    if match is None:
        raise ValueError("week must be in YYYY-Www format")
    year = int(match.group("year"))
    week_number = int(match.group("week"))
    start_date = date.fromisocalendar(year, week_number, 1)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    return start_dt, start_dt + timedelta(days=7)


def default_week_spec(now: datetime) -> str:
    monday = date.fromisocalendar(now.isocalendar().year, now.isocalendar().week, 1)
    previous = monday - timedelta(days=7)
    previous_iso = previous.isocalendar()
    return f"{previous_iso.year}-W{previous_iso.week:02d}"


def compute_priority(
    *,
    impact: float,
    frequency: int,
    latest_at: datetime,
    now: datetime,
) -> float:
    latest = latest_at if latest_at.tzinfo is not None else latest_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - latest).total_seconds() / 86400.0)
    recency = math.exp(-age_days / 7.0)
    return round(float(impact) * max(1, int(frequency)) * recency, 4)


def latest_persisted_week(project_root: Path) -> str | None:
    backlog_dir = Path(project_root) / "reports" / "improvement_backlog"
    if not backlog_dir.exists():
        return None
    weeks = [
        path.stem
        for path in backlog_dir.glob("*.md")
        if WEEK_RE.fullmatch(path.stem)
    ]
    return sorted(weeks, reverse=True)[0] if weeks else None


def list_archive_weeks(project_root: Path, year: int | None = None) -> list[dict[str, Any]]:
    backlog_dir = Path(project_root) / "reports" / "improvement_backlog"
    if not backlog_dir.exists():
        return []

    weeks: list[dict[str, Any]] = []
    for path in sorted(backlog_dir.glob("*.md"), reverse=True):
        if not WEEK_RE.fullmatch(path.stem):
            continue
        if year is not None and not path.stem.startswith(f"{year}-"):
            continue
        weeks.append(
            {
                "week": path.stem,
                "path": str(path.relative_to(project_root)).replace("\\", "/"),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return weeks


def _resolve_output_path(project_root: Path, out: str | Path | None, week: str) -> Path | None:
    if out is None:
        return None
    output_path = Path(out)
    if not output_path.is_absolute():
        output_path = Path(project_root) / output_path
    if output_path.name == "":
        output_path = output_path / f"{week}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _parse_datetime(raw_value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=timezone.utc)
    if isinstance(raw_value, str):
        try:
            parsed = datetime.fromisoformat(raw_value)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if fallback is not None:
        return fallback if fallback.tzinfo is not None else fallback.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _parse_state_blob(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _trace_topic(metadata: dict[str, Any], fallback: str) -> str:
    primary_category = str(metadata.get("primary_category") or "").strip()
    if primary_category:
        return primary_category
    categories = metadata.get("categories") or []
    if isinstance(categories, list):
        for category in categories:
            value = str(category or "").strip()
            if value:
                return value
    question = str(metadata.get("question") or "").strip()
    if question:
        words = question.split()
        return " ".join(words[:6])
    return fallback


def _trace_metadata(db_path: Path, trace_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not trace_ids or not db_path.exists():
        return {}

    unique_ids = list(dict.fromkeys(trace_ids))
    placeholders = ", ".join("?" for _ in unique_ids)
    metadata: dict[str, dict[str, Any]] = {
        trace_id: {
            "trace_id": trace_id,
            "question": "",
            "categories": [],
            "primary_category": "",
            "endpoint": "",
            "duration_ms": None,
            "started_at": None,
        }
        for trace_id in unique_ids
    }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_rows = conn.execute(
            f"""
            SELECT trace_id, started_at
            FROM traces
            WHERE trace_id IN ({placeholders})
            """,
            tuple(unique_ids),
        ).fetchall()
        for row in trace_rows:
            trace_id = str(row["trace_id"])
            metadata[trace_id]["started_at"] = _parse_datetime(row["started_at"], datetime.now(timezone.utc))

        step_rows = conn.execute(
            f"""
            SELECT trace_id, state_json
            FROM trace_steps
            WHERE trace_id IN ({placeholders})
            ORDER BY trace_id ASC, step_order ASC, id ASC
            """,
            tuple(unique_ids),
        ).fetchall()
        for row in step_rows:
            trace_id = str(row["trace_id"])
            state = _parse_state_blob(row["state_json"])
            if not metadata[trace_id]["question"] and state.get("question"):
                metadata[trace_id]["question"] = str(state["question"])

            categories = state.get("categories") or state.get("retrieved_categories") or []
            if not metadata[trace_id]["categories"] and isinstance(categories, list):
                metadata[trace_id]["categories"] = [str(item) for item in categories if str(item or "").strip()]

            if not metadata[trace_id]["primary_category"]:
                primary = state.get("primary_category")
                if primary:
                    metadata[trace_id]["primary_category"] = str(primary)
                elif metadata[trace_id]["categories"]:
                    metadata[trace_id]["primary_category"] = str(metadata[trace_id]["categories"][0])

            if not metadata[trace_id]["endpoint"]:
                endpoint = (
                    state.get("endpoint")
                    or state.get("route_template")
                    or state.get("path")
                    or state.get("request_path")
                )
                if endpoint:
                    metadata[trace_id]["endpoint"] = str(endpoint)

            raw_duration = state.get("duration_ms")
            try:
                duration_ms = float(raw_duration) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current = metadata[trace_id]["duration_ms"]
                metadata[trace_id]["duration_ms"] = duration_ms if current is None else max(float(current), duration_ms)

    return metadata


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((pct / 100.0) * len(ordered)) - 1)
    return float(ordered[index])


def _impact_for_source(source: str, settings: Any) -> float:
    weights = {
        "review": float(getattr(settings, "backlog_weight_review_bad", 3.0)),
        "thumbs_down": float(getattr(settings, "backlog_weight_thumbs_down", 2.0)),
        "kb_gap": float(getattr(settings, "backlog_weight_thumbs_down", 2.0)),
        "slow_trace": float(getattr(settings, "backlog_weight_slow", 1.5)),
        "freshness": float(getattr(settings, "backlog_weight_freshness", 1.0)),
        "evaluator_drift": float(getattr(settings, "backlog_weight_evaluator_drift", 2.5)),
    }
    return weights.get(source, 1.0)


def _suggested_action(source: str) -> str:
    actions = {
        "review": "Inspect confirmed-bad traces and update the prompt or add a KB entry.",
        "thumbs_down": "Review the trace transcripts and address the repeated user dissatisfaction pattern.",
        "kb_gap": "Create or expand a KB article for the missing topic cluster.",
        "slow_trace": "Investigate latency hotspots for the endpoint and tune the slow threshold if needed.",
        "freshness": "Review and refresh the cited document metadata/content.",
        "evaluator_drift": "Inspect evaluator inputs and recent model/prompt changes causing the regression.",
    }
    return actions.get(source, "Review the signal and add a concrete fix for this week.")


async def load_review_queue_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        query = """
            SELECT trace_id, tenant_id, reviewer_notes, reason, COALESCE(reviewed_at, created_at) AS signal_at
            FROM review_queue
            WHERE status = 'confirmed_bad'
              AND COALESCE(reviewed_at, created_at) >= :week_start
              AND COALESCE(reviewed_at, created_at) < :week_end
        """
        params: dict[str, Any] = {
            "week_start": week_start,
            "week_end": week_end,
        }
        if tenant != "all":
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant
        rows = (await session.execute(text(query), params)).mappings().all()

    trace_ids = [str(row["trace_id"]) for row in rows]
    metadata = _trace_metadata(Path(getattr(settings, "tracing_db_path")), trace_ids)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        trace_id = str(row["trace_id"])
        tenant_id = str(row["tenant_id"] or "default")
        label = _trace_topic(metadata.get(trace_id, {}), str(row["reason"] or "confirmed_bad"))
        key = (tenant_id, label)
        signal_at = _parse_datetime(row["signal_at"], week_start)
        item = grouped.setdefault(
            key,
            {
                "source": "review",
                "title": label,
                "tenant_id": tenant_id,
                "frequency": 0,
                "latest_at": signal_at,
                "trace_ids": [],
                "details": {"reason": str(row["reason"] or "confirmed_bad")},
            },
        )
        item["frequency"] += 1
        item["latest_at"] = max(item["latest_at"], signal_at)
        item["trace_ids"].append(trace_id)

    values = sorted(grouped.values(), key=lambda item: (-int(item["frequency"]), str(item["title"])))
    return values[:10]


async def load_kb_gap_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    _ = settings
    async with session_factory() as session:
        stmt = (
            select(KnowledgeGap)
            .where(KnowledgeGap.created_at >= week_start)
            .where(KnowledgeGap.created_at < week_end)
            .where(KnowledgeGap.resolved_at.is_(None))
            .order_by(KnowledgeGap.question_count.desc(), KnowledgeGap.created_at.desc())
        )
        if tenant != "all":
            stmt = stmt.where(KnowledgeGap.tenant_id == tenant)
        rows = (await session.execute(stmt)).scalars().all()

    return [
        {
            "source": "kb_gap",
            "title": row.topic_summary,
            "tenant_id": row.tenant_id,
            "frequency": int(row.question_count or 1),
            "latest_at": _parse_datetime(row.created_at, week_start),
            "trace_ids": [],
            "details": {
                "cluster_id": row.cluster_id,
                "sample_questions": list(row.sample_questions or []),
            },
        }
        for row in rows[:10]
    ]


async def load_slow_trace_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    _ = session_factory
    db_path = Path(getattr(settings, "tracing_db_path"))
    if not db_path.exists():
        return []

    threshold = float(getattr(settings, "slow_trace_threshold_ms", 10000))
    traces: dict[str, dict[str, Any]] = {}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT trace_id, tenant_id, started_at
            FROM traces
            WHERE started_at >= ? AND started_at < ?
        """
        params: list[Any] = [week_start.isoformat(), week_end.isoformat()]
        if tenant != "all":
            query += " AND tenant_id = ?"
            params.append(tenant)
        query += " ORDER BY started_at DESC"
        trace_rows = conn.execute(query, tuple(params)).fetchall()

        for row in trace_rows:
            trace_id = str(row["trace_id"])
            traces[trace_id] = {
                "trace_id": trace_id,
                "tenant_id": str(row["tenant_id"] or "default"),
                "started_at": _parse_datetime(row["started_at"], week_start),
                "duration_ms": None,
                "endpoint": "",
            }

        if not traces:
            return []

        placeholders = ", ".join("?" for _ in traces)
        step_rows = conn.execute(
            f"""
            SELECT trace_id, state_json
            FROM trace_steps
            WHERE trace_id IN ({placeholders})
            ORDER BY trace_id ASC, step_order ASC, id ASC
            """,
            tuple(traces.keys()),
        ).fetchall()

        for row in step_rows:
            trace_id = str(row["trace_id"])
            state = _parse_state_blob(row["state_json"])
            endpoint = (
                state.get("endpoint")
                or state.get("route_template")
                or state.get("path")
                or state.get("request_path")
            )
            if endpoint and not traces[trace_id]["endpoint"]:
                traces[trace_id]["endpoint"] = str(endpoint)

            raw_duration = state.get("duration_ms")
            try:
                duration_ms = float(raw_duration) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current = traces[trace_id]["duration_ms"]
                traces[trace_id]["duration_ms"] = duration_ms if current is None else max(float(current), duration_ms)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces.values():
        endpoint = str(trace["endpoint"] or "/api/ask")
        grouped[endpoint].append(trace)

    signals: list[dict[str, Any]] = []
    for endpoint, endpoint_traces in grouped.items():
        durations = [float(item["duration_ms"]) for item in endpoint_traces if item["duration_ms"] is not None]
        if not durations:
            continue
        p95_ms = _percentile(durations, 95)
        if p95_ms <= threshold:
            continue
        slow_traces = [item for item in endpoint_traces if float(item["duration_ms"] or 0.0) > threshold]
        if not slow_traces:
            continue
        tenant_counter = Counter(str(item["tenant_id"]) for item in slow_traces)
        most_common_tenant = tenant_counter.most_common(1)[0][0]
        signals.append(
            {
                "source": "slow_trace",
                "title": f"{endpoint}",
                "tenant_id": most_common_tenant,
                "frequency": len(slow_traces),
                "latest_at": max(item["started_at"] for item in slow_traces),
                "trace_ids": [str(item["trace_id"]) for item in slow_traces[:10]],
                "details": {
                    "p95_ms": round(p95_ms, 1),
                    "threshold_ms": threshold,
                },
            }
        )

    signals.sort(key=lambda item: (-int(item["frequency"]), str(item["title"])))
    return signals[:10]


async def load_freshness_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    _ = week_start, week_end
    from api.app import _list_tenant_documents  # noqa: PLC0415

    freshness_days = int(getattr(settings, "backlog_freshness_max_days", 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)

    async with session_factory() as session:
        stmt = select(DocumentStats).order_by(DocumentStats.citation_count.desc())
        if tenant != "all":
            stmt = stmt.where(DocumentStats.tenant_id == tenant)
        rows = (await session.execute(stmt)).scalars().all()

    tenant_documents: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        tenant_id = str(row.tenant_id or "default")
        if tenant_id not in tenant_documents:
            tenant_documents[tenant_id] = {
                item["doc_id"]: item
                for item in _list_tenant_documents(tenant_id)
            }

    signals: list[dict[str, Any]] = []
    for row in rows:
        tenant_id = str(row.tenant_id or "default")
        metadata = tenant_documents.get(tenant_id, {}).get(row.doc_id)
        if not metadata:
            continue
        try:
            last_updated = _parse_datetime(metadata.get("last_updated"), cutoff)
        except ValueError:
            continue
        if last_updated >= cutoff:
            continue
        last_cited_at = _parse_datetime(row.last_cited_at, datetime.now(timezone.utc)) if row.last_cited_at else datetime.now(timezone.utc)
        signals.append(
            {
                "source": "freshness",
                "title": str(metadata.get("title") or row.doc_id),
                "tenant_id": tenant_id,
                "frequency": max(1, int(row.citation_count or 1)),
                "latest_at": last_cited_at,
                "trace_ids": [],
                "details": {
                    "doc_id": row.doc_id,
                    "last_updated": last_updated.isoformat(),
                    "citation_count": int(row.citation_count or 0),
                },
            }
        )

    signals.sort(key=lambda item: (-int(item["frequency"]), str(item["title"])))
    return signals[:10]


async def load_evaluator_drift_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    _ = tenant, settings
    previous_start = week_start - timedelta(days=7)

    async with session_factory() as session:
        current_stmt = (
            select(
                EvalResult.metric_name,
                func.avg(EvalResult.value).label("avg_value"),
                func.count(EvalResult.id).label("count_value"),
                func.max(EvalResult.created_at).label("latest_at"),
            )
            .where(EvalResult.created_at >= week_start)
            .where(EvalResult.created_at < week_end)
            .group_by(EvalResult.metric_name)
        )
        previous_stmt = (
            select(
                EvalResult.metric_name,
                func.avg(EvalResult.value).label("avg_value"),
            )
            .where(EvalResult.created_at >= previous_start)
            .where(EvalResult.created_at < week_start)
            .group_by(EvalResult.metric_name)
        )
        current_rows = (await session.execute(current_stmt)).all()
        previous_rows = (await session.execute(previous_stmt)).all()

    previous = {str(metric_name): float(avg_value) for metric_name, avg_value in previous_rows if avg_value is not None}
    signals: list[dict[str, Any]] = []
    for metric_name, avg_value, count_value, latest_at in current_rows:
        metric = str(metric_name)
        current_avg = float(avg_value) if avg_value is not None else None
        previous_avg = previous.get(metric)
        if current_avg is None or previous_avg in (None, 0.0):
            continue
        drop_ratio = (previous_avg - current_avg) / previous_avg
        if drop_ratio <= 0.10:
            continue
        signals.append(
            {
                "source": "evaluator_drift",
                "title": metric,
                "tenant_id": "all",
                "frequency": max(1, int(count_value or 1)),
                "latest_at": _parse_datetime(latest_at, week_start),
                "trace_ids": [],
                "details": {
                    "current_mean": round(current_avg, 4),
                    "previous_mean": round(previous_avg, 4),
                    "drop_pct": round(drop_ratio * 100, 1),
                },
            }
        )

    signals.sort(key=lambda item: (-float(item["details"]["drop_pct"]), str(item["title"])))
    return signals[:10]


async def load_thumbs_down_signals(
    *,
    session_factory: Any,
    tenant: str,
    week_start: datetime,
    week_end: datetime,
    settings: Any,
) -> list[dict[str, Any]]:
    _ = session_factory
    db_path = Path(getattr(settings, "tracing_db_path"))
    if not db_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        feedback_enabled = _table_exists(conn, "feedback")
        if not feedback_enabled:
            return []
        query = """
            SELECT f.trace_id, f.ts, t.tenant_id
            FROM feedback f
            JOIN traces t ON t.trace_id = f.trace_id
            WHERE lower(f.rating) IN ('down', 'thumbs_down')
              AND f.ts >= ?
              AND f.ts < ?
        """
        params: list[Any] = [week_start.isoformat(), week_end.isoformat()]
        if tenant != "all":
            query += " AND t.tenant_id = ?"
            params.append(tenant)
        fetched = conn.execute(query, tuple(params)).fetchall()
        for row in fetched:
            rows.append(
                {
                    "trace_id": str(row["trace_id"]),
                    "tenant_id": str(row["tenant_id"] or "default"),
                    "ts": _parse_datetime(row["ts"], week_start),
                }
            )

    metadata = _trace_metadata(db_path, [row["trace_id"] for row in rows])
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        label = _trace_topic(metadata.get(row["trace_id"], {}), "thumbs_down")
        key = (row["tenant_id"], label)
        item = grouped.setdefault(
            key,
            {
                "source": "thumbs_down",
                "title": label,
                "tenant_id": row["tenant_id"],
                "frequency": 0,
                "latest_at": row["ts"],
                "trace_ids": [],
                "details": {},
            },
        )
        item["frequency"] += 1
        item["latest_at"] = max(item["latest_at"], row["ts"])
        item["trace_ids"].append(row["trace_id"])

    values = sorted(grouped.values(), key=lambda item: (-int(item["frequency"]), str(item["title"])))
    return values[:10]


def _serialize_item(item: dict[str, Any], now: datetime, settings: Any) -> dict[str, Any]:
    latest_at = _parse_datetime(item.get("latest_at"), now)
    impact = float(item.get("impact") or _impact_for_source(str(item["source"]), settings))
    frequency = max(1, int(item.get("frequency") or 1))
    priority = compute_priority(
        impact=impact,
        frequency=frequency,
        latest_at=latest_at,
        now=now,
    )
    age_days = max(0.0, (now - latest_at).total_seconds() / 86400.0)
    trace_ids = [str(trace_id) for trace_id in item.get("trace_ids") or []]
    return {
        "source": str(item["source"]),
        "title": str(item["title"]),
        "tenant_id": str(item.get("tenant_id") or "default"),
        "impact": round(impact, 2),
        "frequency": frequency,
        "priority": round(priority, 2),
        "latest_at": latest_at.isoformat(),
        "age_days": round(age_days, 1),
        "trace_ids": trace_ids[:10],
        "details": dict(item.get("details") or {}),
        "suggested_action": _suggested_action(str(item["source"])),
    }


def _group_label(priority: float) -> tuple[str, str]:
    for heading, label, threshold in PRIORITY_BANDS:
        if priority > threshold or math.isclose(priority, threshold):
            return heading, label
    return PRIORITY_BANDS[-1][0], PRIORITY_BANDS[-1][1]


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Improvement backlog - week {payload['week']} ({payload['week_start']} to {payload['week_end']})",
        "",
        "## Summary",
        f"- Items: {payload['summary']['items']} (priority >= {int(MIN_PRIORITY)})",
        "- Top source: " + (
            ", ".join(
                f"{source} ({count})"
                for source, count in payload["summary"]["top_sources"].items()
            ) or "none"
        ),
        "",
    ]

    grouped: dict[str, list[dict[str, Any]]] = {
        "Priority 1": [],
        "Priority 2": [],
        "Priority 3": [],
    }
    for item in payload["items"]:
        heading, _label = _group_label(float(item["priority"]))
        grouped[heading].append(item)

    for heading, label, threshold in PRIORITY_BANDS:
        lines.append(f"## {heading} - {label} ({'>=' if threshold == MIN_PRIORITY else '>'} {threshold:g})")
        lines.append("")
        if not grouped[heading]:
            lines.append("- No items")
            lines.append("")
            continue
        for item in grouped[heading]:
            lines.append(f"### [{item['source']}] {item['title']}")
            lines.append(
                f"- Source: {item['source']}, {item['frequency']} signal(s)"
            )
            lines.append(
                f"- Tenant: {item['tenant_id']}"
            )
            lines.append(
                f"- Impact: {item['impact']}, frequency: {item['frequency']}, recency: {item['age_days']}d"
            )
            lines.append(f"- Priority: {item['priority']}")
            lines.append(f"- Suggested action: {item['suggested_action']}")
            if item["trace_ids"]:
                lines.append(f"- Related trace_ids: {', '.join(item['trace_ids'])}")
            detail_parts = []
            for key, value in item["details"].items():
                if value in ("", None, [], {}):
                    continue
                detail_parts.append(f"{key}={value}")
            if detail_parts:
                lines.append(f"- Details: {'; '.join(detail_parts)}")
            lines.append("")

    lines.extend(
        [
            "## Backlog stats",
            "- Items by type: " + (
                ", ".join(
                    f"{source} {count}"
                    for source, count in payload["stats"]["items_by_type"].items()
                ) or "none"
            ),
            f"- Most common tenant: {payload['stats']['most_common_tenant']}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


async def _send_email_if_enabled(
    *,
    settings: Any,
    tenant: str,
    week: str,
    markdown: str,
) -> None:
    if not bool(getattr(settings, "backlog_email_enabled", False)):
        return
    recipient = str(getattr(settings, "tenant_admin_email", "") or "").strip()
    if not recipient:
        return
    from scripts.weekly_report import send_email  # noqa: PLC0415

    subject = f"Improvement backlog - {tenant} - {week}"
    await send_email([recipient], subject, markdown)


async def run_once(
    *,
    tenant: str = "all",
    week: str | None = None,
    out: str | Path | None = None,
    session_factory: Any = async_session,
    settings: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    resolved_week = week or default_week_spec(current_time)
    week_start_dt, week_end_dt = parse_week_spec(resolved_week)
    output_path = _resolve_output_path(
        Path(getattr(settings, "project_root", PROJECT_ROOT)),
        out,
        resolved_week,
    )

    loaders = (
        ("review", load_review_queue_signals),
        ("kb_gap", load_kb_gap_signals),
        ("slow_trace", load_slow_trace_signals),
        ("freshness", load_freshness_signals),
        ("evaluator_drift", load_evaluator_drift_signals),
        ("thumbs_down", load_thumbs_down_signals),
    )

    raw_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source_name, loader in loaders:
        try:
            loaded = await loader(
                session_factory=session_factory,
                tenant=tenant,
                week_start=week_start_dt,
                week_end=week_end_dt,
                settings=settings,
            )
        except Exception as exc:
            warnings.append(f"{source_name}: {exc}")
            loaded = []
        raw_items.extend(loaded)

    items = [
        _serialize_item(item, current_time, settings)
        for item in raw_items
    ]
    items = [item for item in items if float(item["priority"]) >= MIN_PRIORITY]
    items.sort(key=lambda item: (-float(item["priority"]), str(item["source"]), str(item["title"])))
    items = items[: int(getattr(settings, "backlog_max_items", 30))]

    items_by_type = Counter(item["source"] for item in items)
    most_common_tenant = Counter(item["tenant_id"] for item in items).most_common(1)
    payload = {
        "tenant": tenant,
        "week": resolved_week,
        "week_start": week_start_dt.date().isoformat(),
        "week_end": (week_end_dt - timedelta(days=1)).date().isoformat(),
        "summary": {
            "items": len(items),
            "top_sources": dict(items_by_type.most_common()),
        },
        "items": items,
        "stats": {
            "items_by_type": dict(items_by_type),
            "most_common_tenant": most_common_tenant[0][0] if most_common_tenant else "n/a",
        },
        "warnings": warnings,
        "generated_at": current_time.isoformat(),
    }

    markdown = render_markdown(payload)
    if output_path is not None:
        output_path.write_text(markdown, encoding="utf-8")

    await _send_email_if_enabled(
        settings=settings,
        tenant=tenant,
        week=resolved_week,
        markdown=markdown,
    )
    return payload


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--week", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    current_time = datetime.now(timezone.utc)
    resolved_week = args.week or default_week_spec(current_time)
    default_out = Path("reports") / "improvement_backlog" / f"{resolved_week}.md"

    result = await run_once(
        tenant=args.tenant,
        week=resolved_week,
        out=args.out or default_out,
        now=current_time,
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Shared helpers for extracted API routers."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import get_settings
from monitoring import prometheus as prometheus_metrics

_REVIEW_QUEUE_REASONS = (
    "thumbs_down",
    "low_quality",
    "escalated",
    "fact_fail",
    "slow_trace",
    "manual",
)
_REVIEW_QUEUE_STATUSES = (
    "pending",
    "in_review",
    "confirmed_good",
    "confirmed_bad",
    "dismissed",
)


def app_module() -> Any:
    from api import app as _app  # noqa: PLC0415

    return _app


def _review_queue_enabled() -> bool:
    return bool(getattr(get_settings(), "review_queue_enabled", True))


def _serialize_timestamp(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _reviewed_by_uuid(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        return str(uuid.UUID(str(raw_value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _load_review_queue_trace_details(trace_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not trace_ids:
        return {}

    db_path = Path(getattr(get_settings(), "tracing_db_path", ""))
    if not db_path.exists():
        return {}

    unique_trace_ids = list(dict.fromkeys(trace_ids))
    placeholders = ", ".join("?" for _ in unique_trace_ids)
    details: dict[str, dict[str, Any]] = {
        trace_id: {
            "quality": None,
            "duration_ms": None,
            "fact_score": None,
            "trace_url": f"/admin/traces/{trace_id}",
        }
        for trace_id in unique_trace_ids
    }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_rows = conn.execute(
            f"""
            SELECT trace_id, final_quality
            FROM traces
            WHERE trace_id IN ({placeholders})
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in trace_rows:
            trace_id = str(row["trace_id"])
            if row["final_quality"] is not None:
                details[trace_id]["quality"] = float(row["final_quality"])

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
            state_json = row["state_json"]
            try:
                state = json.loads(state_json) if state_json else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                state = {}
            if not isinstance(state, dict):
                continue

            raw_duration = state.get("duration_ms")
            try:
                duration_ms = int(float(raw_duration)) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current_duration = details[trace_id]["duration_ms"]
                details[trace_id]["duration_ms"] = (
                    duration_ms
                    if current_duration is None
                    else max(int(current_duration), duration_ms)
                )

            raw_fact_score = state.get("factuality_score", state.get("fact_score"))
            try:
                fact_score = float(raw_fact_score) if raw_fact_score is not None else None
            except (TypeError, ValueError):
                fact_score = None
            if fact_score is not None:
                details[trace_id]["fact_score"] = fact_score

    return details


async def _refresh_review_queue_metrics(_tenant: str | None = None) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    try:
        pending_counts = {reason: 0 for reason in _REVIEW_QUEUE_REASONS}
        confirmed_counts = {"good": 0, "bad": 0}
        oldest_pending_seconds = 0.0

        async with async_session() as db:
            pending_rows = (
                await db.execute(
                    text(
                        """
                        SELECT reason, COUNT(*) AS total
                        FROM review_queue
                        WHERE status = 'pending'
                        GROUP BY reason
                        """
                    )
                )
            ).mappings().all()
            for row in pending_rows:
                reason = str(row["reason"])
                if reason in pending_counts:
                    pending_counts[reason] = int(row["total"] or 0)

            confirmed_rows = (
                await db.execute(
                    text(
                        """
                        SELECT status, COUNT(*) AS total
                        FROM review_queue
                        WHERE status IN ('confirmed_good', 'confirmed_bad')
                        GROUP BY status
                        """
                    )
                )
            ).mappings().all()
            for row in confirmed_rows:
                status = str(row["status"])
                if status == "confirmed_good":
                    confirmed_counts["good"] = int(row["total"] or 0)
                elif status == "confirmed_bad":
                    confirmed_counts["bad"] = int(row["total"] or 0)

            oldest_rows = (
                await db.execute(
                    text(
                        """
                        SELECT MIN(created_at) AS oldest_pending
                        FROM review_queue
                        WHERE status = 'pending'
                        """
                    )
                )
            ).mappings().all()
            oldest_pending = oldest_rows[0]["oldest_pending"] if oldest_rows else None
            if oldest_pending is not None:
                if isinstance(oldest_pending, str):
                    oldest_pending = datetime.fromisoformat(oldest_pending)
                if oldest_pending.tzinfo is None:
                    oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
                oldest_pending_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - oldest_pending).total_seconds(),
                )

        for reason, count in pending_counts.items():
            prometheus_metrics.set_review_queue_pending(reason, count)
        for verdict, count in confirmed_counts.items():
            prometheus_metrics.set_review_queue_confirmed(verdict, count)
        prometheus_metrics.set_review_queue_oldest_pending(oldest_pending_seconds)
    except Exception:
        return None

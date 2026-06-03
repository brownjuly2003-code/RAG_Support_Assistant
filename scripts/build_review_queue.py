# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from db.engine import async_session

REVIEW_REASONS = (
    "thumbs_down",
    "low_quality",
    "escalated",
    "fact_fail",
    "slow_trace",
    "manual",
)


def _parse_state_blob(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_datetime(raw_value: str | None, fallback: datetime) -> datetime:
    if not raw_value:
        return fallback
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return fallback


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _select_reason(
    *,
    thumbs_down: bool,
    final_quality: float | None,
    quality_threshold: float,
    escalated: bool,
    fact_score: float | None,
    fact_verification_enabled: bool,
    fact_verification_min_score: float,
    duration_ms: float | None,
    slow_trace_threshold_ms: float,
) -> str | None:
    if thumbs_down:
        return "thumbs_down"
    if final_quality is not None and final_quality < quality_threshold:
        return "low_quality"
    if escalated:
        return "escalated"
    if (
        fact_verification_enabled
        and fact_score is not None
        and fact_score < fact_verification_min_score
    ):
        return "fact_fail"
    if duration_ms is not None and duration_ms > slow_trace_threshold_ms:
        return "slow_trace"
    return None


def _scan_trace_candidates(
    *,
    db_path: Path,
    days: int,
    tenant: str,
    settings: Any,
    now: datetime,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    cutoff = (now - timedelta(days=max(0, days))).isoformat()
    candidates: list[dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_sql = """
            SELECT trace_id, tenant_id, started_at, finished_at, final_route, final_quality, final_relevance
            FROM traces
            WHERE started_at >= ?
        """
        params: list[Any] = [cutoff]
        if tenant != "all":
            trace_sql += " AND tenant_id = ?"
            params.append(tenant)
        trace_sql += " ORDER BY started_at DESC"

        feedback_enabled = _table_exists(conn, "feedback")

        for row in conn.execute(trace_sql, tuple(params)).fetchall():
            trace_id = str(row["trace_id"])
            final_quality = float(row["final_quality"]) if row["final_quality"] is not None else None
            final_route = str(row["final_route"] or "")

            duration_ms: float | None = None
            fact_score: float | None = None
            escalated = final_route == "human"
            thumbs_down_fallback = False

            step_rows = conn.execute(
                """
                SELECT state_json
                FROM trace_steps
                WHERE trace_id = ?
                ORDER BY step_order ASC
                """,
                (trace_id,),
            ).fetchall()
            for step_row in step_rows:
                state = _parse_state_blob(step_row["state_json"])
                raw_duration = state.get("duration_ms")
                try:
                    parsed_duration = float(raw_duration) if raw_duration is not None else None
                except (TypeError, ValueError):
                    parsed_duration = None
                if parsed_duration is not None:
                    duration_ms = parsed_duration if duration_ms is None else max(duration_ms, parsed_duration)

                raw_fact_score = state.get("factuality_score", state.get("fact_score"))
                try:
                    parsed_fact_score = float(raw_fact_score) if raw_fact_score is not None else None
                except (TypeError, ValueError):
                    parsed_fact_score = None
                if parsed_fact_score is not None:
                    fact_score = parsed_fact_score

                if state.get("route") == "human":
                    escalated = True

                tool_calls = state.get("tool_calls") or []
                if isinstance(tool_calls, list):
                    if any(str(item) == "create_ticket" for item in tool_calls):
                        escalated = True

                rating = state.get("feedback_rating", state.get("rating"))
                if str(rating).lower() in {"down", "thumbs_down"}:
                    thumbs_down_fallback = True

            thumbs_down = thumbs_down_fallback
            if feedback_enabled:
                feedback_rows = conn.execute(
                    "SELECT rating FROM feedback WHERE trace_id = ?",
                    (trace_id,),
                ).fetchall()
                thumbs_down = any(str(item["rating"]).lower() in {"down", "thumbs_down"} for item in feedback_rows)

            reason = _select_reason(
                thumbs_down=thumbs_down,
                final_quality=final_quality,
                quality_threshold=float(getattr(settings, "quality_threshold", 80)),
                escalated=escalated,
                fact_score=fact_score,
                fact_verification_enabled=bool(getattr(settings, "fact_verification_enabled", True)),
                fact_verification_min_score=float(getattr(settings, "fact_verification_min_score", 70)),
                duration_ms=duration_ms,
                slow_trace_threshold_ms=float(getattr(settings, "slow_trace_threshold_ms", 10000)),
            )
            if reason is None:
                continue

            started_at = _parse_datetime(row["started_at"], now)
            finished_at = _parse_datetime(row["finished_at"], started_at) if row["finished_at"] else None
            candidates.append(
                {
                    "trace_id": trace_id,
                    "tenant_id": str(row["tenant_id"] or "default"),
                    "reason": reason,
                    "status": "pending",
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "final_route": final_route or None,
                    "final_quality": final_quality,
                    "final_relevance": (
                        float(row["final_relevance"])
                        if row["final_relevance"] is not None
                        else None
                    ),
                }
            )

    return candidates


async def run_once(
    *,
    days: int,
    tenant: str,
    session_factory: Any = async_session,
    settings: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not getattr(settings, "review_queue_enabled", True):
        return {"status": "disabled", "matched": 0, "inserted": 0}

    current_time = now or datetime.now(timezone.utc)
    db_path = Path(settings.tracing_db_path)
    candidates = _scan_trace_candidates(
        db_path=db_path,
        days=days,
        tenant=tenant,
        settings=settings,
        now=current_time,
    )

    inserted = 0
    async with session_factory() as session:
        for item in candidates:
            await session.execute(
                text(
                    """
                    INSERT INTO traces (
                        id,
                        started_at,
                        finished_at,
                        final_route,
                        final_quality,
                        final_relevance
                    ) VALUES (
                        :trace_id,
                        :started_at,
                        :finished_at,
                        :final_route,
                        :final_quality,
                        :final_relevance
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "trace_id": item["trace_id"],
                    "started_at": item["started_at"],
                    "finished_at": item["finished_at"],
                    "final_route": item["final_route"],
                    "final_quality": item["final_quality"],
                    "final_relevance": item["final_relevance"],
                },
            )
            result = await session.execute(
                text(
                    """
                    INSERT INTO review_queue (
                        trace_id,
                        tenant_id,
                        reason,
                        status,
                        created_at
                    ) VALUES (
                        :trace_id,
                        :tenant_id,
                        :reason,
                        :status,
                        :created_at
                    )
                    ON CONFLICT (trace_id) DO NOTHING
                    """
                ),
                {
                    "trace_id": item["trace_id"],
                    "tenant_id": item["tenant_id"],
                    "reason": item["reason"],
                    "status": item["status"],
                    "created_at": current_time,
                },
            )
            inserted += int(getattr(result, "rowcount", 0) or 0)
        await session.commit()

    return {"status": "ok", "matched": len(candidates), "inserted": inserted}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--tenant", default="all")
    args = parser.parse_args()

    result = await run_once(days=args.days, tenant=args.tenant)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

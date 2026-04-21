# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite_trace
from db.engine import async_session
from db.models import EvalResult
from evaluation.drift import detect_drift
from evaluation.ragas_eval import answer_relevancy, context_precision, faithfulness

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 50
MIN_SAMPLE_SIZE = 10
BASELINE_DAYS = 7
DRIFT_THRESHOLD = 0.10


async def sample_traces(
    session: Any,
    since: datetime,
    n: int,
) -> list[dict[str, Any]]:
    _ = session
    sampled: list[dict[str, Any]] = []

    with sqlite_trace._get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT trace_id
            FROM traces
            WHERE finished_at IS NOT NULL
              AND final_route = 'auto'
              AND started_at >= ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (since.isoformat(), n),
        )
        trace_ids = [row[0] for row in cur.fetchall()]

        for trace_id in trace_ids:
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
            sampled.append(
                {
                    "trace_id": trace_id,
                    "question": state.get("question", ""),
                    "answer": state.get("answer", ""),
                    "context_docs": state.get("graded_docs") or state.get("context_docs") or [],
                }
            )

    return sampled


async def evaluate_traces(traces: list[dict[str, Any]]) -> dict[str, float]:
    if not traces:
        return {
            "faithfulness": 0.0,
            "context_precision": 0.0,
            "answer_relevancy": 0.0,
        }

    totals = {
        "faithfulness": 0.0,
        "context_precision": 0.0,
        "answer_relevancy": 0.0,
    }

    for trace in traces:
        question = str(trace.get("question", ""))
        answer = str(trace.get("answer", ""))
        context_docs = trace.get("context_docs") or []
        totals["faithfulness"] += faithfulness(answer, context_docs)
        totals["context_precision"] += context_precision(question, context_docs)
        totals["answer_relevancy"] += answer_relevancy(question, answer)

    sample_size = len(traces)
    return {
        metric_name: round(total / sample_size, 4)
        for metric_name, total in totals.items()
    }


async def get_baseline(
    session: Any,
    metric_name: str,
    days: int = BASELINE_DAYS,
    now: datetime | None = None,
) -> float | None:
    current_time = now or datetime.now(timezone.utc)
    window_start = current_time - timedelta(days=days)
    stmt = (
        select(func.avg(EvalResult.value))
        .where(EvalResult.metric_name == metric_name)
        .where(EvalResult.created_at >= window_start)
        .where(EvalResult.created_at < current_time)
    )
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    if value is None:
        return None
    return float(value)


async def run_once(
    session_factory: Any = async_session,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    since = current_time - timedelta(hours=24)

    async with session_factory() as session:
        traces = await sample_traces(session, since, SAMPLE_SIZE)
        sample_size = len(traces)
        if sample_size < MIN_SAMPLE_SIZE:
            logger.warning("Too few traces for nightly eval: %d", sample_size)
            return {"status": "skipped", "sample_size": sample_size}

        results = await evaluate_traces(traces)
        baselines = {
            metric_name: await get_baseline(session, metric_name, BASELINE_DAYS, current_time)
            for metric_name in results
        }
        drift_summary = detect_drift(results, baselines, threshold=DRIFT_THRESHOLD)

        for metric_name, value in results.items():
            session.add(
                EvalResult(
                    metric_name=metric_name,
                    value=value,
                    sample_size=sample_size,
                    drift_alert=bool(drift_summary[metric_name]["alert"]),
                )
            )

        await session.commit()
        return {
            "status": "ok",
            "sample_size": sample_size,
            "results": results,
            "drift": {
                metric_name: drift_summary[metric_name]["drift"]
                for metric_name in drift_summary
            },
        }


async def main() -> int:
    result = await run_once()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

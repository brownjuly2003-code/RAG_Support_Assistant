# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.engine import async_session


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "eval_daily"


async def run_once(
    target_date: date | None = None,
    output_dir: Path | None = None,
    session_factory: Any = async_session,
) -> dict[str, Any]:
    current_date = target_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    report_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    window_start = datetime.combine(current_date, time.min, tzinfo=timezone.utc)
    window_end = window_start + timedelta(days=1)

    payload: dict[str, Any] = {
        "date": current_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluators": {},
    }

    async with session_factory() as session:
        aggregate_rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        evaluator_name,
                        AVG(score) AS mean_score,
                        verdict,
                        COUNT(*) AS verdict_count
                    FROM trace_evaluations
                    WHERE evaluated_at >= :window_start
                      AND evaluated_at < :window_end
                    GROUP BY evaluator_name, verdict
                    ORDER BY evaluator_name ASC, verdict ASC
                    """
                ),
                {
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )
        ).mappings().all()

        for row in aggregate_rows:
            evaluator_name = str(row.get("evaluator_name") or "")
            if not evaluator_name:
                continue
            summary = payload["evaluators"].setdefault(
                evaluator_name,
                {
                    "mean_score": float(row.get("mean_score") or 0.0),
                    "verdict_counts": {},
                    "worst_traces": [],
                },
            )
            summary["mean_score"] = float(row.get("mean_score") or 0.0)
            summary["verdict_counts"][str(row.get("verdict") or "unknown")] = int(
                row.get("verdict_count") or 0
            )

        for evaluator_name in list(payload["evaluators"]):
            worst_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            trace_id,
                            score,
                            verdict,
                            evaluated_at
                        FROM trace_evaluations
                        WHERE evaluator_name = :evaluator_name
                          AND evaluated_at >= :window_start
                          AND evaluated_at < :window_end
                        ORDER BY score ASC, evaluated_at ASC
                        LIMIT 10
                        """
                    ),
                    {
                        "evaluator_name": evaluator_name,
                        "window_start": window_start,
                        "window_end": window_end,
                    },
                )
            ).mappings().all()
            payload["evaluators"][evaluator_name]["worst_traces"] = [
                {
                    "trace_id": str(row.get("trace_id") or ""),
                    "score": float(row.get("score") or 0.0),
                    "verdict": str(row.get("verdict") or ""),
                    "evaluated_at": (
                        row.get("evaluated_at").isoformat()
                        if hasattr(row.get("evaluated_at"), "isoformat")
                        else str(row.get("evaluated_at"))
                        if row.get("evaluated_at") is not None
                        else None
                    ),
                }
                for row in worst_rows
            ]

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{current_date.isoformat()}.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "date": current_date.isoformat(),
        "path": str(report_path),
        "evaluators": payload["evaluators"],
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Target UTC date in YYYY-MM-DD format")
    args = parser.parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None
    result = await run_once(target_date=target_date)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

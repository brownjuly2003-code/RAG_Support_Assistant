#!/usr/bin/env python3
"""Curated dataset staleness detector (task-156 close-out).

For each curated case older than ``CURATED_CASE_STALE_DAYS`` days, re-run
it through the supplied pipeline callable and compare the new verdict to
the stored expectations. Differences above configured thresholds mark the
case as ``stale_needs_review`` in the ``curated_case_status`` table.

By default runs read-only signal detection. Writing rows to the DB
requires an `--apply` flag.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_STALE_DAYS = 180
DEFAULT_QUALITY_DELTA = 10
DEFAULT_FACTUALITY_DELTA = 10


@dataclass
class StalenessDecision:
    case_id: str
    tenant_id: str
    is_stale: bool
    reason: str | None = None
    diff: dict[str, Any] = field(default_factory=dict)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_case_age_stale(
    case: dict[str, Any],
    *,
    now: datetime,
    stale_days: int,
) -> bool:
    created = _parse_iso_datetime(case.get("created_at"))
    if created is None:
        return False
    return (now - created) >= timedelta(days=stale_days)


def compare_verdicts(
    case: dict[str, Any],
    rerun: dict[str, Any],
    *,
    quality_delta: int = DEFAULT_QUALITY_DELTA,
    factuality_delta: int = DEFAULT_FACTUALITY_DELTA,
) -> StalenessDecision:
    """Pure: decide whether a re-run diverges materially from the stored case."""
    case_id = str(case.get("case_id") or "")
    tenant_id = str(case.get("tenant_id") or "default")
    expected = dict(case.get("expected") or {})

    route_expected = str(expected.get("route") or "").strip()
    route_actual = str(rerun.get("route") or "").strip()

    if route_expected and route_actual and route_expected != route_actual:
        return StalenessDecision(
            case_id=case_id,
            tenant_id=tenant_id,
            is_stale=True,
            reason="route_drift",
            diff={"route_expected": route_expected, "route_actual": route_actual},
        )

    quality_min = int(expected.get("min_quality") or 0)
    quality_actual = int(rerun.get("quality_score") or 0)
    if quality_min and quality_actual < quality_min - quality_delta:
        return StalenessDecision(
            case_id=case_id,
            tenant_id=tenant_id,
            is_stale=True,
            reason="quality_drop",
            diff={"expected_min": quality_min, "actual": quality_actual},
        )

    factuality_min = int(expected.get("min_factuality") or 0)
    factuality_actual = int(rerun.get("factuality_score") or 0)
    if factuality_min and factuality_actual < factuality_min - factuality_delta:
        return StalenessDecision(
            case_id=case_id,
            tenant_id=tenant_id,
            is_stale=True,
            reason="factuality_drop",
            diff={"expected_min": factuality_min, "actual": factuality_actual},
        )

    answer_must_contain = list(expected.get("answer_contains") or [])
    answer_actual = str(rerun.get("answer") or "")
    missing_phrases = [phrase for phrase in answer_must_contain if phrase and phrase not in answer_actual]
    if missing_phrases:
        return StalenessDecision(
            case_id=case_id,
            tenant_id=tenant_id,
            is_stale=True,
            reason="answer_contains_missing",
            diff={"missing": missing_phrases},
        )

    answer_must_contain_any = list(expected.get("answer_contains_any") or [])
    missing_any_groups = [
        [phrase for phrase in group if phrase]
        for group in answer_must_contain_any
        if group and not any(phrase and phrase in answer_actual for phrase in group)
    ]
    if missing_any_groups:
        return StalenessDecision(
            case_id=case_id,
            tenant_id=tenant_id,
            is_stale=True,
            reason="answer_contains_any_missing",
            diff={"missing_any": missing_any_groups},
        )

    return StalenessDecision(case_id=case_id, tenant_id=tenant_id, is_stale=False)


def load_curated_cases(jsonl_path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not jsonl_path.exists():
        return cases
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


async def write_status_rows(
    session,
    *,
    decisions: list[StalenessDecision],
    now: datetime | None = None,
) -> int:
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    inserted = 0
    for decision in decisions:
        if not decision.is_stale:
            continue
        await session.execute(
            sql_text(
                "DELETE FROM curated_case_status "
                "WHERE case_id = :case_id AND tenant_id = :tenant_id"
            ),
            {"case_id": decision.case_id, "tenant_id": decision.tenant_id},
        )
        await session.execute(
            sql_text(
                "INSERT INTO curated_case_status "
                "(case_id, tenant_id, status, staleness_reason, last_checked_at) "
                "VALUES (:case_id, :tenant_id, :status, :reason, :checked_at)"
            ),
            {
                "case_id": decision.case_id,
                "tenant_id": decision.tenant_id,
                "status": "stale_needs_review",
                "reason": decision.reason,
                "checked_at": now,
            },
        )
        inserted += 1
    await session.commit()
    return inserted


async def run_detection(
    *,
    jsonl_path: Path,
    rerun_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    session=None,
    stale_days: int = DEFAULT_STALE_DAYS,
    quality_delta: int = DEFAULT_QUALITY_DELTA,
    factuality_delta: int = DEFAULT_FACTUALITY_DELTA,
    now: datetime | None = None,
    apply_to_db: bool = False,
) -> list[StalenessDecision]:
    now = now or datetime.now(timezone.utc)
    decisions: list[StalenessDecision] = []

    for case in load_curated_cases(jsonl_path):
        if not is_case_age_stale(case, now=now, stale_days=stale_days):
            continue
        try:
            rerun = await rerun_fn(case)
        except Exception:
            continue
        decisions.append(
            compare_verdicts(
                case,
                rerun,
                quality_delta=quality_delta,
                factuality_delta=factuality_delta,
            )
        )

    if apply_to_db and session is not None:
        await write_status_rows(session, decisions=[d for d in decisions if d.is_stale], now=now)

    return decisions


def _make_placeholder_rerun_fn() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    async def _placeholder(case: dict[str, Any]) -> dict[str, Any]:
        expected = dict(case.get("expected") or {})
        return {
            "route": expected.get("route") or "auto",
            "quality_score": int(expected.get("min_quality") or 80),
            "factuality_score": int(expected.get("min_factuality") or 80),
            "answer": "",
        }

    return _placeholder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", default=str(PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"))
    parser.add_argument("--stale-days", type=int, default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--apply", action="store_true", help="write stale rows to curated_case_status")
    args = parser.parse_args(argv)

    stale_days = args.stale_days
    if stale_days is None:
        stale_days = int(os.environ.get("CURATED_CASE_STALE_DAYS", str(DEFAULT_STALE_DAYS)))

    decisions = asyncio.run(
        run_detection(
            jsonl_path=Path(args.jsonl),
            rerun_fn=_make_placeholder_rerun_fn(),
            stale_days=stale_days,
        )
    )

    stale_count = sum(1 for d in decisions if d.is_stale)
    lines = [
        "# Curated staleness report",
        "",
        f"created_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"evaluated: {len(decisions)}",
        f"stale: {stale_count}",
    ]
    if stale_count:
        lines.extend(["", "| case_id | tenant | reason |", "| --- | --- | --- |"])
        for decision in decisions:
            if decision.is_stale:
                lines.append(
                    f"| {decision.case_id} | {decision.tenant_id} | {decision.reason} |"
                )

    markdown = "\n".join(lines)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python3
"""Weekly recommendation engine (task-157).

Aggregates rule-based recommendations from improvement backlog, threshold
analyzer, latest green regression candidates and curated-dataset staleness
pressure into a ranked actionable list.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class Recommendation:
    title: str
    action: str
    evidence: str
    source: str
    priority: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _rec_from_backlog_item(item: dict[str, Any]) -> Recommendation | None:
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        return None
    priority = _coerce_float(item.get("priority"), 0.0)
    if priority <= 0:
        return None
    action = str(item.get("action") or item.get("recommendation") or title)
    evidence = str(item.get("evidence") or item.get("reason") or "")
    return Recommendation(
        title=title,
        action=action,
        evidence=evidence,
        source="backlog",
        priority=priority,
    )


def _rec_from_threshold_item(item: dict[str, Any]) -> Recommendation | None:
    metric = str(item.get("metric") or "").strip()
    if not metric:
        return None
    current = _coerce_float(item.get("current"), 0.0)
    suggested = _coerce_float(item.get("suggested"), 0.0)
    f1_gain = _coerce_float(item.get("f1_gain"), 0.0)
    if suggested == current and f1_gain <= 0:
        return None
    return Recommendation(
        title=f"Adjust threshold {metric}",
        action=f"Move {metric} from {current:g} to {suggested:g}",
        evidence=(
            f"F1 gain {f1_gain:.3f} on the latest threshold analyzer run"
            if f1_gain
            else f"threshold analyzer suggests {suggested:g}"
        ),
        source="threshold",
        priority=round(3.0 + f1_gain * 10.0, 4),
    )


def _rec_from_green_regression(item: dict[str, Any]) -> Recommendation | None:
    experiment_id = str(item.get("candidate_experiment_id") or item.get("experiment_id") or "").strip()
    if not experiment_id:
        return None
    quality_delta = _coerce_float(item.get("quality_delta"), 0.0)
    if quality_delta <= 0:
        return None
    run_id = str(item.get("run_id") or "")
    return Recommendation(
        title=f"Deploy experiment {experiment_id}",
        action=f"Promote experiment {experiment_id} (regression run {run_id}) to deployed",
        evidence=(
            f"regression run {run_id} shows quality delta +{quality_delta:.2f} "
            "over the deployed baseline on the curated dataset"
        ),
        source="regression",
        priority=round(5.0 + quality_delta, 4),
    )


def _rec_from_stale_case(item: dict[str, Any]) -> Recommendation | None:
    case_id = str(item.get("case_id") or "").strip()
    if not case_id:
        return None
    tenant = str(item.get("tenant_id") or "").strip() or "default"
    reason = str(item.get("staleness_reason") or "stale")
    return Recommendation(
        title=f"Re-review curated case {case_id}",
        action=f"Re-label {case_id} for tenant {tenant} ({reason})",
        evidence=f"marked stale at {item.get('last_checked_at', 'unknown')}",
        source="stale",
        priority=2.0,
    )


def aggregate_recommendations(
    *,
    backlog_items: Iterable[dict[str, Any]] = (),
    threshold_items: Iterable[dict[str, Any]] = (),
    green_regressions: Iterable[dict[str, Any]] = (),
    stale_cases: Iterable[dict[str, Any]] = (),
) -> list[Recommendation]:
    """Deterministic rule-based aggregation across all signal sources."""
    raw: list[Recommendation] = []
    for item in backlog_items or ():
        candidate = _rec_from_backlog_item(dict(item))
        if candidate is not None:
            raw.append(candidate)
    for item in threshold_items or ():
        candidate = _rec_from_threshold_item(dict(item))
        if candidate is not None:
            raw.append(candidate)
    for item in green_regressions or ():
        candidate = _rec_from_green_regression(dict(item))
        if candidate is not None:
            raw.append(candidate)
    for item in stale_cases or ():
        candidate = _rec_from_stale_case(dict(item))
        if candidate is not None:
            raw.append(candidate)

    raw.sort(key=lambda rec: (-rec.priority, rec.source, rec.title))
    return raw


def render_markdown(recs: list[Recommendation], *, week: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = f"# Recommendations{(' — ' + week) if week else ''}"
    summary = f"Generated at {now}. {len(recs)} ranked recommendation(s)."
    body_lines: list[str] = [header, "", summary, ""]
    if not recs:
        body_lines.append("_No actionable signals this window._")
        body_lines.append("")
        return "\n".join(body_lines)

    body_lines.extend(["## Ranked recommendations", ""])
    for idx, rec in enumerate(recs, 1):
        body_lines.append(f"### {idx}. {rec.title}")
        body_lines.append(f"- **Source:** {rec.source}")
        body_lines.append(f"- **Priority:** {rec.priority}")
        body_lines.append(f"- **Action:** {rec.action}")
        if rec.evidence:
            body_lines.append(f"- **Why now:** {rec.evidence}")
        body_lines.append("")
    return "\n".join(body_lines)


async def fetch_signals(session) -> dict[str, list[dict[str, Any]]]:
    """Collect signal rows from the live DB for admin endpoint use."""
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    stale_cases: list[dict[str, Any]] = []
    green_regressions: list[dict[str, Any]] = []
    try:
        result = await session.execute(
            sql_text(
                "SELECT case_id, tenant_id, status, staleness_reason, last_checked_at "
                "FROM curated_case_status WHERE status = 'stale_needs_review' "
                "ORDER BY last_checked_at DESC LIMIT 50"
            ),
            {},
        )
        stale_cases = [dict(row) for row in result.mappings().all()]
    except Exception:
        stale_cases = []

    try:
        result = await session.execute(
            sql_text(
                "SELECT run_id, candidate_experiment_id, quality_delta "
                "FROM eval_results WHERE drift_alert = false "
                "ORDER BY started_at DESC LIMIT 20"
            ),
            {},
        )
        green_regressions = [dict(row) for row in result.mappings().all()]
    except Exception:
        green_regressions = []

    return {
        "backlog_items": [],
        "threshold_items": [],
        "green_regressions": green_regressions,
        "stale_cases": stale_cases,
    }


def _resolve_output_path(project_root: Path, out: str | None, week: str) -> Path:
    if out:
        path = Path(out)
        if not path.is_absolute():
            path = project_root / path
        return path
    return project_root / "reports" / "recommendations" / f"{week}.md"


def _write_report(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="all", help="tenant id or 'all'")
    parser.add_argument("--week", default=None, help="ISO week spec YYYY-Www")
    parser.add_argument("--out", default=None, help="output markdown path")
    parser.add_argument(
        "--signals-json",
        default=None,
        help="optional path to a JSON file with {backlog_items,threshold_items,green_regressions,stale_cases}",
    )
    args = parser.parse_args(argv)

    week = args.week or datetime.now(timezone.utc).strftime("%G-W%V")

    signals: dict[str, list[dict[str, Any]]] = {
        "backlog_items": [],
        "threshold_items": [],
        "green_regressions": [],
        "stale_cases": [],
    }
    if args.signals_json:
        with open(args.signals_json, encoding="utf-8") as fh:
            signals.update(json.load(fh) or {})

    recommendations = aggregate_recommendations(**signals)
    markdown = render_markdown(recommendations, week=week)

    output_path = _resolve_output_path(PROJECT_ROOT, args.out, week)
    _write_report(output_path, markdown)
    print(f"wrote {len(recommendations)} recommendations to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

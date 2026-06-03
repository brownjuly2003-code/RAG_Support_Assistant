# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Sequence

from sklearn.metrics import f1_score, precision_recall_curve
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from db.engine import async_session

THRESHOLD_SPECS = (
    {
        "name": "quality_threshold",
        "field": "final_quality",
        "current_attr": "quality_threshold",
        "env_var": "QUALITY_THRESHOLD",
        "higher_is_bad": False,
        "value_type": "int",
    },
    {
        "name": "fact_verification_min_score",
        "field": "fact_score",
        "current_attr": "fact_verification_min_score",
        "env_var": "FACT_VERIFICATION_MIN_SCORE",
        "higher_is_bad": False,
        "value_type": "int",
    },
    {
        "name": "escalation_threshold",
        "field": "final_relevance",
        "current_attr": "escalation_threshold",
        "env_var": "ESCALATION_THRESHOLD",
        "higher_is_bad": False,
        "value_type": "float",
    },
    {
        "name": "slow_trace_threshold_ms",
        "field": "duration_ms",
        "current_attr": "slow_trace_threshold_ms",
        "env_var": "SLOW_TRACE_THRESHOLD_MS",
        "higher_is_bad": True,
        "value_type": "int",
    },
)


def _chunked(items: Sequence[str], size: int = 500) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield list(items[index:index + size])


def _parse_state_blob(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _format_value(value: float | int | None, value_type: str | None = None) -> str:
    if value is None:
        return "n/a"
    if value_type == "int":
        return str(int(round(float(value))))
    if value_type == "float":
        formatted = f"{float(value):.2f}"
        return formatted.rstrip("0").rstrip(".")
    if float(value).is_integer():
        return str(int(value))
    formatted = f"{float(value):.2f}"
    return formatted.rstrip("0").rstrip(".")


def _normalize_value(value: float | int | None, value_type: str) -> float | int | None:
    if value is None:
        return None
    if value_type == "int":
        return int(round(float(value)))
    return round(float(value), 2)


def _format_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _candidate_step(values: Sequence[float], value_type: str) -> float:
    unique_values = sorted(set(values))
    if len(unique_values) < 2:
        return 1.0 if value_type == "int" else 0.01
    diffs = [
        unique_values[index + 1] - unique_values[index]
        for index in range(len(unique_values) - 1)
        if unique_values[index + 1] - unique_values[index] > 0
    ]
    if not diffs:
        return 1.0 if value_type == "int" else 0.01
    step = min(diffs)
    if value_type == "int":
        return max(1.0, round(step))
    return step


def _build_histogram(values: Sequence[float], value_type: str, bins: int = 8) -> str:
    numeric_values = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not numeric_values:
        return "no data"

    lower = min(numeric_values)
    upper = max(numeric_values)
    if math.isclose(lower, upper):
        return f"{_format_value(lower, value_type)} | #################### ({len(numeric_values)})"

    bucket_count = max(1, min(bins, len(set(numeric_values))))
    step = (upper - lower) / bucket_count
    counts = [0] * bucket_count
    edges: list[tuple[float, float]] = []
    for index in range(bucket_count):
        start = lower + (step * index)
        end = upper if index == bucket_count - 1 else lower + (step * (index + 1))
        edges.append((start, end))

    for value in numeric_values:
        offset = int((value - lower) / step) if step else 0
        bucket_index = min(bucket_count - 1, max(0, offset))
        counts[bucket_index] += 1

    max_count = max(counts) or 1
    lines: list[str] = []
    for index, count in enumerate(counts):
        start, end = edges[index]
        if value_type == "float":
            label = f"{start:.2f}-{end:.2f}"
        else:
            label = f"{int(round(start))}-{int(round(end))}"
        bar_width = max(1, round((count / max_count) * 20)) if count else 0
        lines.append(f"{label} | {'#' * bar_width} ({count})")
    return "\n".join(lines)


def _compute_percentiles(values: Sequence[float]) -> dict[str, int]:
    numeric_values = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not numeric_values:
        return {}

    def _percentile(percent: int) -> int:
        if len(numeric_values) == 1:
            return int(round(numeric_values[0]))
        rank = ((len(numeric_values) - 1) * percent) / 100
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return int(round(numeric_values[lower]))
        fraction = rank - lower
        interpolated = numeric_values[lower] + ((numeric_values[upper] - numeric_values[lower]) * fraction)
        return int(round(interpolated))

    return {
        "p50": _percentile(50),
        "p90": _percentile(90),
        "p95": _percentile(95),
        "p99": _percentile(99),
    }


def compute_binary_metrics(
    *,
    actual_bad: Sequence[bool],
    predicted_bad: Sequence[bool],
) -> dict[str, float]:
    actual = [bool(item) for item in actual_bad]
    predicted = [bool(item) for item in predicted_bad]

    true_positive = sum(1 for truth, guess in zip(actual, predicted, strict=True) if truth and guess)
    false_positive = sum(1 for truth, guess in zip(actual, predicted, strict=True) if not truth and guess)
    false_negative = sum(1 for truth, guess in zip(actual, predicted, strict=True) if truth and not guess)

    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
    f1 = float(f1_score(actual, predicted, zero_division=0)) if actual else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _predict_bad(score: float, threshold: float, higher_is_bad: bool) -> bool:
    if higher_is_bad:
        return score > threshold
    return score < threshold


def _threshold_candidates(
    *,
    samples: Sequence[tuple[float, bool]],
    current_value: float,
    higher_is_bad: bool,
    value_type: str,
) -> list[float]:
    values = [float(score) for score, _ in samples if math.isfinite(float(score))]
    candidates = {float(current_value)}
    if not values:
        return [float(current_value)]

    candidates.update(values)

    transformed = [value if higher_is_bad else -value for value in values]
    labels = [1 if label else 0 for _, label in samples]
    try:
        _precision, _recall, raw_thresholds = precision_recall_curve(labels, transformed)
        for raw_threshold in raw_thresholds:
            original = float(raw_threshold) if higher_is_bad else float(-raw_threshold)
            candidates.add(original)
    except Exception:
        pass

    step = _candidate_step(values, value_type)
    if higher_is_bad:
        candidates.add(min(values) - step)
    else:
        candidates.add(max(values) + step)

    return sorted(candidates)


def find_optimal_threshold(
    *,
    name: str,
    samples: Sequence[tuple[float, bool]],
    current_value: float,
    higher_is_bad: bool,
    min_labels: int,
    value_type: str | None = None,
) -> dict[str, Any]:
    kind = value_type or ("int" if isinstance(current_value, int) else "float")
    filtered_samples = [
        (float(score), bool(is_bad))
        for score, is_bad in samples
        if score is not None and math.isfinite(float(score))
    ]
    current_metrics = None
    if filtered_samples:
        current_predictions = [
            _predict_bad(score, float(current_value), higher_is_bad)
            for score, _ in filtered_samples
        ]
        current_metrics = compute_binary_metrics(
            actual_bad=[label for _, label in filtered_samples],
            predicted_bad=current_predictions,
        )

    if len(filtered_samples) < min_labels:
        return {
            "name": name,
            "status": "insufficient_data",
            "current": _normalize_value(current_value, kind),
            "suggested": None,
            "current_metrics": current_metrics,
            "suggested_metrics": None,
            "labeled_count": len(filtered_samples),
            "reason": f"insufficient labeled traces ({len(filtered_samples)} < {min_labels})",
        }

    best_threshold = float(current_value)
    best_metrics = current_metrics or {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    for candidate in _threshold_candidates(
        samples=filtered_samples,
        current_value=float(current_value),
        higher_is_bad=higher_is_bad,
        value_type=kind,
    ):
        predictions = [_predict_bad(score, candidate, higher_is_bad) for score, _ in filtered_samples]
        metrics = compute_binary_metrics(
            actual_bad=[label for _, label in filtered_samples],
            predicted_bad=predictions,
        )
        better_f1 = metrics["f1"] > best_metrics["f1"] + 1e-9
        same_f1 = math.isclose(metrics["f1"], best_metrics["f1"], abs_tol=1e-9)
        closer_to_current = abs(candidate - float(current_value)) < abs(best_threshold - float(current_value))
        if better_f1 or (same_f1 and closer_to_current):
            best_threshold = candidate
            best_metrics = metrics

    delta = best_threshold - float(current_value)
    if math.isclose(delta, 0.0, abs_tol=1e-9):
        note = "current value is already optimal on the labeled sample."
    elif higher_is_bad:
        note = "raising the threshold flags fewer traces; lowering flags more."
    elif delta > 0:
        note = "raising the threshold catches more potentially bad traces."
    else:
        note = "lowering the threshold is more selective while improving F1."

    return {
        "name": name,
        "status": "ok",
        "current": _normalize_value(current_value, kind),
        "suggested": _normalize_value(best_threshold, kind),
        "current_metrics": current_metrics,
        "suggested_metrics": best_metrics,
        "labeled_count": len(filtered_samples),
        "reason": "",
        "note": note,
    }


def _load_trace_rows(
    *,
    db_path: Path,
    days: int,
    tenant: str,
    now: datetime,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    cutoff = (now - timedelta(days=max(0, days))).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT trace_id, tenant_id, started_at, final_route, final_quality, final_relevance
            FROM traces
            WHERE started_at >= ?
        """
        params: list[Any] = [cutoff]
        if tenant != "all":
            query += " AND tenant_id = ?"
            params.append(tenant)
        query += " ORDER BY started_at DESC"
        trace_rows = conn.execute(query, tuple(params)).fetchall()
        if not trace_rows:
            return []

        trace_ids = [str(row["trace_id"]) for row in trace_rows]
        details: dict[str, dict[str, Any]] = {
            trace_id: {"fact_score": None, "duration_ms": None}
            for trace_id in trace_ids
        }
        for batch in _chunked(trace_ids):
            placeholders = ", ".join("?" for _ in batch)
            step_rows = conn.execute(
                f"""
                SELECT trace_id, state_json
                FROM trace_steps
                WHERE trace_id IN ({placeholders})
                ORDER BY trace_id ASC, step_order ASC, id ASC
                """,
                tuple(batch),
            ).fetchall()
            for row in step_rows:
                trace_id = str(row["trace_id"])
                state = _parse_state_blob(row["state_json"])
                raw_duration = state.get("duration_ms")
                try:
                    duration_ms = int(round(float(raw_duration))) if raw_duration is not None else None
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

        return [
            {
                "trace_id": str(row["trace_id"]),
                "tenant_id": str(row["tenant_id"] or "default"),
                "started_at": row["started_at"],
                "final_route": str(row["final_route"] or ""),
                "final_quality": (
                    float(row["final_quality"])
                    if row["final_quality"] is not None
                    else None
                ),
                "final_relevance": (
                    float(row["final_relevance"])
                    if row["final_relevance"] is not None
                    else None
                ),
                "fact_score": details[str(row["trace_id"])]["fact_score"],
                "duration_ms": details[str(row["trace_id"])]["duration_ms"],
            }
            for row in trace_rows
        ]


async def _load_review_rows(
    *,
    tenant: str,
    session_factory: Any,
) -> list[dict[str, Any]]:
    query = """
        SELECT trace_id, tenant_id, status, created_at
        FROM review_queue
        WHERE status IN ('confirmed_good', 'confirmed_bad')
    """
    params: dict[str, Any] = {}
    if tenant != "all":
        query += " AND tenant_id = :tenant_id"
        params["tenant_id"] = tenant
    query += " ORDER BY created_at DESC"

    try:
        async with session_factory() as session:
            rows = (await session.execute(text(query), params)).mappings().all()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _labels_from_review_rows(review_rows: Sequence[dict[str, Any]]) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    for row in review_rows:
        trace_id = str(row.get("trace_id") or "").strip()
        if not trace_id or trace_id in labels:
            continue
        status = str(row.get("status") or "")
        if status == "confirmed_bad":
            labels[trace_id] = True
        elif status == "confirmed_good":
            labels[trace_id] = False
    return labels


def _proxy_labels_from_traces(traces: Sequence[dict[str, Any]]) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    for trace in traces:
        trace_id = str(trace.get("trace_id") or "").strip()
        if not trace_id:
            continue
        labels[trace_id] = str(trace.get("final_route") or "") == "human"
    return labels


def _build_caveats(
    *,
    tenant: str,
    review_rows: Sequence[dict[str, Any]],
    label_source: str,
    traces: Sequence[dict[str, Any]],
) -> list[str]:
    caveats: list[str] = []
    if label_source == "proxy_route":
        caveats.append(
            "Human review_queue verdicts were unavailable; recommendations use proxy labels "
            "from traces with final_route == 'human'."
        )
        caveats.append(
            "escalated_tickets could not be joined back to trace_id in the current schema, "
            "so proxy labels rely on trace routing only."
        )

    if tenant == "all" and review_rows:
        bad_counts: dict[str, int] = {}
        total_bad = 0
        for row in review_rows:
            if row.get("status") != "confirmed_bad":
                continue
            tenant_id = str(row.get("tenant_id") or "default")
            bad_counts[tenant_id] = bad_counts.get(tenant_id, 0) + 1
            total_bad += 1
        if total_bad:
            dominant_tenant, dominant_bad = max(bad_counts.items(), key=lambda item: item[1])
            share = dominant_bad / total_bad
            if share >= 0.5:
                caveats.append(
                    f"Tenant {dominant_tenant} accounts for {share:.0%} of confirmed bad traces; "
                    "per-tenant thresholds may fit better."
                )

    if traces and not any(trace.get("duration_ms") is not None for trace in traces):
        caveats.append("No duration_ms values were found in trace snapshots for the selected window.")
    if traces and not any(trace.get("fact_score") is not None for trace in traces):
        caveats.append("No fact_score values were found in trace snapshots for the selected window.")

    return caveats


def render_report(analysis: dict[str, Any]) -> str:
    generated_at = str(analysis.get("generated_at") or "")
    report_date = generated_at[:10] or "unknown-date"
    label_source = str(analysis.get("label_source") or "proxy_route")
    label_count = int(analysis.get("label_count") or 0)
    label_phrase = "human-reviewed" if label_source == "human_review" else "proxy-labeled"

    lines = [
        f"# Threshold recommendations - {report_date}",
        "",
        (
            f"Based on {int(analysis.get('total_traces') or 0)} traces "
            f"(last {int(analysis.get('days') or 0)} days), {label_count} {label_phrase}."
        ),
        "",
    ]

    for spec in THRESHOLD_SPECS:
        item = (analysis.get("thresholds") or {}).get(spec["name"], {})
        lines.append(f"## {spec['name']}")
        lines.append(f"- Current: {_format_value(item.get('current'), spec['value_type'])}")
        if item.get("status") == "ok":
            current_metrics = item.get("current_metrics") or {}
            suggested_metrics = item.get("suggested_metrics") or {}
            lines.append(
                "- Suggested: "
                f"{_format_value(item.get('suggested'), spec['value_type'])} "
                f"(F1 {_format_metric(suggested_metrics.get('f1'))} vs current "
                f"F1 {_format_metric(current_metrics.get('f1'))})"
            )
            lines.append(
                "- Trade-off at suggested value: "
                f"precision {_format_metric(suggested_metrics.get('precision'))}, "
                f"recall {_format_metric(suggested_metrics.get('recall'))}"
            )
            if item.get("note"):
                lines.append(f"- Rationale: {item['note']}")
        else:
            lines.append("- Suggested: insufficient data")
            lines.append(f"- Detail: {item.get('reason') or 'insufficient labeled traces'}")

        percentiles = item.get("percentiles") or {}
        if percentiles:
            lines.append(
                "- Distribution: "
                f"p50={percentiles.get('p50')}, "
                f"p90={percentiles.get('p90')}, "
                f"p95={percentiles.get('p95')}, "
                f"p99={percentiles.get('p99')}"
            )

        lines.extend(
            [
                "- Distribution chart:",
                "```text",
                str(item.get("histogram") or "no data"),
                "```",
                "",
            ]
        )

    patch_lines = ["# copy to .env if accepting recommendation:"]
    for spec in THRESHOLD_SPECS:
        item = (analysis.get("thresholds") or {}).get(spec["name"], {})
        if item.get("status") == "ok" and item.get("suggested") is not None:
            patch_lines.append(f"{spec['env_var']}={_format_value(item['suggested'], spec['value_type'])}")

    lines.extend(["## YAML patch", "```yaml", *patch_lines, "```", ""])

    caveats = list(analysis.get("caveats") or [])
    lines.append("## Caveats")
    if caveats:
        lines.extend(f"- {item}" for item in caveats)
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


async def run_once(
    *,
    days: int,
    tenant: str,
    out: Path | str | None = None,
    session_factory: Any = async_session,
    settings: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    db_path = Path(getattr(active_settings, "tracing_db_path"))
    min_labels = int(getattr(active_settings, "threshold_analysis_min_labels", 20))

    traces = _load_trace_rows(
        db_path=db_path,
        days=days,
        tenant=tenant,
        now=current_time,
    )
    review_rows = await _load_review_rows(tenant=tenant, session_factory=session_factory)
    human_labels = _labels_from_review_rows(review_rows)
    label_source = "human_review" if human_labels else "proxy_route"
    labels = human_labels or _proxy_labels_from_traces(traces)

    thresholds: dict[str, Any] = {}
    for spec in THRESHOLD_SPECS:
        all_values = [
            float(trace[spec["field"]])
            for trace in traces
            if trace.get(spec["field"]) is not None
        ]
        labeled_samples = [
            (float(trace[spec["field"]]), labels[str(trace["trace_id"])])
            for trace in traces
            if trace.get(spec["field"]) is not None and str(trace["trace_id"]) in labels
        ]
        result = find_optimal_threshold(
            name=spec["name"],
            samples=labeled_samples,
            current_value=float(getattr(active_settings, spec["current_attr"])),
            higher_is_bad=bool(spec["higher_is_bad"]),
            min_labels=min_labels,
            value_type=spec["value_type"],
        )
        result["metric_count"] = len(all_values)
        result["histogram"] = _build_histogram(all_values, spec["value_type"])
        if spec["name"] == "slow_trace_threshold_ms":
            result["percentiles"] = _compute_percentiles(all_values)
        thresholds[spec["name"]] = result

    analysis = {
        "generated_at": current_time.isoformat(),
        "days": int(days),
        "tenant": tenant,
        "total_traces": len(traces),
        "label_count": len(labels),
        "label_source": label_source,
        "thresholds": thresholds,
        "caveats": _build_caveats(
            tenant=tenant,
            review_rows=review_rows,
            label_source=label_source,
            traces=traces,
        ),
        "report_path": str(Path(out).resolve()) if out is not None else None,
    }

    markdown = render_report(analysis)
    if out is not None:
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown)

    return analysis


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "reports" / "threshold_recommendations.md"),
    )
    args = parser.parse_args()

    result = await run_once(
        days=max(1, args.days),
        tenant=str(args.tenant or "all"),
        out=Path(args.out),
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

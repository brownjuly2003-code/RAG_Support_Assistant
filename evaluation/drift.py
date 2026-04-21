from __future__ import annotations

from typing import Mapping

from monitoring import prometheus as prometheus_metrics


def _relative_drift(current: float | None, baseline: float | None) -> float:
    if current is None or baseline in (None, 0):
        return 0.0
    return abs(current - baseline) / baseline


def detect_drift(
    current_metrics: Mapping[str, float],
    baseline_metrics: Mapping[str, float | None],
    threshold: float = 0.1,
) -> dict[str, dict[str, float | bool | None]]:
    summary: dict[str, dict[str, float | bool | None]] = {}

    for metric_name, current_value in current_metrics.items():
        baseline_value = baseline_metrics.get(metric_name)
        drift_value = _relative_drift(current_value, baseline_value)
        prometheus_metrics.record_eval_drift(metric_name, drift_value)
        summary[metric_name] = {
            "value": current_value,
            "baseline": baseline_value,
            "drift": drift_value,
            "alert": baseline_value not in (None, 0) and drift_value > threshold,
        }

    return summary

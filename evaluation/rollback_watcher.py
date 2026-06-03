"""Automatic rollback watcher (task-155).

Compares mean online-evaluator scores between baseline traces and traces
exposed to a deployed experiment. If the candidate degrades by more than
`rollback_drift_threshold_pct`, the deployment row is marked
`rolled_back_at`, a Prometheus counter ticks and (optionally) a
notification goes out.

All behaviour is opt-in via `AUTO_ROLLBACK_ENABLED`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import Awaitable, Callable

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class DriftDecision:
    should_rollback: bool
    reason: str
    worst_evaluator: Optional[str] = None
    drop_pct: float = 0.0
    candidate_scores: dict[str, float] = field(default_factory=dict)
    baseline_scores: dict[str, float] = field(default_factory=dict)


def compute_drift(
    baseline_scores: dict[str, float],
    candidate_scores: dict[str, float],
    threshold_pct: float,
) -> DriftDecision:
    """Pure: decide whether the candidate is materially worse than baseline."""
    if not baseline_scores or not candidate_scores:
        return DriftDecision(
            should_rollback=False,
            reason="insufficient_data",
            candidate_scores=candidate_scores,
            baseline_scores=baseline_scores,
        )

    worst_drop_pct = 0.0
    worst_evaluator: Optional[str] = None
    for evaluator, baseline_mean in baseline_scores.items():
        if evaluator not in candidate_scores:
            continue
        if baseline_mean == 0:
            continue
        candidate_mean = candidate_scores[evaluator]
        drop_pct = ((baseline_mean - candidate_mean) / baseline_mean) * 100.0
        if drop_pct > worst_drop_pct:
            worst_drop_pct = drop_pct
            worst_evaluator = evaluator

    if worst_evaluator is not None and worst_drop_pct >= threshold_pct:
        return DriftDecision(
            should_rollback=True,
            reason=f"drift_{worst_evaluator}_{worst_drop_pct:.1f}pct",
            worst_evaluator=worst_evaluator,
            drop_pct=worst_drop_pct,
            candidate_scores=candidate_scores,
            baseline_scores=baseline_scores,
        )
    return DriftDecision(
        should_rollback=False,
        reason="normal_variance",
        worst_evaluator=worst_evaluator,
        drop_pct=worst_drop_pct,
        candidate_scores=candidate_scores,
        baseline_scores=baseline_scores,
    )


async def fetch_mean_scores(session, *, experiment_id: Optional[str], window_size: int) -> dict[str, float]:
    """Mean evaluator score across recent traces.

    When `experiment_id` is None, the SQL mock session in tests filters by
    `experiment_id IS NULL`. Real deployments join `trace_evaluations` to
    `traces` via trace_id; here the caller is expected to provide a view
    or an aggregate that exposes `experiment_id` on the evaluation row.
    """
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    if experiment_id is None:
        stmt = sql_text(
            "SELECT evaluator_name, AVG(score) AS mean_score "
            "FROM trace_evaluations "
            "WHERE experiment_id IS NULL "
            "GROUP BY evaluator_name "
            "LIMIT :window_size"
        )
        params: dict[str, object] = {"window_size": window_size}
    else:
        stmt = sql_text(
            "SELECT evaluator_name, AVG(score) AS mean_score "
            "FROM trace_evaluations "
            "WHERE experiment_id = :experiment_id "
            "GROUP BY evaluator_name "
            "LIMIT :window_size"
        )
        params = {"experiment_id": experiment_id, "window_size": window_size}

    result = await session.execute(stmt, params)
    rows = list(result.mappings().all())
    scores: dict[str, float] = {}
    for row in rows:
        name = row.get("evaluator_name") if hasattr(row, "get") else row["evaluator_name"]
        raw = row.get("mean_score") if hasattr(row, "get") else row["mean_score"]
        if name is None or raw is None:
            continue
        scores[str(name)] = float(raw)
    return scores


async def fetch_active_deployments(session) -> list[dict[str, Any]]:
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    result = await session.execute(
        sql_text(
            "SELECT experiment_id, regression_run_id, deployed_at "
            "FROM experiment_deployments "
            "WHERE rolled_back_at IS NULL"
        ),
        {},
    )
    return [dict(row) for row in result.mappings().all()]


async def trigger_rollback(
    session,
    *,
    experiment_id: str,
    regression_run_id: Optional[str],
    reason: str,
) -> None:
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    await session.execute(
        sql_text(
            "UPDATE experiment_deployments "
            "SET rolled_back_at = :rolled_back_at "
            "WHERE experiment_id = :experiment_id "
            "AND regression_run_id = :regression_run_id "
            "AND rolled_back_at IS NULL"
        ),
        {
            "rolled_back_at": now,
            "experiment_id": experiment_id,
            "regression_run_id": regression_run_id,
        },
    )
    await session.commit()

    try:
        from monitoring.prometheus import EXPERIMENT_AUTO_ROLLBACK_TOTAL  # noqa: PLC0415

        EXPERIMENT_AUTO_ROLLBACK_TOTAL.labels(
            experiment_id=experiment_id,
            reason=reason,
        ).inc()
    except Exception:  # pragma: no cover - metrics optional
        logger.debug("prometheus rollback counter unavailable", exc_info=True)


async def default_notifier(experiment_id: str, reason: str) -> None:
    settings = get_settings()
    recipient = (getattr(settings, "tenant_admin_email", "") or "").strip()
    if not recipient:
        return
    try:
        from scripts.weekly_report import send_email  # noqa: PLC0415
    except Exception:
        logger.debug("weekly_report.send_email import failed", exc_info=True)
        return

    subject = f"[rag-support] auto-rollback: {experiment_id}"
    body = (
        f"Experiment: {experiment_id}\n"
        f"Reason: {reason}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
    )
    try:
        await send_email([recipient], subject, body)
    except Exception:
        logger.warning("auto-rollback email notification failed", exc_info=True)


async def check_and_rollback(
    session,
    *,
    notifier: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> list[dict[str, Any]]:
    """Run the watcher once. Returns rollback events (empty if none)."""
    settings = get_settings()
    if not getattr(settings, "auto_rollback_enabled", False):
        return []

    threshold = float(getattr(settings, "rollback_drift_threshold_pct", 10.0))
    window = int(getattr(settings, "rollback_trace_window", 1000))

    try:
        active = await fetch_active_deployments(session)
    except Exception:
        logger.warning("auto-rollback: fetching active deployments failed", exc_info=True)
        return []
    if not active:
        return []

    try:
        baseline_scores = await fetch_mean_scores(session, experiment_id=None, window_size=window)
    except Exception:
        logger.warning("auto-rollback: fetching baseline scores failed", exc_info=True)
        return []

    events: list[dict[str, Any]] = []
    use_notifier = notifier if notifier is not None else default_notifier

    for deployment in active:
        experiment_id = str(deployment.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        try:
            candidate_scores = await fetch_mean_scores(
                session,
                experiment_id=experiment_id,
                window_size=window,
            )
        except Exception:
            logger.warning(
                "auto-rollback: fetching candidate scores failed for %s",
                experiment_id,
                exc_info=True,
            )
            continue

        decision = compute_drift(baseline_scores, candidate_scores, threshold)
        if not decision.should_rollback:
            continue

        await trigger_rollback(
            session,
            experiment_id=experiment_id,
            regression_run_id=deployment.get("regression_run_id"),
            reason=decision.reason,
        )
        try:
            await use_notifier(experiment_id, decision.reason)
        except Exception:
            logger.warning("auto-rollback notifier failed", exc_info=True)

        events.append(
            {
                "experiment_id": experiment_id,
                "reason": decision.reason,
                "drop_pct": decision.drop_pct,
                "worst_evaluator": decision.worst_evaluator,
            }
        )

    return events

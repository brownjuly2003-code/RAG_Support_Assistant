from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation import rollback_watcher


class _AsyncMappingResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_AsyncMappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)


class _WatcherSession:
    def __init__(
        self,
        *,
        active_deployments: list[dict[str, object]] | None = None,
        baseline_scores: list[dict[str, object]] | None = None,
        candidate_scores_by_experiment: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.active_deployments = list(active_deployments or [])
        self.baseline_scores = list(baseline_scores or [])
        self.candidate_scores_by_experiment = dict(candidate_scores_by_experiment or {})
        self.deployment_updates: list[dict[str, object]] = []
        self.commits = 0

    async def __aenter__(self) -> "_WatcherSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _AsyncMappingResult:
        sql = " ".join(str(statement).split()).upper()
        values = dict(params or {})

        if sql.startswith("SELECT") and "FROM EXPERIMENT_DEPLOYMENTS" in sql:
            rows = [row for row in self.active_deployments if row.get("rolled_back_at") is None]
            return _AsyncMappingResult(rows)

        if sql.startswith("UPDATE EXPERIMENT_DEPLOYMENTS"):
            self.deployment_updates.append(values)
            for row in self.active_deployments:
                if row.get("experiment_id") != values.get("experiment_id"):
                    continue
                if row.get("regression_run_id") != values.get("regression_run_id"):
                    continue
                row["rolled_back_at"] = values.get("rolled_back_at")
            return _AsyncMappingResult()

        if sql.startswith("SELECT") and "FROM TRACE_EVALUATIONS" in sql:
            if "EXPERIMENT_ID IS NULL" in sql:
                return _AsyncMappingResult(self.baseline_scores)
            experiment_id = values.get("experiment_id")
            rows = self.candidate_scores_by_experiment.get(str(experiment_id), [])
            return _AsyncMappingResult(rows)

        raise AssertionError(f"Unexpected SQL: {statement}")

    async def commit(self) -> None:
        self.commits += 1


def test_compute_drift_triggers_above_threshold() -> None:
    baseline = {"citation_coverage": 0.9, "factuality": 0.8}
    candidate = {"citation_coverage": 0.9, "factuality": 0.65}

    decision = rollback_watcher.compute_drift(baseline, candidate, threshold_pct=10.0)

    assert decision.should_rollback is True
    assert decision.worst_evaluator == "factuality"
    assert decision.drop_pct > 10.0


def test_compute_drift_ignores_normal_variance() -> None:
    baseline = {"citation_coverage": 0.9, "factuality": 0.8}
    candidate = {"citation_coverage": 0.89, "factuality": 0.78}

    decision = rollback_watcher.compute_drift(baseline, candidate, threshold_pct=10.0)

    assert decision.should_rollback is False
    assert decision.reason == "normal_variance"


def test_compute_drift_insufficient_data_is_safe() -> None:
    decision = rollback_watcher.compute_drift({}, {"a": 0.5}, threshold_pct=10.0)
    assert decision.should_rollback is False
    assert decision.reason == "insufficient_data"


@pytest.mark.asyncio
async def test_check_and_rollback_marks_deployment_and_calls_notifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = rollback_watcher.get_settings()
    monkeypatch.setattr(settings, "auto_rollback_enabled", True, raising=False)
    monkeypatch.setattr(settings, "rollback_drift_threshold_pct", 10.0, raising=False)
    monkeypatch.setattr(settings, "rollback_trace_window", 500, raising=False)

    session = _WatcherSession(
        active_deployments=[
            {
                "experiment_id": "exp-bad",
                "regression_run_id": "reg-1",
                "rolled_back_at": None,
            }
        ],
        baseline_scores=[
            {"evaluator_name": "factuality", "mean_score": 0.9},
            {"evaluator_name": "citation_coverage", "mean_score": 0.85},
        ],
        candidate_scores_by_experiment={
            "exp-bad": [
                {"evaluator_name": "factuality", "mean_score": 0.5},
                {"evaluator_name": "citation_coverage", "mean_score": 0.85},
            ]
        },
    )

    notifications: list[tuple[str, str]] = []

    async def _capture(experiment_id: str, reason: str) -> None:
        notifications.append((experiment_id, reason))

    events = await rollback_watcher.check_and_rollback(session, notifier=_capture)

    assert len(events) == 1
    assert events[0]["experiment_id"] == "exp-bad"
    assert events[0]["worst_evaluator"] == "factuality"
    assert notifications == [("exp-bad", events[0]["reason"])]
    assert session.deployment_updates[0]["rolled_back_at"] is not None
    assert session.active_deployments[0]["rolled_back_at"] is not None


@pytest.mark.asyncio
async def test_check_and_rollback_respects_feature_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = rollback_watcher.get_settings()
    monkeypatch.setattr(settings, "auto_rollback_enabled", False, raising=False)

    session = _WatcherSession(
        active_deployments=[
            {"experiment_id": "exp-any", "regression_run_id": "reg-1", "rolled_back_at": None}
        ]
    )

    events = await rollback_watcher.check_and_rollback(session)

    assert events == []
    assert session.deployment_updates == []


@pytest.mark.asyncio
async def test_check_and_rollback_skips_when_no_active_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = rollback_watcher.get_settings()
    monkeypatch.setattr(settings, "auto_rollback_enabled", True, raising=False)

    session = _WatcherSession(active_deployments=[])

    events = await rollback_watcher.check_and_rollback(session)

    assert events == []


@pytest.mark.asyncio
async def test_check_and_rollback_does_not_touch_already_rolled_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = rollback_watcher.get_settings()
    monkeypatch.setattr(settings, "auto_rollback_enabled", True, raising=False)

    from datetime import datetime, timezone

    session = _WatcherSession(
        active_deployments=[
            {
                "experiment_id": "exp-done",
                "regression_run_id": "reg-1",
                "rolled_back_at": datetime.now(timezone.utc),
            }
        ],
        baseline_scores=[{"evaluator_name": "factuality", "mean_score": 0.9}],
        candidate_scores_by_experiment={
            "exp-done": [{"evaluator_name": "factuality", "mean_score": 0.1}]
        },
    )

    events = await rollback_watcher.check_and_rollback(session)

    assert events == []
    assert session.deployment_updates == []


@pytest.mark.asyncio
async def test_trigger_rollback_increments_metric() -> None:
    from monitoring.prometheus import EXPERIMENT_AUTO_ROLLBACK_TOTAL

    before = EXPERIMENT_AUTO_ROLLBACK_TOTAL.labels(
        experiment_id="exp-metric",
        reason="drift_factuality_20.0pct",
    )._value.get()

    session = _WatcherSession(
        active_deployments=[
            {
                "experiment_id": "exp-metric",
                "regression_run_id": "reg-metric",
                "rolled_back_at": None,
            }
        ]
    )

    await rollback_watcher.trigger_rollback(
        session,
        experiment_id="exp-metric",
        regression_run_id="reg-metric",
        reason="drift_factuality_20.0pct",
    )

    after = EXPERIMENT_AUTO_ROLLBACK_TOTAL.labels(
        experiment_id="exp-metric",
        reason="drift_factuality_20.0pct",
    )._value.get()

    assert after == before + 1

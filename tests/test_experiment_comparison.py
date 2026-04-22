from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.jwt_handler import create_access_token

ADMIN_HEADERS = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


def _write_experiment(project_root: Path, experiment_id: str) -> Path:
    experiments_dir = project_root / "evaluation" / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{experiment_id}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": experiment_id,
                "name": "test",
                "created_at": "2026-04-22T00:00:00+00:00",
                "created_by": "system",
                "description": "comparison test",
                "prompt_overrides": {},
                "settings_overrides": {},
                "parent_experiment_id": None,
                "status": "draft",
                "tags": [],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


class _AsyncMappingResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_AsyncMappingResult":
        return self

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _ComparisonSession:
    def __init__(
        self,
        *,
        trace_rows: dict[str, dict[str, object]] | None = None,
        regression_rows: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.trace_rows = dict(trace_rows or {})
        self.regression_rows = dict(regression_rows or {})

    async def __aenter__(self) -> "_ComparisonSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _AsyncMappingResult:
        sql = " ".join(str(statement).split()).upper()
        experiment_id = str((params or {}).get("experiment_id") or "")
        if "FROM TRACES" in sql:
            row = self.trace_rows.get(experiment_id)
            return _AsyncMappingResult([row] if row is not None else [])
        if "FROM EVAL_RESULTS" in sql:
            row = self.regression_rows.get(experiment_id)
            return _AsyncMappingResult([row] if row is not None else [])
        raise AssertionError(f"Unexpected SQL: {statement}")

    async def commit(self) -> None:
        return None


def test_comparison_endpoint_returns_three_buckets(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    candidate_id = "2026-04-22-candidate"
    _write_experiment(tmp_path, candidate_id)

    session = _ComparisonSession(
        trace_rows={
            "exp-deployed": {
                "trace_count": 120,
                "quality_mean": 82.5,
                "cost_mean": 0.0021,
                "latency_mean": 1450.0,
            }
        },
        regression_rows={
            "exp-staged": {
                "run_id": "reg-7",
                "quality_delta": 2.3,
                "cost_delta": -0.0001,
                "latency_delta": 30.0,
            }
        },
    )
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.get(
        "/api/admin/experiments/comparison",
        params={
            "deployed": "exp-deployed",
            "staged": "exp-staged",
            "candidate": candidate_id,
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployed"]["experiment_id"] == "exp-deployed"
    assert payload["deployed"]["trace_count"] == 120
    assert payload["deployed"]["quality"]["mean"] == pytest.approx(82.5)
    assert payload["deployed"]["cost_per_trace"] == pytest.approx(0.0021)

    assert payload["staged"]["experiment_id"] == "exp-staged"
    assert payload["staged"]["evaluator_breakdown"]["run_id"] == "reg-7"
    assert payload["staged"]["quality"]["mean"] == pytest.approx(2.3)

    assert payload["candidate"]["experiment_id"] == candidate_id
    assert payload["candidate"]["evaluator_breakdown"]["yaml_present"] is True


def test_comparison_endpoint_handles_empty_query(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    session = _ComparisonSession()
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.get(
        "/api/admin/experiments/comparison",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    for bucket in ("deployed", "staged", "candidate"):
        assert payload[bucket]["experiment_id"] is None
        assert payload[bucket]["trace_count"] == 0
        assert payload[bucket]["quality"]["mean"] is None


def test_comparison_endpoint_missing_live_data_still_serializes(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    session = _ComparisonSession(trace_rows={}, regression_rows={})
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.get(
        "/api/admin/experiments/comparison",
        params={"deployed": "unknown-exp", "staged": "unknown-staged"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployed"]["trace_count"] == 0
    assert payload["deployed"]["quality"]["mean"] is None
    assert payload["staged"]["evaluator_breakdown"] == {}


def test_admin_html_contains_experiment_comparison_surface() -> None:
    html = (Path(__file__).resolve().parent.parent / "static" / "admin.html").read_text(
        encoding="utf-8"
    )
    assert "tab-experiment-comparison" in html
    assert "experiment-comparison-output" in html
    assert "Experiment Comparison" in html

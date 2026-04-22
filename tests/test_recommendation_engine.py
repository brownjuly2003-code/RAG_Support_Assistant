from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.jwt_handler import create_access_token
from scripts import generate_recommendations

ADMIN_HEADERS = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


class _AsyncMappingResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_AsyncMappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)


class _RecommendationsSession:
    def __init__(
        self,
        *,
        stale_rows: list[dict[str, object]] | None = None,
        green_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.stale_rows = stale_rows or []
        self.green_rows = green_rows or []

    async def __aenter__(self) -> "_RecommendationsSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _AsyncMappingResult:
        sql = " ".join(str(statement).split()).upper()
        if "FROM CURATED_CASE_STATUS" in sql:
            return _AsyncMappingResult(self.stale_rows)
        if "FROM EVAL_RESULTS" in sql:
            return _AsyncMappingResult(self.green_rows)
        raise AssertionError(f"Unexpected SQL: {statement}")

    async def commit(self) -> None:
        return None


def test_aggregate_merges_multiple_signal_types() -> None:
    recs = generate_recommendations.aggregate_recommendations(
        backlog_items=[
            {"title": "Improve KB freshness", "priority": 6.5, "action": "Re-ingest stale pages"}
        ],
        threshold_items=[
            {"metric": "refusal_rate", "current": 0.1, "suggested": 0.15, "f1_gain": 0.05}
        ],
        green_regressions=[
            {
                "candidate_experiment_id": "2026-04-23-test",
                "run_id": "reg-42",
                "quality_delta": 3.5,
            }
        ],
        stale_cases=[
            {
                "case_id": "case-7",
                "tenant_id": "acme",
                "staleness_reason": "quality_drop",
                "last_checked_at": "2026-04-23T10:00:00+00:00",
            }
        ],
    )

    assert len(recs) == 4
    sources = {rec.source for rec in recs}
    assert sources == {"backlog", "threshold", "regression", "stale"}


def test_aggregate_ranking_is_deterministic() -> None:
    input_kwargs = dict(
        backlog_items=[{"title": "A", "priority": 6.0}, {"title": "B", "priority": 7.0}],
        threshold_items=[{"metric": "recall", "current": 0.7, "suggested": 0.8, "f1_gain": 0.05}],
        green_regressions=[
            {"candidate_experiment_id": "exp-2", "run_id": "r2", "quality_delta": 1.0}
        ],
        stale_cases=[],
    )
    first = generate_recommendations.aggregate_recommendations(**input_kwargs)
    second = generate_recommendations.aggregate_recommendations(**input_kwargs)

    assert [rec.to_dict() for rec in first] == [rec.to_dict() for rec in second]
    assert first[0].title == "B"


def test_aggregate_empty_returns_zero() -> None:
    assert generate_recommendations.aggregate_recommendations() == []


def test_render_markdown_includes_ranked_items() -> None:
    recs = generate_recommendations.aggregate_recommendations(
        backlog_items=[
            {"title": "Re-ingest KB", "priority": 8.0, "action": "Run ingestion", "evidence": "stale docs"}
        ],
    )
    markdown = generate_recommendations.render_markdown(recs, week="2026-W17")
    assert "# Recommendations — 2026-W17" in markdown
    assert "Re-ingest KB" in markdown
    assert "Priority:** 8.0" in markdown
    assert "Why now:** stale docs" in markdown


def test_render_markdown_handles_empty_list() -> None:
    markdown = generate_recommendations.render_markdown([], week="2026-W17")
    assert "# Recommendations — 2026-W17" in markdown
    assert "No actionable signals" in markdown


def test_admin_recommendations_current_endpoint_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    session = _RecommendationsSession(
        stale_rows=[
            {
                "case_id": "case-42",
                "tenant_id": "acme",
                "status": "stale_needs_review",
                "staleness_reason": "quality_drop",
                "last_checked_at": "2026-04-23T10:00:00+00:00",
            }
        ],
        green_rows=[
            {
                "run_id": "reg-42",
                "candidate_experiment_id": "2026-04-23-test",
                "quality_delta": 3.5,
            }
        ],
    )
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.get(
        "/api/admin/recommendations/current",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    titles = {rec["title"] for rec in payload["recommendations"]}
    assert "Deploy experiment 2026-04-23-test" in titles
    assert "Re-review curated case case-42" in titles


def test_admin_recommendations_disabled_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    fake_settings = type("S", (), {"recommendations_enabled": False})()
    monkeypatch.setattr(api_app, "get_settings", lambda: fake_settings)

    response = client_with_key.get(
        "/api/admin/recommendations/current",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendations"] == []
    assert payload["status"] == "disabled"

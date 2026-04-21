from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant: str = "default", role: str = "admin", user_id: str | None = None) -> dict[str, str]:
    subject = user_id or str(uuid.uuid4())
    return {"Authorization": f"Bearer {create_access_token(subject, role, tenant)}"}


def _init_trace_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE traces (
                trace_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                tenant_id TEXT NOT NULL,
                final_route TEXT,
                final_quality REAL,
                final_relevance REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                state_json TEXT,
                ts TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _insert_trace(
    db_path: Path,
    trace_id: str,
    *,
    tenant_id: str = "default",
    days_ago: int = 1,
    final_quality: float,
    final_relevance: float,
    fact_score: float,
    duration_ms: int,
) -> None:
    started_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    finished_at = datetime.now(timezone.utc).isoformat()
    state = {
        "duration_ms": duration_ms,
        "factuality_score": fact_score,
        "relevance_score": final_relevance,
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces (
                trace_id,
                started_at,
                finished_at,
                tenant_id,
                final_route,
                final_quality,
                final_relevance
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trace_id, started_at, finished_at, tenant_id, "auto", final_quality, final_relevance),
        )
        conn.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, 0, "evaluate", json.dumps(state), started_at),
        )
        conn.commit()


class _Result:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _ThresholdSession:
    def __init__(
        self,
        review_rows: list[dict[str, object]] | None = None,
        ticket_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.review_rows = review_rows or []
        self.ticket_rows = ticket_rows or []

    async def __aenter__(self) -> "_ThresholdSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        data = params or {}
        if "FROM review_queue" in sql:
            tenant_id = str(data["tenant_id"])
            return _Result(
                [
                    dict(row)
                    for row in self.review_rows
                    if row["tenant_id"] == tenant_id and row["status"] in {"confirmed_good", "confirmed_bad"}
                ]
            )
        if "FROM escalated_tickets" in sql:
            tenant_id = str(data["tenant_id"])
            return _Result(
                [dict(row) for row in self.ticket_rows if row["tenant_id"] == tenant_id]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_find_optimal_threshold_on_synthetic_scores() -> None:
    from scripts import analyze_thresholds

    samples = [(float(score), score < 60) for score in range(100)]

    result = analyze_thresholds.find_optimal_threshold(
        name="quality_threshold",
        samples=samples,
        current_value=80,
        higher_is_bad=False,
        min_labels=20,
    )

    assert result["status"] == "ok"
    assert result["suggested"] == 60
    assert result["suggested_metrics"]["f1"] == pytest.approx(1.0)
    assert result["current_metrics"]["f1"] < result["suggested_metrics"]["f1"]


def test_find_optimal_threshold_skips_when_labels_below_minimum() -> None:
    from scripts import analyze_thresholds

    result = analyze_thresholds.find_optimal_threshold(
        name="quality_threshold",
        samples=[(float(score), score < 5) for score in range(19)],
        current_value=80,
        higher_is_bad=False,
        min_labels=20,
    )

    assert result["status"] == "insufficient_data"
    assert result["suggested"] is None
    assert "insufficient" in result["reason"]


def test_compute_binary_metrics_matches_expected_f1() -> None:
    from scripts import analyze_thresholds

    metrics = analyze_thresholds.compute_binary_metrics(
        actual_bad=[True, True, False, False],
        predicted_bad=[True, False, True, False],
    )

    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)


def test_render_report_contains_sections_and_env_patch() -> None:
    from scripts import analyze_thresholds

    analysis = {
        "generated_at": "2026-04-21T12:00:00+00:00",
        "days": 30,
        "tenant": "acme",
        "total_traces": 100,
        "label_count": 30,
        "label_source": "human_review",
        "thresholds": {
            "quality_threshold": {
                "status": "ok",
                "current": 80,
                "suggested": 75,
                "current_metrics": {"precision": 0.5, "recall": 0.4, "f1": 0.44},
                "suggested_metrics": {"precision": 0.72, "recall": 0.89, "f1": 0.8},
                "histogram": "70-79 | ###",
                "note": "lowering improves recall",
            },
            "fact_verification_min_score": {
                "status": "insufficient_data",
                "current": 70,
                "suggested": None,
                "reason": "insufficient labeled traces",
                "histogram": "60-69 | ##",
            },
            "escalation_threshold": {
                "status": "ok",
                "current": 0.7,
                "suggested": 0.65,
                "current_metrics": {"precision": 0.6, "recall": 0.5, "f1": 0.55},
                "suggested_metrics": {"precision": 0.8, "recall": 0.75, "f1": 0.77},
                "histogram": "0.6-0.7 | ####",
                "note": "better balance",
            },
            "slow_trace_threshold_ms": {
                "status": "ok",
                "current": 10000,
                "suggested": 12000,
                "current_metrics": {"precision": 0.7, "recall": 0.3, "f1": 0.42},
                "suggested_metrics": {"precision": 0.72, "recall": 0.85, "f1": 0.78},
                "histogram": "10k-12k | #####",
                "percentiles": {"p50": 3200, "p90": 8400, "p95": 12000, "p99": 22000},
                "note": "use p95",
            },
        },
        "caveats": ["Tenant acme dominates bad verdicts."],
    }

    markdown = analyze_thresholds.render_report(analysis)

    assert "# Threshold recommendations" in markdown
    assert "## quality_threshold" in markdown
    assert "QUALITY_THRESHOLD=75" in markdown
    assert "ESCALATION_THRESHOLD=0.65" in markdown
    assert "insufficient labeled traces" in markdown
    assert "Tenant acme dominates bad verdicts." in markdown


def test_run_once_analyzes_sqlite_traces_and_human_labels(tmp_path: Path) -> None:
    from scripts import analyze_thresholds

    db_path = tmp_path / "traces.db"
    report_path = tmp_path / "threshold_recommendations.md"
    _init_trace_db(db_path)

    for score in range(100):
        _insert_trace(
            db_path,
            f"trace-{score:03d}",
            tenant_id="acme",
            final_quality=float(score),
            final_relevance=round(score / 100, 2),
            fact_score=float(score),
            duration_ms=12000 - (score * 100),
        )

    review_rows: list[dict[str, object]] = []
    for score in range(45, 75):
        review_rows.append(
            {
                "trace_id": f"trace-{score:03d}",
                "tenant_id": "acme",
                "status": "confirmed_bad" if score < 60 else "confirmed_good",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    settings = SimpleNamespace(
        tracing_db_path=db_path,
        project_root=tmp_path,
        quality_threshold=80,
        fact_verification_min_score=70,
        escalation_threshold=0.7,
        slow_trace_threshold_ms=10000,
        threshold_analysis_min_labels=20,
    )

    result = asyncio.run(
        analyze_thresholds.run_once(
            days=30,
            tenant="acme",
            out=report_path,
            session_factory=lambda: _ThresholdSession(review_rows=review_rows),
            settings=settings,
        )
    )

    assert result["label_source"] == "human_review"
    assert result["label_count"] == 30
    assert result["total_traces"] == 100
    assert result["thresholds"]["quality_threshold"]["suggested"] == 60
    assert result["thresholds"]["fact_verification_min_score"]["suggested"] == 60
    assert result["thresholds"]["escalation_threshold"]["suggested"] == pytest.approx(0.6)
    assert result["thresholds"]["slow_trace_threshold_ms"]["suggested"] == 6000
    assert report_path.exists()


def test_threshold_admin_endpoints_refresh_and_get_cached_analysis(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    payload = {
        "generated_at": "2026-04-21T12:00:00+00:00",
        "days": 30,
        "tenant": "acme",
        "total_traces": 12,
        "label_count": 8,
        "label_source": "human_review",
        "thresholds": {
            "quality_threshold": {
                "status": "ok",
                "current": 80,
                "suggested": 75,
            }
        },
        "caveats": [],
    }

    stored: dict[str, object] = {}

    async def _fake_run_once(*, days: int, tenant: str, out, session_factory=None, settings=None, now=None):
        assert days == 30
        assert tenant == "acme"
        return payload

    monkeypatch.setattr(api_app, "cache_json_get", lambda key: stored.get(key), raising=False)
    monkeypatch.setattr(
        api_app,
        "cache_json_set",
        lambda key, value, ttl_seconds=0: stored.__setitem__(key, value),
        raising=False,
    )

    from scripts import analyze_thresholds

    monkeypatch.setattr(analyze_thresholds, "run_once", _fake_run_once)

    refresh = client_with_key.post(
        "/api/admin/thresholds/refresh?days=30",
        headers=_token("acme", "admin"),
    )

    assert refresh.status_code == 200
    assert refresh.json()["thresholds"]["quality_threshold"]["suggested"] == 75

    response = client_with_key.get(
        "/api/admin/thresholds/analysis?days=30",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["tenant"] == "acme"
    assert response.json()["thresholds"]["quality_threshold"]["current"] == 80

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("analytics-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _trace_connection(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _install_trace_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "traces.db"
    sqlite_trace = sys.modules["sqlite_trace"]
    monkeypatch.setattr(
        sqlite_trace,
        "_get_connection",
        lambda: _trace_connection(db_path),
        raising=False,
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE traces (
                trace_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                final_route TEXT,
                final_quality INTEGER
            );

            CREATE TABLE trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                state_json TEXT,
                ts TEXT NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                model_name TEXT,
                cost_usd REAL
            );
            """
        )
    return db_path


def _insert_trace(
    db_path: Path,
    *,
    trace_id: str,
    tenant_id: str = "acme",
    started_at: datetime,
    categories: list[str],
    route: str = "auto",
    quality_score: int = 80,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    model_name: str | None = None,
    cost_usd: float | None = None,
) -> None:
    state_json = json.dumps(
        {
            "graded_docs": [
                {
                    "metadata": {
                        "categories": categories,
                    }
                }
            ]
        }
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces (trace_id, started_at, tenant_id, final_route, final_quality)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, started_at.isoformat(), tenant_id, route, quality_score),
        )
        conn.execute(
            """
            INSERT INTO trace_steps (
                trace_id,
                step_order,
                node_name,
                state_json,
                ts,
                prompt_tokens,
                completion_tokens,
                model_name,
                cost_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                0,
                "generate",
                state_json,
                started_at.isoformat(),
                prompt_tokens,
                completion_tokens,
                model_name,
                cost_usd,
            ),
        )
        conn.commit()


def _install_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.app as api_app

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: SimpleNamespace(
            llm_input_price_per_1m_tokens=0.0,
            llm_output_price_per_1m_tokens=0.0,
            llm_model_prices={
                "claude-opus-4-7": {"input": 15.0, "output": 75.0},
                "ollama-local": {"input": 0.0, "output": 0.0},
            },
            ollama_model_name="ollama-local",
            ollama_fast_model_name="ollama-fast",
        ),
        raising=False,
    )


def test_load_recent_trace_summaries_calculates_cost_from_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    db_path = _install_trace_db(monkeypatch, tmp_path)
    _install_pricing(monkeypatch)
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    _insert_trace(
        db_path,
        trace_id="trace-paid",
        started_at=now,
        categories=["shipping"],
        prompt_tokens=100,
        completion_tokens=50,
        model_name="claude-opus-4-7",
    )

    summaries = api_app._load_recent_trace_summaries("acme", 7)

    assert len(summaries) == 1
    assert summaries[0]["cost_usd"] == pytest.approx(0.00525)


def test_load_recent_trace_summaries_keeps_ollama_cost_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    db_path = _install_trace_db(monkeypatch, tmp_path)
    _install_pricing(monkeypatch)
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    _insert_trace(
        db_path,
        trace_id="trace-free",
        started_at=now,
        categories=["shipping"],
        prompt_tokens=100,
        completion_tokens=50,
        model_name="ollama-local",
    )

    summaries = api_app._load_recent_trace_summaries("acme", 7)

    assert len(summaries) == 1
    assert summaries[0]["cost_usd"] == 0.0


def test_cost_summary_aggregates_trace_costs_over_period(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    client_with_key,
) -> None:
    db_path = _install_trace_db(monkeypatch, tmp_path)
    _install_pricing(monkeypatch)
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    _insert_trace(
        db_path,
        trace_id="trace-paid-1",
        started_at=now,
        categories=["shipping"],
        prompt_tokens=100,
        completion_tokens=50,
        model_name="claude-opus-4-7",
    )
    _insert_trace(
        db_path,
        trace_id="trace-paid-2",
        started_at=now,
        categories=["shipping"],
        prompt_tokens=200,
        completion_tokens=100,
        model_name="claude-opus-4-7",
    )

    response = client_with_key.get(
        "/api/analytics/cost-summary?days=7",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_cost_usd"] == pytest.approx(0.01575)
    assert payload["summary"]["label"] == "$0.02"
    assert payload["per_category"] == [
        {"category": "shipping", "cost_usd": pytest.approx(0.01575)}
    ]


def test_top_topics_endpoint_groups_by_category(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        api_app,
        "_load_recent_trace_summaries",
        lambda tenant_id, days: [
            {
                "categories": ["shipping"],
                "route": "auto",
                "quality_score": 80,
                "cost_usd": 0.0,
                "created_at": now,
            },
            {
                "categories": ["shipping", "returns"],
                "route": "human",
                "quality_score": 60,
                "cost_usd": 0.0,
                "created_at": now,
            },
        ],
    )

    response = client_with_key.get(
        "/api/analytics/top-topics?days=7",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    topics = response.json()["topics"]
    assert topics[0]["category"] == "shipping"
    assert topics[0]["count"] == 2


def test_cost_summary_reports_self_hosted_when_cost_is_zero(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        api_app,
        "_load_recent_trace_summaries",
        lambda tenant_id, days: [
            {
                "categories": ["shipping"],
                "route": "auto",
                "quality_score": 80,
                "cost_usd": 0.0,
                "created_at": now,
            }
        ],
    )

    response = client_with_key.get(
        "/api/analytics/cost-summary?days=7",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["label"] == "self-hosted (no cost)"

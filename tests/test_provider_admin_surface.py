from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from auth.jwt_handler import create_access_token


def _seed_provider_trace_db(path: Path) -> None:
    recent_ts = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE traces (
                trace_id TEXT PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                final_route TEXT,
                final_quality INTEGER,
                final_relevance REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                step_order INTEGER,
                node_name TEXT,
                state_json TEXT,
                ts TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                model_name TEXT,
                provider_name TEXT,
                cost_usd REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO traces (trace_id, started_at, tenant_id)
            VALUES (?, ?, ?)
            """,
            ("trace-provider-admin", recent_ts, "default"),
        )
        conn.execute(
            """
            INSERT INTO trace_steps (
                trace_id, step_order, node_name, state_json, ts,
                prompt_tokens, completion_tokens, model_name, provider_name, cost_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trace-provider-admin",
                0,
                "generate",
                "{}",
                recent_ts,
                120,
                30,
                "qwen2.5:7b",
                "ollama",
                0.0,
            ),
        )
        conn.commit()


def test_admin_providers_endpoint_returns_registry_and_recent_usage(
    client_with_key,
    monkeypatch,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    db_path = tmp_path / "traces.db"
    _seed_provider_trace_db(db_path)

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: SimpleNamespace(
            provider_registry_path=Path(__file__).resolve().parent.parent / "config" / "providers.yml",
            tracing_db_path=db_path,
            llm_provider_profile="local-first",
        ),
    )

    response = client_with_key.get(
        "/api/admin/providers",
        headers={"Authorization": f"Bearer {create_access_token('admin', 'admin', 'default')}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_profile"] == "local-first"
    assert payload["default_profile"] == "local-first"

    ollama = next(item for item in payload["providers"] if item["id"] == "ollama")
    assert ollama["configured"] is True
    assert ollama["usage_1m"]["requests"] == 1
    assert ollama["usage_1m"]["tokens"] == 150
    assert ollama["last_success_at"]


def test_admin_html_contains_providers_tab(client) -> None:
    response = client.get("/static/admin.html")

    assert response.status_code == 200
    assert "Providers" in response.text
    assert "btn-load-providers" in response.text

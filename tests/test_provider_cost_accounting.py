from __future__ import annotations

import importlib
import sqlite3
import uuid

import pytest


def test_trace_log_step_persists_provider_name_and_cost(monkeypatch, tmp_path) -> None:
    trace_module = importlib.import_module("tracing.sqlite_trace")
    db_path = tmp_path / "traces.db"
    monkeypatch.setattr(trace_module._sqlite_trace, "_get_db_path", lambda: db_path)
    trace_module._sqlite_trace._init_db()

    trace_id = trace_module.start_trace()
    trace_module.log_step(
        trace_id,
        "generate",
        {
            "provider_name": "mistral",
            "model_name": "mistral-small-latest",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider_name, model_name, prompt_tokens, completion_tokens, cost_usd
            FROM trace_steps
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "mistral"
    assert row[1] == "mistral-small-latest"
    assert row[2] == 1000
    assert row[3] == 500
    assert row[4] == pytest.approx(0.0005)


def test_prometheus_metrics_expose_provider_cost_counter(client, monkeypatch, tmp_path) -> None:
    trace_module = importlib.import_module("tracing.sqlite_trace")
    db_path = tmp_path / "traces.db"
    monkeypatch.setattr(trace_module._sqlite_trace, "_get_db_path", lambda: db_path)
    trace_module._sqlite_trace._init_db()
    tenant_id = f"provider-metrics-{uuid.uuid4().hex}"
    metric_line = (
        f'llm_cost_usd_total{{model="mistral-small-latest",provider="mistral",tenant="{tenant_id}"}} 0.25'
    )

    before = client.get("/metrics").text
    assert metric_line not in before

    trace_id = trace_module.start_trace()
    trace_module.log_step(
        trace_id,
        "generate",
        {
            "tenant_id": tenant_id,
            "provider_name": "mistral",
            "model_name": "mistral-small-latest",
            "cost_usd": 0.25,
        },
    )

    after = client.get("/metrics").text
    assert metric_line in after

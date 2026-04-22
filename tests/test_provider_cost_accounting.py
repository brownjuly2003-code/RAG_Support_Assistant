from __future__ import annotations

import importlib
import sqlite3
import sys

import pytest


def test_trace_log_step_persists_provider_name_and_cost(monkeypatch, tmp_path) -> None:
    trace_module_module = sys.modules.pop("tracing.sqlite_trace", None)
    sqlite_trace_module = sys.modules.pop("sqlite_trace", None)
    trace_module = importlib.import_module("tracing.sqlite_trace")
    db_path = tmp_path / "traces.db"
    try:
        monkeypatch.setattr(trace_module._sqlite_trace, "_get_db_path", lambda: db_path)
        trace_module._sqlite_trace._init_db()

        trace_id = trace_module.start_trace()
        trace_module.log_step(
            trace_id,
            "generate",
            {
                "provider_name": "claude",
                "model_name": "claude-haiku-4-5",
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
        assert row[0] == "claude"
        assert row[1] == "claude-haiku-4-5"
        assert row[2] == 1000
        assert row[3] == 500
        assert row[4] == pytest.approx(0.0035)
    finally:
        sys.modules.pop("tracing.sqlite_trace", None)
        sys.modules.pop("sqlite_trace", None)
        if trace_module_module is not None:
            sys.modules["tracing.sqlite_trace"] = trace_module_module
        if sqlite_trace_module is not None:
            sys.modules["sqlite_trace"] = sqlite_trace_module


def test_prometheus_metrics_expose_provider_cost_counter(client) -> None:
    sqlite_trace_module = sys.modules.pop("sqlite_trace", None)
    tenant_id = "provider-metrics-test"
    metric_line = (
        f'llm_cost_usd_total{{model="gpt-5.4",provider="openai",tenant="{tenant_id}"}} 0.25'
    )
    try:
        sqlite_trace = importlib.import_module("sqlite_trace")

        before = client.get("/metrics").text
        assert metric_line not in before

        trace_id = sqlite_trace.start_trace()
        sqlite_trace.log_step(
            trace_id,
            "generate",
            {
                "tenant_id": tenant_id,
                "provider_name": "openai",
                "model_name": "gpt-5.4",
                "cost_usd": 0.25,
            },
        )

        after = client.get("/metrics").text
        assert metric_line in after
    finally:
        sys.modules.pop("sqlite_trace", None)
        if sqlite_trace_module is not None:
            sys.modules["sqlite_trace"] = sqlite_trace_module

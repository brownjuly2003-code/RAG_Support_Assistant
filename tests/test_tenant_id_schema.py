from __future__ import annotations

import importlib
import sqlite3


def test_graph_state_accepts_tenant_id() -> None:
    from agent.state import create_initial_state

    state = create_initial_state(
        question="x",
        trace_id="t1",
        tenant_id="acme-corp",
    )

    assert state["tenant_id"] == "acme-corp"


def test_graph_state_defaults_to_default_tenant() -> None:
    from agent.state import create_initial_state

    state = create_initial_state(question="x", trace_id="t1")

    assert state["tenant_id"] == "default"


def test_ask_request_accepts_tenant_id(mock_pipeline, client) -> None:
    response = client.post(
        "/api/ask",
        json={"question": "hi", "tenant_id": "customer-42"},
    )

    assert response.status_code == 200


def test_ask_request_rejects_malformed_tenant_id(client) -> None:
    response = client.post(
        "/api/ask",
        json={"question": "hi", "tenant_id": "bad tenant; DROP"},
    )

    assert response.status_code == 422


def test_sqlite_trace_accepts_tenant_id(tmp_path) -> None:
    sqlite_trace = importlib.import_module("tracing._base_trace")
    db_path = tmp_path / "traces.db"
    original_get_db_path = sqlite_trace._get_db_path
    try:
        sqlite_trace._get_db_path = lambda: db_path
        sqlite_trace._init_db()

        trace_id = sqlite_trace.start_trace(tenant_id="megacorp")

        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT tenant_id FROM traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
    finally:
        sqlite_trace._get_db_path = original_get_db_path

    assert row is not None
    assert row[0] == "megacorp"

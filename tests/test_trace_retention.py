from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CLIENT_WITH_KEY_RAISE_SERVER_EXCEPTIONS = False


@pytest.fixture
def trace_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    import config.settings as settings_module

    source_path = Path(__file__).resolve().parent.parent / "sqlite_trace.py"
    module_path = tmp_path / "sqlite_trace.py"
    module_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    previous_module = sys.modules.pop("sqlite_trace", None)
    settings_module._settings = None
    monkeypatch.setenv("TRACING_DB_PATH", str(tmp_path / "traces.db"))

    spec = importlib.util.spec_from_file_location("sqlite_trace", module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules["sqlite_trace"] = module
    spec.loader.exec_module(module)

    try:
        yield module
    finally:
        sys.modules.pop("sqlite_trace", None)
        if previous_module is not None:
            sys.modules["sqlite_trace"] = previous_module
        settings_module._settings = None


def _insert_trace(db_path: Path, trace_id: str, days_ago: int) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces (
                trace_id,
                started_at,
                finished_at,
                final_route,
                final_quality,
                final_relevance
            ) VALUES (?, ?, NULL, NULL, NULL, NULL)
            """,
            (trace_id, ts),
        )
        conn.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, 0, "node", "{}", ts),
        )
        conn.execute(
            """
            INSERT INTO feedback (trace_id, session_id, rating, reason, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, f"session-{trace_id}", "up", "", ts),
        )
        conn.commit()


def _purged_metric_value(table: str) -> float | None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, TRACES_PURGED

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in TRACES_PURGED.collect():
        for sample in metric.samples:
            if sample.name == "rag_traces_purged_total" and sample.labels.get("table") == table:
                return sample.value
    return 0.0


def test_purge_deletes_old_traces_and_keeps_recent(trace_module) -> None:
    db_path = Path(trace_module._get_db_path())

    _insert_trace(db_path, "old-1", days_ago=120)
    _insert_trace(db_path, "old-2", days_ago=95)
    _insert_trace(db_path, "new-1", days_ago=10)

    result = trace_module.purge_old_traces(retention_days=90)

    assert result == {"traces_deleted": 2, "steps_deleted": 2, "feedback_deleted": 2}

    with sqlite3.connect(db_path) as conn:
        remaining = [
            row[0]
            for row in conn.execute("SELECT trace_id FROM traces ORDER BY started_at")
        ]
        index_name = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index' AND name = 'idx_traces_started_at'
            """
        ).fetchone()

    assert remaining == ["new-1"]
    assert index_name == ("idx_traces_started_at",)


def test_purge_with_zero_retention_is_noop(trace_module) -> None:
    db_path = Path(trace_module._get_db_path())
    _insert_trace(db_path, "old-1", days_ago=365)

    result = trace_module.purge_old_traces(retention_days=0)

    assert result == {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]

    assert count == 1


def test_purge_handles_empty_db(trace_module) -> None:
    result = trace_module.purge_old_traces(retention_days=30)

    assert result == {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}


def test_admin_purge_endpoint_returns_counts_and_records_audit(
    trace_module,
    client_with_key: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auth.jwt_handler import create_access_token

    db_path = Path(trace_module._get_db_path())
    _insert_trace(db_path, "ancient", days_ago=200)
    _insert_trace(db_path, "recent", days_ago=5)

    audit_calls: list[dict] = []

    async def _fake_log_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    before_metric = _purged_metric_value("traces")
    token = create_access_token("admin", "admin")

    response = client_with_key.request(
        "DELETE",
        "/api/admin/traces?older_than_days=30",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "traces_deleted": 1,
        "steps_deleted": 1,
        "feedback_deleted": 1,
    }
    assert audit_calls == [
        {
            "actor": "admin",
            "action": "trace_purge",
            "resource": "traces/older_than=30d",
            "detail": {
                "traces_deleted": 1,
                "steps_deleted": 1,
                "feedback_deleted": 1,
            },
            "ip_address": "testclient",
        }
    ]

    with sqlite3.connect(db_path) as conn:
        remaining = [
            row[0]
            for row in conn.execute("SELECT trace_id FROM traces ORDER BY started_at")
        ]

    assert remaining == ["recent"]
    if before_metric is not None:
        assert _purged_metric_value("traces") == before_metric + 1.0


def test_admin_purge_endpoint_enforces_role_and_range(
    trace_module,
    client_with_key: TestClient,
) -> None:
    from auth.jwt_handler import create_access_token

    viewer_token = create_access_token("viewer-user", "viewer")
    admin_token = create_access_token("admin-user", "admin")

    viewer_response = client_with_key.request(
        "DELETE",
        "/api/admin/traces?older_than_days=30",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    negative_days_response = client_with_key.request(
        "DELETE",
        "/api/admin/traces?older_than_days=-1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    too_large_response = client_with_key.request(
        "DELETE",
        "/api/admin/traces?older_than_days=3651",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert viewer_response.status_code == 403
    assert negative_days_response.status_code == 400
    assert too_large_response.status_code == 400

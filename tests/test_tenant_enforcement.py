from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant: str = "default", role: str = "admin") -> dict[str, str]:
    token = create_access_token("tenant-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def real_trace_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    import config.settings as settings_module

    source_path = Path(__file__).resolve().parent.parent / "tracing" / "_base_trace.py"
    module_path = tmp_path / "sqlite_trace.py"
    module_path.write_text(
        source_path.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )

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


def _insert_trace(
    db_path: Path,
    trace_id: str,
    tenant_id: str,
    days_ago: int,
) -> None:
    started_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()

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
            ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL)
            """,
            (trace_id, started_at, tenant_id),
        )
        conn.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, 0, "retrieve", "{}", started_at),
        )
        conn.execute(
            """
            INSERT INTO feedback (trace_id, session_id, rating, reason, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, f"session-{trace_id}", "up", "", started_at),
        )
        conn.commit()


def test_list_traces_filters_by_tenant(real_trace_module) -> None:
    db_path = Path(real_trace_module._get_db_path())
    _insert_trace(db_path, "acme-trace-1", "acme-corp", days_ago=1)
    _insert_trace(db_path, "mega-trace-1", "megacorp", days_ago=1)

    acme_only = real_trace_module.list_recent_traces(50, tenant_id="acme-corp")
    mega_only = real_trace_module.list_recent_traces(50, tenant_id="megacorp")
    all_traces = real_trace_module.list_recent_traces(50)

    assert [item["trace_id"] for item in acme_only] == ["acme-trace-1"]
    assert [item["trace_id"] for item in mega_only] == ["mega-trace-1"]
    assert {item["trace_id"] for item in all_traces} == {"acme-trace-1", "mega-trace-1"}


def test_get_trace_detail_hides_foreign_tenant(real_trace_module) -> None:
    db_path = Path(real_trace_module._get_db_path())
    _insert_trace(db_path, "acme-trace-1", "acme-corp", days_ago=1)
    _insert_trace(db_path, "mega-trace-1", "megacorp", days_ago=1)

    assert real_trace_module.get_trace_detail("acme-trace-1", tenant_id="acme-corp") is not None
    assert real_trace_module.get_trace_detail("mega-trace-1", tenant_id="acme-corp") is None


def test_purge_traces_respects_tenant(real_trace_module) -> None:
    db_path = Path(real_trace_module._get_db_path())
    _insert_trace(db_path, "acme-old-trace", "acme-corp", days_ago=120)
    _insert_trace(db_path, "mega-old-trace", "megacorp", days_ago=120)

    result = real_trace_module.purge_old_traces(30, tenant_id="acme-corp")

    with sqlite3.connect(db_path) as conn:
        remaining = [
            row[0]
            for row in conn.execute("SELECT trace_id FROM traces ORDER BY trace_id")
        ]

    assert result["traces_deleted"] == 1
    assert remaining == ["mega-old-trace"]


def test_admin_traces_endpoint_filters_by_jwt_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, object] = {}

    def _fake_list_recent_traces(limit: int, tenant_id: str | None = None):
        captured["limit"] = limit
        captured["tenant_id"] = tenant_id
        if tenant_id == "acme":
            return [{"trace_id": "tenant-trace", "started_at": None, "finished_at": None}]
        return []

    monkeypatch.setattr("sqlite_trace.list_recent_traces", _fake_list_recent_traces, raising=False)

    response = client_with_key.get("/api/admin/traces?limit=5", headers=_token("acme", "agent"))

    assert response.status_code == 200
    assert response.json()["traces"] == [
        {"trace_id": "tenant-trace", "started_at": None, "finished_at": None}
    ]
    assert captured == {"limit": 5, "tenant_id": "acme"}


def test_admin_trace_detail_returns_404_for_foreign(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    def _fake_get_trace_detail(trace_id: str, tenant_id: str | None = None):
        if tenant_id == "acme":
            return None
        return {
            "trace_id": trace_id,
            "started_at": "2026-04-17T00:00:00Z",
            "finished_at": None,
            "steps": [],
            "feedback": [],
        }

    monkeypatch.setattr("sqlite_trace.get_trace_detail", _fake_get_trace_detail, raising=False)

    response = client_with_key.get(
        "/api/admin/traces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "trace not found"}


def test_admin_audit_list_filters_by_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, str] = {}

    class _Row:
        id = 1
        ts = None
        actor = "support-1"
        action = "trace_view"
        resource = "trace/abc123"
        detail = "{}"
        ip_address = None

    class _ScalarResult:
        def all(self):
            return [_Row()]

    class _Result:
        def scalars(self):
            return _ScalarResult()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get("/api/admin/audit?limit=5", headers=_token("my-tenant", "admin"))

    assert response.status_code == 200
    assert "WHERE audit_log.tenant_id" in captured["sql"]


def test_audit_purge_scoped_to_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_purge_old_audit(days: int, tenant_id: str | None = None) -> int:
        captured["days"] = days
        captured["tenant_id"] = tenant_id
        return 5

    async def _fake_log_audit(**kwargs) -> None:
        captured.setdefault("audit_calls", []).append(kwargs)

    monkeypatch.setattr("db.audit.purge_old_audit", _fake_purge_old_audit)
    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    response = client_with_key.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=30",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    assert captured["days"] == 30
    assert captured["tenant_id"] == "acme"


def test_metrics_snapshot_filtered_by_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, object] = {}

    def _fake_get_metrics_snapshot(tenant_id: str | None = None):
        captured["tenant_id"] = tenant_id
        return {
            "latency": {},
            "escalation": {},
            "quality": {},
            "errors": {},
            "feedback": {},
            "generated_at": "2026-04-18T00:00:00+00:00",
        }

    monkeypatch.setattr("sqlite_trace.get_metrics_snapshot", _fake_get_metrics_snapshot, raising=False)

    response = client_with_key.get("/api/metrics", headers=_token("x-corp", "admin"))

    assert response.status_code == 200
    assert captured["tenant_id"] == "x-corp"

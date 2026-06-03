from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_HEADERS = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}
AGENT_HEADERS = {"Authorization": f"Bearer {create_access_token('op1', 'agent')}"}
VIEWER_HEADERS = {"Authorization": f"Bearer {create_access_token('v1', 'viewer')}"}


def test_audit_list_requires_role(client_with_key: TestClient) -> None:
    response = client_with_key.get("/api/admin/audit", headers=VIEWER_HEADERS)

    assert response.status_code == 403


def test_audit_list_admin_ok(monkeypatch, client_with_key: TestClient) -> None:
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

        async def execute(self, *args, **kwargs):
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get("/api/admin/audit?limit=10", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "entries": [
            {
                "id": 1,
                "ts": None,
                "actor": "support-1",
                "action": "trace_view",
                "resource": "trace/abc123",
                "detail": "{}",
                "ip_address": None,
            }
        ]
    }


def test_traces_list_agent_ok(monkeypatch, client_with_key: TestClient) -> None:
    monkeypatch.setattr(
        "tracing.sqlite_trace.list_recent_traces",
        lambda limit: [
            {
                "trace_id": "abc123",
                "started_at": "2026-04-17T00:00:00Z",
                "finished_at": None,
            }
        ],
        raising=False,
    )

    response = client_with_key.get("/api/admin/traces?limit=5", headers=AGENT_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "traces": [
            {
                "trace_id": "abc123",
                "started_at": "2026-04-17T00:00:00Z",
                "finished_at": None,
            }
        ]
    }


def test_trace_detail_not_found(monkeypatch, client_with_key: TestClient) -> None:
    monkeypatch.setattr(
        "tracing.sqlite_trace.get_trace_detail",
        lambda trace_id: None,
        raising=False,
    )

    response = client_with_key.get(
        "/api/admin/traces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "trace not found"}


def test_trace_detail_invalid_id_rejected(monkeypatch, client_with_key: TestClient) -> None:
    def _unexpected_call(trace_id: str):
        raise AssertionError(f"trace lookup must not happen for invalid id: {trace_id}")

    monkeypatch.setattr(
        "tracing.sqlite_trace.get_trace_detail",
        _unexpected_call,
        raising=False,
    )

    response = client_with_key.get(
        "/api/admin/traces/'; DROP TABLE traces--",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code in (400, 404)


def test_trace_detail_returns_steps(monkeypatch, client_with_key: TestClient) -> None:
    trace = {
        "trace_id": "abc12345",
        "started_at": "2026-04-17T00:00:00Z",
        "finished_at": "2026-04-17T00:00:02Z",
        "steps": [
            {
                "order": 0,
                "node": "transform_query",
                "state": {},
                "ts": "2026-04-17T00:00:00Z",
            }
        ],
        "feedback": [],
    }
    monkeypatch.setattr(
        "tracing.sqlite_trace.get_trace_detail",
        lambda trace_id: trace,
        raising=False,
    )

    response = client_with_key.get("/api/admin/traces/abc12345", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == trace


def test_review_queue_trace_action_uses_authenticated_api_fetch() -> None:
    # CSP (commit 67dc286) split admin's inline JS into static/admin.inline*.js;
    # join them so the assertion is robust to which split the code lands in.
    js = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((PROJECT_ROOT / "static").glob("admin.inline*.js"))
    )

    assert 'fetch("/api/admin/traces/" + encodeURIComponent(item.trace_id || ""), {' in js
    assert 'traceLink.target = "_blank";' not in js

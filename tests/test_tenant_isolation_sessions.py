"""Cross-tenant isolation guards for /api/sessions* and feedback (Codex P0).

Without these checks an agent/admin from tenant A could:
- read history of any session from tenant B if they knew/guessed the UUID,
- list sessions from tenant B,
- delete tenant B's session,
- read tenant B's feedback statistics.
"""

from __future__ import annotations

import importlib
from typing import Any

from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


def _auth(tenant: str, role: str = "agent") -> dict[str, str]:
    token = create_access_token("u-" + tenant, role, tenant)
    return {"Authorization": f"Bearer {token}"}


def _seed_session(session_id: str, tenant_id: str, history: list[dict[str, str]]) -> None:
    api_app._sessions[session_id] = {
        "history": history,
        "tenant_id": tenant_id,
    }


def test_history_blocks_cross_tenant_access(client: TestClient) -> None:
    _seed_session(
        "sess-a",
        "tenant-a",
        [{"role": "user", "content": "secret-a"}],
    )

    response = client.get("/api/sessions/sess-a/history", headers=_auth("tenant-b"))
    assert response.status_code == 404, response.text


def test_history_returns_history_for_owning_tenant(client: TestClient) -> None:
    _seed_session(
        "sess-a",
        "tenant-a",
        [{"role": "user", "content": "hello-a"}],
    )

    response = client.get("/api/sessions/sess-a/history", headers=_auth("tenant-a"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(m["content"] == "hello-a" for m in body["messages"])


def test_list_sessions_filters_by_tenant(client: TestClient) -> None:
    _seed_session("sess-a", "tenant-a", [{"role": "user", "content": "a"}])
    _seed_session("sess-b", "tenant-b", [{"role": "user", "content": "b"}])

    response = client.get("/api/sessions", headers=_auth("tenant-a"))
    assert response.status_code == 200, response.text
    ids = {item["session_id"] for item in response.json()}
    assert "sess-a" in ids
    assert "sess-b" not in ids


def test_delete_session_blocks_cross_tenant(client: TestClient) -> None:
    _seed_session("sess-a", "tenant-a", [{"role": "user", "content": "a"}])

    response = client.delete("/api/sessions/sess-a", headers=_auth("tenant-b"))
    assert response.status_code == 404, response.text
    # Session must remain in memory.
    assert "sess-a" in api_app._sessions


def test_delete_session_succeeds_for_owning_tenant(client: TestClient) -> None:
    _seed_session("sess-a", "tenant-a", [{"role": "user", "content": "a"}])

    response = client.delete("/api/sessions/sess-a", headers=_auth("tenant-a"))
    assert response.status_code == 200, response.text
    assert "sess-a" not in api_app._sessions


def test_invalid_session_id_does_not_poison_db_cooldown(client: TestClient) -> None:
    """Non-uuid session_id must not blow up to 500 nor trip _db_retry_after.

    Regression: previously `uuid.UUID(session_id)` raised inside the SQLAlchemy
    expression, was caught by the outer except, set `_db_retry_after = +60s`
    and returned 404 from the in-memory fallback — but disabled DB lookups for
    everyone for a minute. Now we parse early and skip DB on invalid input.
    """
    api_app._db_retry_after = 0.0

    response = client.get(
        "/api/sessions/not-a-uuid/history", headers=_auth("tenant-a")
    )
    assert response.status_code == 404, response.text
    assert api_app._db_retry_after == 0.0, "DB cooldown must not be poisoned"

    response = client.delete(
        "/api/sessions/also-bad", headers=_auth("tenant-a")
    )
    assert response.status_code == 404, response.text
    assert api_app._db_retry_after == 0.0, "DB cooldown must not be poisoned"


def test_feedback_save_propagates_tenant(monkeypatch, client: TestClient) -> None:
    saved: dict[str, Any] = {}

    def _capture_save_feedback(**kwargs):
        saved.update(kwargs)

    import sys
    fake_module = type(sys)("tracing.sqlite_trace")
    fake_module.save_feedback = _capture_save_feedback  # type: ignore[attr-defined]
    fake_module.get_feedback_stats = lambda **kwargs: {  # type: ignore[attr-defined]
        "total": 0,
        "up": 0,
        "down": 0,
        "up_pct": 0.0,
        "by_route": {},
        "period_days": kwargs.get("days", 30),
    }
    monkeypatch.setitem(sys.modules, "tracing.sqlite_trace", fake_module)

    response = client.post(
        "/api/feedback",
        json={
            "trace_id": "t-1",
            "session_id": "s-1",
            "rating": "up",
            "reason": "great",
        },
        headers=_auth("tenant-a"),
    )
    assert response.status_code == 204, response.text
    assert saved.get("tenant_id") == "tenant-a"


def test_feedback_stats_scope_per_tenant_for_agent(monkeypatch, client: TestClient) -> None:
    captured: dict[str, Any] = {}

    def _stub_stats(days: int = 30, tenant_id: str | None = None) -> dict:
        captured["tenant_id"] = tenant_id
        captured["days"] = days
        return {"total": 0, "up": 0, "down": 0, "up_pct": 0.0, "by_route": {}, "period_days": days}

    import sys
    fake_module = type(sys)("tracing.sqlite_trace")
    fake_module.get_feedback_stats = _stub_stats  # type: ignore[attr-defined]
    fake_module.save_feedback = lambda **kwargs: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tracing.sqlite_trace", fake_module)

    response = client.get("/api/feedback/stats", headers=_auth("tenant-a", role="agent"))
    assert response.status_code == 200, response.text
    assert captured["tenant_id"] == "tenant-a", "agent must only see his tenant"


def test_feedback_stats_global_for_admin(monkeypatch, client: TestClient) -> None:
    captured: dict[str, Any] = {}

    def _stub_stats(days: int = 30, tenant_id: str | None = None) -> dict:
        captured["tenant_id"] = tenant_id
        return {"total": 0, "up": 0, "down": 0, "up_pct": 0.0, "by_route": {}, "period_days": days}

    import sys
    fake_module = type(sys)("tracing.sqlite_trace")
    fake_module.get_feedback_stats = _stub_stats  # type: ignore[attr-defined]
    fake_module.save_feedback = lambda **kwargs: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tracing.sqlite_trace", fake_module)

    response = client.get("/api/feedback/stats", headers=_auth("tenant-a", role="admin"))
    assert response.status_code == 200, response.text
    assert captured["tenant_id"] is None, "admin must keep global aggregate"

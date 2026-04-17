from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient


def test_purge_with_zero_retention_is_noop() -> None:
    from db.audit import purge_old_audit

    result = asyncio.run(purge_old_audit(0))

    assert result == 0


def test_purge_with_negative_returns_zero() -> None:
    from db.audit import purge_old_audit

    result = asyncio.run(purge_old_audit(-10))

    assert result == 0


def test_admin_purge_endpoint_calls_purge(
    monkeypatch,
    client_with_key: TestClient,
) -> None:
    from auth.jwt_handler import create_access_token

    called_with: dict[str, object] = {}

    async def _fake_purge(days: int) -> int:
        called_with["days"] = days
        return 42

    async def _fake_log_audit(**kwargs) -> None:
        called_with.setdefault("audit_calls", []).append(kwargs)

    monkeypatch.setattr("db.audit.purge_old_audit", _fake_purge)
    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    token = create_access_token("admin", "admin")
    response = client_with_key.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=90",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 42}
    assert called_with["days"] == 90
    assert any(
        call.get("action") == "audit_purge"
        for call in called_with.get("audit_calls", [])
    )


def test_admin_purge_rejects_non_admin(client_with_key: TestClient) -> None:
    from auth.jwt_handler import create_access_token

    token = create_access_token("viewer-user", "viewer")
    response = client_with_key.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=90",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_purge_validates_bounds(client_with_key: TestClient) -> None:
    from auth.jwt_handler import create_access_token

    token = create_access_token("admin", "admin")

    for bad in (-1, 4000):
        response = client_with_key.request(
            "DELETE",
            f"/api/admin/audit-log?older_than_days={bad}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400, f"expected 400 for {bad}"

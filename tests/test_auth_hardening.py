"""Тесты rate-limit + observability на /auth/login."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

CLIENT_DELETE_ENV = ("ADMIN_PASSWORD_HASH",)


def _auth_failure_total() -> float | None:
    from monitoring.prometheus import AUTH_FAILURES, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return None

    total = 0.0
    for metric in AUTH_FAILURES.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                total += sample.value
    return total


def test_failed_login_returns_401_and_records_audit(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    audit_calls: list[dict] = []

    async def _fake_log_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    assert any(call.get("action") == "login_failed" for call in audit_calls), audit_calls


def test_failure_detail_is_generic(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    async def _noop(**kwargs) -> None:
        return None

    monkeypatch.setattr("api.app.log_audit", _noop)

    unknown_user = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    bad_password = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "x"},
    )

    assert unknown_user.status_code == 401
    assert bad_password.status_code == 401
    assert unknown_user.json()["detail"] == bad_password.json()["detail"]


def test_auth_failure_counter_increments(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    async def _noop(**kwargs) -> None:
        return None

    monkeypatch.setattr("api.app.log_audit", _noop)

    before = _auth_failure_total() or 0.0
    client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    after = _auth_failure_total() or 0.0

    assert after > before


def test_rate_limit_kicks_after_5_attempts(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    async def _noop(**kwargs) -> None:
        return None

    monkeypatch.setattr("api.app.log_audit", _noop)

    last_status = None
    for _ in range(8):
        response = client.post(
            "/api/auth/login",
            json={"username": "attacker", "password": "x"},
        )
        last_status = response.status_code
        if last_status == 429:
            break

    assert last_status == 429


def test_successful_login_does_not_increment_failure_counter(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    async def _noop(**kwargs) -> None:
        return None

    monkeypatch.setattr("api.app.log_audit", _noop)

    before = _auth_failure_total() or 0.0
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    after = _auth_failure_total() or 0.0

    assert response.status_code == 200
    assert after == before

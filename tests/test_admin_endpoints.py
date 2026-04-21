from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

import agent.graph as graph


def test_admin_can_reset_circuit_breaker(client_with_key: TestClient) -> None:
    import config.settings as settings_module

    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    graph._default_breaker = None

    breaker = graph.get_default_breaker()
    if breaker is None:
        pytest.skip("breaker disabled in this environment")

    for _ in range(breaker.failure_threshold):
        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

    assert breaker.snapshot()["state"] == "open"

    login = client_with_key.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client_with_key.post(
        "/api/admin/circuit-breaker/reset",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset"
    assert data["breaker"] == breaker.name
    assert data["previous"]["state"] == "open"
    assert data["current"]["state"] == "closed"
    assert breaker.snapshot()["state"] == "closed"


def test_viewer_is_forbidden(client_with_key: TestClient) -> None:
    from auth.jwt_handler import create_access_token

    token = create_access_token("viewer-user", "viewer")

    response = client_with_key.post(
        "/api/admin/circuit-breaker/reset",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_unauthenticated_is_rejected(client_with_key: TestClient) -> None:
    response = client_with_key.post("/api/admin/circuit-breaker/reset")

    assert response.status_code == 401


def test_reset_returns_409_when_breaker_disabled(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import config.settings as settings_module

    with monkeypatch.context() as context:
        context.setenv("CIRCUIT_BREAKER_ENABLED", "false")
        settings_module = importlib.reload(settings_module)
        settings_module._settings = None
        graph._default_breaker = None

        login = client_with_key.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        response = client_with_key.post(
            "/api/admin/circuit-breaker/reset",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 409
        assert response.json() == {
            "status": "disabled",
            "detail": "circuit breaker disabled via CIRCUIT_BREAKER_ENABLED=false",
        }

    importlib.reload(settings_module)
    graph._default_breaker = None

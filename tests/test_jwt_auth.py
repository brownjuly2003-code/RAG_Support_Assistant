from auth.jwt_handler import JWT_SECRET, verify_token
from fastapi.testclient import TestClient
CLIENT_SETTINGS_OVERRIDES = {
    "api_key": "secret123",
    "ollama_model_name": "test-model",
}
CLIENT_DELETE_ENV = ("ADMIN_PASSWORD_HASH",)


def test_login_dev_mode(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_refresh_token(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    tokens = login.json()
    refresh_payload = verify_token(tokens["refresh_token"], expected_type="refresh")

    assert refresh_payload is not None
    assert refresh_payload["role"] == "admin"

    resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    metrics = client.get(
        "/api/metrics",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert metrics.status_code == 200


def test_default_jwt_secret_has_minimum_length() -> None:
    assert len(JWT_SECRET.encode("utf-8")) >= 32


def test_protected_endpoint_with_jwt(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    token = login.json()["access_token"]

    resp = client.post(
        "/api/ask",
        json={"question": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code not in (401, 403)


def test_protected_endpoint_with_legacy_api_key(client: TestClient) -> None:
    resp = client.post(
        "/api/ask",
        json={"question": "test"},
        headers={"X-API-Key": "secret123"},
    )
    assert resp.status_code not in (401, 403)

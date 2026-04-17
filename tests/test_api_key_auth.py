from fastapi.testclient import TestClient


def test_ask_without_key_returns_401(client_with_key: TestClient) -> None:
    resp = client_with_key.post("/api/ask", json={"question": "test"})
    assert resp.status_code == 401


def test_ask_with_wrong_key_returns_403(client_with_key: TestClient) -> None:
    resp = client_with_key.post(
        "/api/ask",
        json={"question": "test"},
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 403


def test_ask_with_correct_key_passes_auth(client_with_key: TestClient) -> None:
    resp = client_with_key.post(
        "/api/ask",
        json={"question": "test"},
        headers={"X-API-Key": "secret123"},
    )
    assert resp.status_code not in (401, 403)

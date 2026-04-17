from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


@pytest.fixture
def _mock_critical_probes_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr(api_app, "_probe_ollama", _ok)
    monkeypatch.setattr(api_app, "_probe_chromadb", _ok)
    monkeypatch.setattr(api_app, "_probe_sqlite", _ok)


def test_health_returns_200_when_postgres_and_redis_ok(
    client: TestClient,
    _mock_critical_probes_ok,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr(api_app, "_probe_postgres", _ok, raising=False)
    monkeypatch.setattr(api_app, "_probe_redis", _ok, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "postgres" in body["components"]
    assert "redis" in body["components"]
    assert body["components"]["postgres"]["status"] == "ok"
    assert body["components"]["redis"]["status"] == "ok"


def test_health_returns_degraded_when_postgres_down(
    client: TestClient,
    _mock_critical_probes_ok,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    async def _fail(*args, **kwargs):
        return api_app.ComponentStatus(status="error", detail="connection refused")

    monkeypatch.setattr(api_app, "_probe_postgres", _fail, raising=False)
    monkeypatch.setattr(api_app, "_probe_redis", _ok, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["postgres"]["status"] == "error"


def test_health_returns_degraded_when_redis_down(
    client: TestClient,
    _mock_critical_probes_ok,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    async def _fail(*args, **kwargs):
        return api_app.ComponentStatus(status="error", detail="connection refused")

    monkeypatch.setattr(api_app, "_probe_postgres", _ok, raising=False)
    monkeypatch.setattr(api_app, "_probe_redis", _fail, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["redis"]["status"] == "error"


def test_health_unavailable_is_not_error(
    client: TestClient,
    _mock_critical_probes_ok,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unavailable(*args, **kwargs):
        return api_app.ComponentStatus(status="unavailable", detail="driver missing")

    monkeypatch.setattr(api_app, "_probe_postgres", _unavailable, raising=False)
    monkeypatch.setattr(api_app, "_probe_redis", _unavailable, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"]["postgres"]["status"] == "unavailable"
    assert body["components"]["redis"]["status"] == "unavailable"

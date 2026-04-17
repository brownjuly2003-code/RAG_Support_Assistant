from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def test_readiness_returns_503_when_shutting_down(
    monkeypatch,
    client: TestClient,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _ok)

    monkeypatch.setattr("api.app._shutting_down", True, raising=False)

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "shutting_down"


def test_health_alias_also_flips_when_shutting_down(
    monkeypatch,
    client: TestClient,
) -> None:
    async def _ok(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _ok)

    monkeypatch.setattr("api.app._shutting_down", True, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "shutting_down"


def test_liveness_stays_200_during_shutdown(
    monkeypatch,
    client: TestClient,
) -> None:
    monkeypatch.setattr("api.app._shutting_down", True, raising=False)

    response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"

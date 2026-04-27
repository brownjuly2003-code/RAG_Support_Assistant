from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def test_liveness_returns_200_and_alive(client: TestClient) -> None:
    response = client.get("/api/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "rag-support-assistant"


def test_dependency_health_routes_live_in_system_router() -> None:
    from api.routers import system

    routes = {route.path: route for route in system.router.routes}

    assert "/health" in routes
    assert "/health/ready" in routes
    assert routes["/health"].response_model is system.HealthResponse
    assert routes["/health/ready"].response_model is system.HealthResponse


def test_liveness_does_not_call_probes(monkeypatch, client: TestClient) -> None:
    calls: list[str] = []

    async def _spy_probe(*args, **kwargs):
        calls.append("called")
        return api_app.ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _spy_probe)

    response = client.get("/api/health/live")

    assert response.status_code == 200
    assert calls == []


def test_liveness_stays_200_when_dependencies_are_down(monkeypatch, client: TestClient) -> None:
    async def _fail(*args, **kwargs):
        return api_app.ComponentStatus(status="error", detail="down")

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _fail)

    live = client.get("/api/health/live")
    ready = client.get("/api/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503

import importlib

import pytest
from fastapi.testclient import TestClient
api_app = importlib.import_module("api.app")


def test_health_returns_200_when_all_probes_are_ok(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ollama_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=1.0)

    async def chroma_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=2.0)

    async def sqlite_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=3.0)

    monkeypatch.setattr(api_app, "_probe_ollama", ollama_probe)
    monkeypatch.setattr(api_app, "_probe_chromadb", chroma_probe)
    monkeypatch.setattr(api_app, "_probe_sqlite", sqlite_probe)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"]["ollama"]["status"] == "ok"
    assert body["components"]["chromadb"]["status"] == "ok"
    assert body["components"]["sqlite"]["status"] == "ok"


def test_health_returns_503_when_ollama_is_down(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ollama_probe(*args, **kwargs):
        return api_app.ComponentStatus(
            status="error",
            latency_ms=1.0,
            detail="Ollama unavailable",
        )

    async def chroma_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=2.0)

    async def sqlite_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=3.0)

    monkeypatch.setattr(api_app, "_probe_ollama", ollama_probe)
    monkeypatch.setattr(api_app, "_probe_chromadb", chroma_probe)
    monkeypatch.setattr(api_app, "_probe_sqlite", sqlite_probe)

    response = client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["components"]["ollama"]["status"] == "error"
    assert body["components"]["ollama"]["detail"] == "Ollama unavailable"


def test_health_returns_200_when_sqlite_is_degraded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ollama_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=1.0)

    async def chroma_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=2.0)

    async def sqlite_probe(*args, **kwargs):
        return api_app.ComponentStatus(
            status="error",
            latency_ms=3.0,
            detail="SQLite unavailable",
        )

    monkeypatch.setattr(api_app, "_probe_ollama", ollama_probe)
    monkeypatch.setattr(api_app, "_probe_chromadb", chroma_probe)
    monkeypatch.setattr(api_app, "_probe_sqlite", sqlite_probe)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["ollama"]["status"] == "ok"
    assert body["components"]["chromadb"]["status"] == "ok"
    assert body["components"]["sqlite"]["status"] == "error"
    assert body["components"]["sqlite"]["detail"] == "SQLite unavailable"


def test_health_returns_503_when_chromadb_is_down(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ollama_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=1.0)

    async def chroma_probe(*args, **kwargs):
        return api_app.ComponentStatus(
            status="error",
            latency_ms=2.0,
            detail="ChromaDB unavailable",
        )

    async def sqlite_probe(*args, **kwargs):
        return api_app.ComponentStatus(status="ok", latency_ms=3.0)

    monkeypatch.setattr(api_app, "_probe_ollama", ollama_probe)
    monkeypatch.setattr(api_app, "_probe_chromadb", chroma_probe)
    monkeypatch.setattr(api_app, "_probe_sqlite", sqlite_probe)

    response = client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["components"]["ollama"]["status"] == "ok"
    assert body["components"]["chromadb"]["status"] == "error"
    assert body["components"]["chromadb"]["detail"] == "ChromaDB unavailable"
    assert body["components"]["sqlite"]["status"] == "ok"

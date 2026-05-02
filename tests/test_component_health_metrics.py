from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROVIDER_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "providers.yml"
CLIENT_SETTINGS_OVERRIDES = {
    "llm_provider_profile": "local-first",
    "provider_registry_path": PROVIDER_REGISTRY_PATH,
}


def _get_gauge_value(component: str) -> float | None:
    from monitoring.prometheus import COMPONENT_UP, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in COMPONENT_UP.collect():
        for sample in metric.samples:
            if sample.labels.get("component") == component:
                return sample.value
    return None


@pytest.fixture
def _mock_all_probes_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _ok)


def test_record_component_health_sets_one_for_ok() -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_component_health("ollama", "ok")

    assert _get_gauge_value("ollama") == 1.0


def test_record_component_health_sets_zero_for_error() -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_component_health("postgres", "error")

    assert _get_gauge_value("postgres") == 0.0


def test_record_component_health_skips_unavailable() -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_component_health("new_unavailable_component", "unavailable")

    assert _get_gauge_value("new_unavailable_component") is None


def test_health_endpoint_updates_component_gauges(
    client: TestClient,
    _mock_all_probes_ok,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    response = client.get("/api/health")

    assert response.status_code == 200
    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        assert _get_gauge_value(name) == 1.0, f"{name} gauge not updated"


def test_health_endpoint_updates_gracekelly_gauge_when_profile_uses_gracekelly(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
) -> None:
    from api.app import ComponentStatus
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    settings = settings_factory(
        llm_provider_profile="gracekelly-primary",
        provider_registry_path=PROVIDER_REGISTRY_PATH,
        gracekelly_base_url="http://gracekelly.test",
        gracekelly_health_check_timeout_sec=1.0,
    )

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr("api.app.get_settings", lambda: settings)
    for name in ("gracekelly", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _ok, raising=False)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert _get_gauge_value("gracekelly") == 1.0

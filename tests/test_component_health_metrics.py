from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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

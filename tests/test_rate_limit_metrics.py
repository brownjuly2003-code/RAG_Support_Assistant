from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _get_counter_value(endpoint: str) -> float | None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, RATE_LIMIT_REJECTIONS

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in RATE_LIMIT_REJECTIONS.collect():
        for sample in metric.samples:
            if sample.labels.get("endpoint") != endpoint:
                continue
            if sample.name.endswith("_total"):
                return sample.value
    return None


def test_rejection_counter_increments_on_429(
    mock_pipeline,
    client: TestClient,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before = _get_counter_value("/api/ask") or 0.0

    last_status = None
    for _ in range(65):
        response = client.post("/api/ask", json={"question": "что?"})
        last_status = response.status_code
        if last_status == 429:
            break

    assert last_status == 429

    after = _get_counter_value("/api/ask") or 0.0
    assert after > before


def test_counter_labeled_by_endpoint(
    mock_pipeline,
    client: TestClient,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    for _ in range(65):
        response = client.post("/api/ask", json={"question": "маркер"})
        if response.status_code == 429:
            break

    assert _get_counter_value("/api/ask") not in (None, 0.0)
    assert _get_counter_value("/api/nonexistent-endpoint") in (None, 0.0)


def test_handler_does_not_crash_when_prometheus_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_pipeline,
    client: TestClient,
) -> None:
    def _boom(endpoint: str) -> None:
        raise RuntimeError("prometheus dead")

    monkeypatch.setattr("monitoring.prometheus.record_rate_limit_rejection", _boom)

    for _ in range(65):
        response = client.post("/api/ask", json={"question": "тест"})
        if response.status_code == 429:
            assert "detail" in response.json()
            assert "limit" in response.json()["detail"].lower()
            return

    pytest.fail("never hit 429")

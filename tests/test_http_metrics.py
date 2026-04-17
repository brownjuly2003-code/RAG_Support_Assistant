"""Tests for universal HTTP metrics middleware."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _counter_sum(endpoint_filter: str | None = None) -> float:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return 0.0

    total = 0.0
    for metric in HTTP_REQUESTS.collect():
        for sample in metric.samples:
            if not sample.name.endswith("_total"):
                continue
            if endpoint_filter and sample.labels.get("endpoint") != endpoint_filter:
                continue
            total += sample.value
    return total


def test_counter_increments_on_any_endpoint(client: TestClient) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before = _counter_sum("/api/health/live")
    client.get("/api/health/live")
    after = _counter_sum("/api/health/live")
    assert after > before


def test_labels_include_method_and_status(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    client.get("/api/health/live")

    found = False
    for metric in HTTP_REQUESTS.collect():
        for sample in metric.samples:
            if (
                sample.name.endswith("_total")
                and sample.labels.get("method") == "GET"
                and sample.labels.get("endpoint") == "/api/health/live"
                and sample.labels.get("status") == "200"
            ):
                found = True
                break

    assert found, "GET /api/health/live -> 200 missing in metrics"


def test_endpoint_uses_route_template_not_actual_path(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    response = client.get("/api/sessions/random-id-42/history")
    _ = response.status_code

    seen_endpoints: set[str] = set()
    for metric in HTTP_REQUESTS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                endpoint = sample.labels.get("endpoint", "")
                if "sessions" in endpoint:
                    seen_endpoints.add(endpoint)

    for endpoint in seen_endpoints:
        assert "random-id-42" not in endpoint, (
            f"actual path leaked into metric label: {endpoint}"
        )


def test_unknown_route_labeled_unknown(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    response = client.get("/wp-admin/login.php")
    assert response.status_code == 404

    found_unknown = False
    for metric in HTTP_REQUESTS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                endpoint = sample.labels.get("endpoint", "")
                assert "wp-admin" not in endpoint, (
                    f"scan traffic leaked into metric label: {endpoint}"
                )
                if endpoint == "unknown" and sample.labels.get("status") == "404":
                    found_unknown = True

    assert found_unknown, "404 unknown route missing endpoint=unknown metric"


def test_duration_histogram_observed(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUEST_DURATION, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    client.get("/api/health/live")

    found_count = False
    for metric in HTTP_REQUEST_DURATION.collect():
        for sample in metric.samples:
            if (
                sample.name.endswith("_count")
                and sample.labels.get("endpoint") == "/api/health/live"
                and sample.value > 0
            ):
                found_count = True
                break

    assert found_count, "histogram count was not incremented"

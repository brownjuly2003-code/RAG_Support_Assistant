from __future__ import annotations

import importlib
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")
CLIENT_RAISE_SERVER_EXCEPTIONS = False
CLIENT_WITH_KEY_RAISE_SERVER_EXCEPTIONS = False


MOCK_SNAPSHOT = {
    "latency": {"p50_sec": 1.5, "p95_sec": 8.2, "p99_sec": 14.0, "window": "24h"},
    "escalation": {"total_traces": 100, "escalated": 15, "rate_pct": 15.0, "window": "24h"},
    "quality": {"scored_traces": 90, "avg_quality": 78.5, "low_quality_share_pct": 10.0, "window": "7d"},
    "errors": {"total_started": 100, "likely_failed": 2, "likely_failure_rate_pct": 2.0, "window": "24h"},
    "feedback": {"total": 60, "thumbs_down": 8, "thumbs_down_rate_pct": 13.3, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}

EMPTY_SNAPSHOT = {
    "latency": {"p50_sec": None, "p95_sec": None, "p99_sec": None, "window": "24h"},
    "escalation": {"total_traces": 0, "escalated": 0, "rate_pct": None, "window": "24h"},
    "quality": {"scored_traces": 0, "avg_quality": None, "low_quality_share_pct": None, "window": "7d"},
    "errors": {"total_started": 0, "likely_failed": 0, "likely_failure_rate_pct": None, "window": "24h"},
    "feedback": {"total": 0, "thumbs_down": 0, "thumbs_down_rate_pct": None, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}


def _metric_value(metrics_text: str, name: str, labels: str = "") -> float | None:
    label_part = f"{{{labels}}}" if labels else ""
    match = re.search(
        rf"^{re.escape(name)}{re.escape(label_part)}\s+([0-9.e+-]+)$",
        metrics_text,
        re.MULTILINE,
    )
    if match is None:
        return None
    return float(match.group(1))


def test_metrics_returns_200(client: TestClient) -> None:
    with patch("tracing.sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    assert response.status_code == 200


def test_metrics_has_required_keys(client: TestClient) -> None:
    with patch("tracing.sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    data = response.json()
    for key in ("latency", "escalation", "quality", "errors", "feedback", "generated_at"):
        assert key in data


def test_metrics_latency_fields(client: TestClient) -> None:
    with patch("tracing.sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        response = client.get("/api/metrics")

    latency = response.json()["latency"]
    assert latency["p50_sec"] == 1.5
    assert latency["p95_sec"] == 8.2
    assert latency["window"] == "24h"


def test_metrics_empty_snapshot_returns_200(client: TestClient) -> None:
    with patch("tracing.sqlite_trace.get_metrics_snapshot", return_value=EMPTY_SNAPSHOT):
        response = client.get("/api/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["latency"]["p50_sec"] is None
    assert data["escalation"]["total_traces"] == 0


def test_metrics_error_fallback(client: TestClient) -> None:
    with patch("tracing.sqlite_trace.get_metrics_snapshot", side_effect=RuntimeError("db locked")):
        response = client.get("/api/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "db locked"
    assert data["generated_at"] == ""


def test_prometheus_metrics_endpoint_tracks_ask_requests(client: TestClient) -> None:
    before = client.get("/metrics")
    before_text = before.text
    before_requests = _metric_value(before_text, "rag_requests_total", 'route="human"') or 0.0
    before_duration = _metric_value(before_text, "rag_request_duration_seconds_count") or 0.0
    before_escalations = _metric_value(before_text, "rag_escalation_total") or 0.0

    ask_response = client.post("/api/ask", json={"question": "test question"})
    assert ask_response.status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    body = response.text
    assert (_metric_value(body, "rag_requests_total", 'route="human"') or 0.0) == before_requests + 1.0
    assert (_metric_value(body, "rag_request_duration_seconds_count") or 0.0) == before_duration + 1.0
    assert (_metric_value(body, "rag_escalation_total") or 0.0) == before_escalations + 1.0
    assert (_metric_value(body, "rag_active_sessions") or 0.0) >= 1.0


def test_prometheus_metrics_endpoint_tracks_feedback(client: TestClient) -> None:
    before = client.get("/metrics")
    before_feedback = _metric_value(before.text, "rag_feedback_total", 'rating="up"') or 0.0

    feedback_response = client.post(
        "/api/feedback",
        json={
            "trace_id": "trace-1",
            "session_id": "session-1",
            "rating": "up",
        },
    )
    assert feedback_response.status_code == 204

    response = client.get("/metrics")

    assert response.status_code == 200
    assert (_metric_value(response.text, "rag_feedback_total", 'rating="up"') or 0.0) == before_feedback + 1.0


def test_prometheus_metrics_endpoint_requires_no_auth_when_api_key_is_set(
    client_with_key: TestClient,
) -> None:
    response = client_with_key.get("/metrics")

    assert response.status_code == 200


def test_prometheus_metrics_endpoint_returns_501_when_client_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_app, "prometheus_metrics", SimpleNamespace(PROMETHEUS_AVAILABLE=False), raising=False)

    response = client.get("/metrics")

    assert response.status_code == 501

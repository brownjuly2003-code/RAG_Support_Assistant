from __future__ import annotations

import importlib
import threading
import time
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def _fake_slow_session_factory(sleep_sec: float):
    def _slow_ask(question: str, trace_id=None) -> dict:
        _ = question, trace_id
        time.sleep(sleep_sec)
        return {"answer": "ok", "quality_score": 75, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: ClassVar[list] = []

    return FakeSession


def _get_inflight_gauge_value() -> float | None:
    from monitoring.prometheus import INFLIGHT_PIPELINES, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in INFLIGHT_PIPELINES.collect():
        for sample in metric.samples:
            if sample.name == "rag_inflight_pipelines":
                return sample.value
    return 0.0


def _get_rejection_counter_value(reason: str) -> float | None:
    from monitoring.prometheus import PIPELINE_REJECTIONS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in PIPELINE_REJECTIONS.collect():
        for sample in metric.samples:
            if sample.labels.get("reason") != reason:
                continue
            if sample.name.endswith("_total"):
                return sample.value
    return 0.0


def test_saturated_pool_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            max_concurrent_pipelines=1,
            pipeline_acquire_timeout_sec=0.2,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0

    fake_session = _fake_slow_session_factory(0.8)
    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", fake_session()),
    )

    statuses: list[int] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            response = client.post("/api/ask", json={"question": "q"})
            statuses.append(response.status_code)
        except BaseException as exc:  # pragma: no cover - defensive for thread handoff
            errors.append(exc)

    first = threading.Thread(target=_worker)
    second = threading.Thread(target=_worker)
    first.start()
    time.sleep(0.05)
    second.start()
    first.join()
    second.join()

    assert errors == []
    assert 200 in statuses
    assert 503 in statuses
    assert statuses.count(503) == 1


def test_rejection_counter_increments(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            max_concurrent_pipelines=1,
            pipeline_acquire_timeout_sec=0.1,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0

    fake_session = _fake_slow_session_factory(0.5)
    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", fake_session()),
    )

    before = _get_rejection_counter_value("busy") or 0.0

    first = threading.Thread(
        target=lambda: client.post("/api/ask", json={"question": "q1"})
    )
    second = threading.Thread(
        target=lambda: client.post("/api/ask", json={"question": "q2"})
    )
    first.start()
    time.sleep(0.05)
    second.start()
    first.join()
    second.join()

    after = _get_rejection_counter_value("busy") or 0.0
    assert after > before


def test_inflight_gauge_decrements_after_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    api_app._db_retry_after = time.monotonic() + 60.0
    assert _get_inflight_gauge_value() == 0.0

    fake_session = _fake_slow_session_factory(0.1)
    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", fake_session()),
    )

    response = client.post("/api/ask", json={"question": "q"})

    assert response.status_code == 200
    assert _get_inflight_gauge_value() == 0.0


def test_inflight_gauge_decrements_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(request_timeout_sec=0.3),
    )
    api_app._db_retry_after = time.monotonic() + 60.0
    assert _get_inflight_gauge_value() == 0.0

    fake_session = _fake_slow_session_factory(1.0)
    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", fake_session()),
    )

    response = client.post("/api/ask", json={"question": "q"})

    assert response.status_code == 504
    assert _get_inflight_gauge_value() == 0.0

from __future__ import annotations

from typing import ClassVar

import importlib
import threading
import time

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def _get_timeout_counter_value(endpoint: str) -> float | None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, REQUEST_TIMEOUTS

    if not PROMETHEUS_AVAILABLE:
        return None

    for metric in REQUEST_TIMEOUTS.collect():
        for sample in metric.samples:
            if sample.labels.get("endpoint") != endpoint:
                continue
            if sample.name.endswith("_total"):
                return sample.value
    return None


def test_normal_request_passes(client: TestClient) -> None:
    response = client.post("/api/ask", json={"question": "быстрый вопрос"})

    assert response.status_code == 200
    assert response.json()["route"] in ("auto", "human")


def test_slow_pipeline_returns_504(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(request_timeout_sec=0.5),
    )

    def _slow_ask(question: str, trace_id=None) -> dict:
        _ = question, trace_id
        time.sleep(2.0)
        return {"answer": "never", "quality_score": 99, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: ClassVar[list] = []

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("test-sid", FakeSession()),
    )

    response = client.post("/api/ask", json={"question": "медленный вопрос"})

    assert response.status_code == 504
    assert "wall-time limit" in response.json()["detail"]


def test_timeout_counter_increments(
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

    def _slow_ask(question: str, trace_id=None) -> dict:
        _ = question, trace_id
        time.sleep(1.0)
        return {"answer": "x"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: ClassVar[list] = []

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", FakeSession()),
    )

    before = _get_timeout_counter_value("/api/ask") or 0.0

    response = client.post("/api/ask", json={"question": "timeout"})

    assert response.status_code == 504
    after = _get_timeout_counter_value("/api/ask") or 0.0
    assert after > before


def test_event_loop_not_blocked_during_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(request_timeout_sec=2.0),
    )
    api_app._db_retry_after = time.monotonic() + 60.0

    def _sync_ask(question: str, trace_id=None) -> dict:
        _ = question, trace_id
        time.sleep(0.4)
        return {"answer": "ok", "quality_score": 75, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_sync_ask)
        _history: ClassVar[list] = []

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda session_id: ("sid", FakeSession()),
    )

    results: dict[str, float | int] = {}
    errors: list[BaseException] = []

    def _worker_ask() -> None:
        t0 = time.monotonic()
        try:
            response = client.post("/api/ask", json={"question": "q"})
            results["ask_status"] = response.status_code
        except BaseException as exc:  # pragma: no cover - defensive for thread handoff
            errors.append(exc)
        finally:
            results["ask_time"] = time.monotonic() - t0

    def _worker_health() -> None:
        time.sleep(0.1)
        t0 = time.monotonic()
        try:
            response = client.get("/api/health/live")
            results["health_status"] = response.status_code
        except BaseException as exc:  # pragma: no cover - defensive for thread handoff
            errors.append(exc)
        finally:
            results["health_time"] = time.monotonic() - t0

    ask_thread = threading.Thread(target=_worker_ask)
    health_thread = threading.Thread(target=_worker_health)
    ask_thread.start()
    health_thread.start()
    ask_thread.join()
    health_thread.join()

    assert errors == []
    assert results["ask_status"] == 200
    assert results["health_status"] == 200
    assert results["health_time"] < 0.3

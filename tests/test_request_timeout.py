from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from typing import ClassVar

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

    def _slow_ask(question: str, trace_id=None, **kwargs) -> dict:
        _ = question, trace_id, kwargs
        time.sleep(2.0)
        return {"answer": "never", "quality_score": 99, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: ClassVar[list] = []

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("test-sid", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

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

    def _slow_ask(question: str, trace_id=None, **kwargs) -> dict:
        _ = question, trace_id, kwargs
        time.sleep(1.0)
        return {"answer": "x"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: ClassVar[list] = []

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("sid", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    before = _get_timeout_counter_value("/api/ask") or 0.0

    response = client.post("/api/ask", json={"question": "timeout"})

    assert response.status_code == 504
    after = _get_timeout_counter_value("/api/ask") or 0.0
    assert after > before


def test_timeout_logs_effective_budgets_and_evaluate_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import agent.graph as graph
    from agent.state import create_initial_state

    settings = settings_factory(
        request_timeout_sec=0.5,
        ask_budget_sec=0.0,
        ollama_request_timeout_sec=17.0,
        gracekelly_request_timeout_sec=29.0,
        llm_provider_profile="gracekelly-mixed",
    )
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "log_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph, "trace_llm_call", lambda *args, **kwargs: None)

    evaluate_entered = threading.Event()
    release_evaluate = threading.Event()
    evaluate_finished = threading.Event()

    class BlockingLLM:
        model_name = "diagnostic-model"

        def invoke(self, prompt: str) -> str:
            _ = prompt
            evaluate_entered.set()
            assert release_evaluate.wait(timeout=2.0)
            return "88"

    llm = BlockingLLM()

    def _blocking_ask(question: str, trace_id: str | None = None, **kwargs) -> dict:
        _ = kwargs
        state = create_initial_state(question=question, trace_id=trace_id)
        state["complexity"] = "simple"
        state["answer"] = "Диагностический ответ"
        try:
            return graph.make_evaluate_node(llm, llm)(state)
        finally:
            evaluate_finished.set()

    class FakeSession:
        ask = staticmethod(_blocking_ask)
        _history: ClassVar[list] = []

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        _ = session_id, tenant_id
        return ("timeout-observability", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    caplog.set_level(logging.INFO, logger="api.routers.conversation")
    caplog.set_level(logging.INFO, logger="agent.graph")

    try:
        response = client.post(
            "/api/ask",
            json={"question": "проверить границы timeout"},
            headers={"X-Request-Id": "timeout-observability-1"},
        )
    finally:
        release_evaluate.set()
        assert evaluate_finished.wait(timeout=2.0)

    assert response.status_code == 504
    assert evaluate_entered.is_set()

    effective_record = next(
        record for record in caplog.records if "effective_timeouts" in record.getMessage()
    )
    session_start_record = next(
        record
        for record in caplog.records
        if "session_setup boundary=start" in record.getMessage()
    )
    session_end_record = next(
        record
        for record in caplog.records
        if "session_setup boundary=end" in record.getMessage()
    )
    evaluate_start_record = next(
        record
        for record in caplog.records
        if "[evaluate] boundary=start" in record.getMessage()
    )
    outer_timeout_record = next(
        record for record in caplog.records if "outer_timeout_monotonic=" in record.getMessage()
    )
    evaluate_end_record = next(
        record
        for record in caplog.records
        if "[evaluate] boundary=end" in record.getMessage()
    )
    diagnostic_records = (
        effective_record,
        session_start_record,
        session_end_record,
        evaluate_start_record,
        outer_timeout_record,
        evaluate_end_record,
    )
    assert {
        getattr(record, "trace_id", None) for record in diagnostic_records
    } == {"timeout-observability-1"}

    effective = effective_record.getMessage()
    session_start = session_start_record.getMessage()
    session_end = session_end_record.getMessage()
    evaluate_start = evaluate_start_record.getMessage()
    outer_timeout = outer_timeout_record.getMessage()
    evaluate_end = evaluate_end_record.getMessage()

    assert "request=0.500s" in effective
    assert "ask_budget=0.000s" in effective
    assert "ollama_mistral=17.000s" in effective
    assert "gracekelly=29.000s" in effective
    assert "profile=gracekelly-mixed" in effective

    def _timestamp(message: str, key: str) -> float:
        match = re.search(rf"{key}=([0-9.]+)", message)
        assert match is not None
        return float(match.group(1))

    session_started_at = _timestamp(session_start, "monotonic")
    session_finished_at = _timestamp(session_end, "monotonic")
    started_at = _timestamp(evaluate_start, "monotonic")
    timed_out_at = _timestamp(outer_timeout, "outer_timeout_monotonic")
    finished_at = _timestamp(evaluate_end, "monotonic")

    assert session_started_at < session_finished_at <= started_at < timed_out_at < finished_at


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

    def _sync_ask(question: str, trace_id=None, **kwargs) -> dict:
        _ = question, trace_id, kwargs
        time.sleep(0.4)
        return {"answer": "ok", "quality_score": 75, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_sync_ask)
        _history: ClassVar[list] = []

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("sid", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

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

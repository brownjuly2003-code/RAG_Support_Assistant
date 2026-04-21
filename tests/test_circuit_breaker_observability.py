"""Tests for circuit breaker observability hooks and health payload."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import agent.graph as graph
from api import app as api_app
from utils.circuit_breaker import CircuitBreaker, CircuitState


def _boom() -> str:
    raise RuntimeError("x")


def test_on_state_change_fires_on_open() -> None:
    events: list[tuple[str, CircuitState, CircuitState]] = []

    def hook(name: str, old: CircuitState, new: CircuitState) -> None:
        events.append((name, old, new))

    cb = CircuitBreaker(
        failure_threshold=2,
        reset_timeout_sec=10,
        on_state_change=hook,
    )

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert events == []

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert events == [("ollama", CircuitState.CLOSED, CircuitState.OPEN)]


def test_on_state_change_fires_on_close_after_success() -> None:
    events: list[tuple[str, CircuitState, CircuitState]] = []

    def hook(name: str, old: CircuitState, new: CircuitState) -> None:
        events.append((name, old, new))

    cb = CircuitBreaker(
        failure_threshold=1,
        reset_timeout_sec=0.01,
        on_state_change=hook,
    )

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    time.sleep(0.02)

    assert cb.call(lambda: "ok") == "ok"
    assert events == [
        ("ollama", CircuitState.CLOSED, CircuitState.OPEN),
        ("ollama", CircuitState.OPEN, CircuitState.HALF_OPEN),
        ("ollama", CircuitState.HALF_OPEN, CircuitState.CLOSED),
    ]


def test_callback_exception_does_not_break_breaker() -> None:
    lock_states: list[bool] = []

    def bad_hook(*args: object) -> None:
        _ = args
        lock_states.append(cb._lock.locked())
        raise ValueError("hook failed")

    cb = CircuitBreaker(
        failure_threshold=1,
        reset_timeout_sec=10,
        on_state_change=bad_hook,
    )

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert lock_states == [False]
    assert cb.state == CircuitState.OPEN


def test_snapshot_returns_state_and_counters() -> None:
    cb = CircuitBreaker(failure_threshold=5, reset_timeout_sec=10, name="ollama")

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    snap = cb.snapshot()
    assert snap["name"] == "ollama"
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 1
    assert snap["opened_at_monotonic"] is None


def test_health_endpoint_includes_circuit_breaker_snapshot(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str, str]] = []

    async def ok_probe(*args: object, **kwargs: object) -> api_app.ComponentStatus:
        _ = args, kwargs
        return api_app.ComponentStatus(status="ok", latency_ms=1.0)

    monkeypatch.setattr(api_app, "_probe_ollama", ok_probe)
    monkeypatch.setattr(api_app, "_probe_chromadb", ok_probe)
    monkeypatch.setattr(api_app, "_probe_sqlite", ok_probe)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_reset_timeout_sec=30.0,
        ),
    )
    monkeypatch.setattr(
        "monitoring.prometheus.record_circuit_breaker_change",
        lambda name, from_state, to_state: events.append((name, from_state, to_state)),
    )
    monkeypatch.setattr(graph, "_default_breaker", None, raising=False)

    breaker = graph.get_default_breaker()
    assert breaker is not None
    with breaker._lock:
        breaker._state = CircuitState.OPEN
        breaker._opened_at = time.monotonic()

    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["circuit_breakers"] == [
        {
            "name": "ollama",
            "state": "open",
            "consecutive_failures": 0,
            "opened_at_monotonic": pytest.approx(breaker._opened_at),
        }
    ]
    assert events == [("ollama", "closed", "closed")]

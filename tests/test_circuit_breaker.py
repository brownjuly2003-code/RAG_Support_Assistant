"""Tests for the Ollama circuit breaker."""
from __future__ import annotations

import importlib
import time

import pytest

import agent.graph as graph
from utils.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def _boom() -> str:
    raise RuntimeError("ollama down")


def _ok() -> str:
    return "ok"


def test_initial_state_is_closed_and_reset_clears_state() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=10)

    assert cb.state == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_stays_closed_below_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=0.1)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)

    assert cb.state == CircuitState.CLOSED


def test_opens_after_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=0.1)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(_boom)

    assert cb.state == CircuitState.OPEN


def test_open_circuit_fast_fails() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=10)

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    calls: list[int] = []

    def tracker() -> str:
        calls.append(1)
        return "x"

    with pytest.raises(CircuitOpenError):
        cb.call(tracker)

    assert calls == []


def test_half_open_after_reset_timeout() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    time.sleep(0.06)

    assert cb.call(_ok) == "ok"
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    time.sleep(0.06)

    with pytest.raises(RuntimeError):
        cb.call(_boom)

    assert cb.state == CircuitState.OPEN


def test_success_resets_failure_counter() -> None:
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)

    assert cb.call(_ok) == "ok"

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)

    assert cb.state == CircuitState.CLOSED


def test_get_default_breaker_is_singleton_and_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import config.settings as settings_module

    monkeypatch.setenv("CIRCUIT_BREAKER_ENABLED", "true")
    monkeypatch.setenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("CIRCUIT_BREAKER_RESET_TIMEOUT_SEC", "0.5")
    settings_module = importlib.reload(settings_module)
    graph._default_breaker = None
    settings_module._settings = None

    first = graph.get_default_breaker()
    second = graph.get_default_breaker()

    assert first is second
    assert first is not None
    assert first.failure_threshold == 2
    assert first.reset_timeout_sec == pytest.approx(0.5)

    monkeypatch.setenv("CIRCUIT_BREAKER_ENABLED", "false")
    settings_module = importlib.reload(settings_module)
    graph._default_breaker = None
    settings_module._settings = None

    assert graph.get_default_breaker() is None


def test_local_ollama_llm_uses_breaker() -> None:
    class FakeLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            raise RuntimeError("ollama down")

    llm = graph.LocalOllamaLLM.__new__(graph.LocalOllamaLLM)
    llm._llm = FakeLLM()
    llm._breaker = CircuitBreaker(failure_threshold=2, reset_timeout_sec=10)

    with pytest.raises(RuntimeError):
        llm.invoke("hi")

    with pytest.raises(RuntimeError):
        llm.invoke("hi")

    with pytest.raises(CircuitOpenError):
        llm.invoke("hi")

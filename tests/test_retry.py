"""Tests for utils.retry."""
from __future__ import annotations

import pytest

import agent.graph as graph
from utils.retry import is_retryable_error, retry_with_backoff


class ConnectError(Exception):
    """Simulates httpx.ConnectError."""


class ReadTimeout(Exception):
    """Simulates httpx.ReadTimeout."""


class FatalError(Exception):
    """Non-retryable error."""


def test_is_retryable_matches_by_class_name() -> None:
    assert is_retryable_error(ConnectError("boom"))
    assert is_retryable_error(ReadTimeout("boom"))
    assert not is_retryable_error(FatalError("boom"))
    assert not is_retryable_error(ValueError("boom"))


def test_returns_value_on_first_success() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        return "ok"

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)

    assert wrapped() == "ok"
    assert calls["n"] == 1


def test_retries_transient_then_succeeds() -> None:
    seq = iter([ConnectError("x"), ReadTimeout("y"), "ok"])
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        value = next(seq)
        if isinstance(value, BaseException):
            raise value
        return value

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)

    assert wrapped() == "ok"
    assert calls["n"] == 3


def test_gives_up_after_max_attempts() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise ConnectError("nope")

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)

    with pytest.raises(ConnectError):
        wrapped()

    assert calls["n"] == 3


def test_does_not_retry_non_retryable() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise FatalError("bad request")

    wrapped = retry_with_backoff(fn, max_attempts=5, sleep=lambda _: None)

    with pytest.raises(FatalError):
        wrapped()

    assert calls["n"] == 1


def test_backoff_respects_base_and_cap_without_jitter() -> None:
    sleeps: list[float] = []

    def fn() -> str:
        raise ConnectError("x")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=4,
        base_delay_sec=1.0,
        max_delay_sec=3.0,
        jitter=False,
        sleep=sleeps.append,
    )

    with pytest.raises(ConnectError):
        wrapped()

    assert sleeps == [1.0, 2.0, 3.0]


def test_jitter_stays_within_half_to_max() -> None:
    sleeps: list[float] = []

    def fn() -> str:
        raise ConnectError("x")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=4,
        base_delay_sec=1.0,
        max_delay_sec=3.0,
        jitter=True,
        sleep=sleeps.append,
    )

    with pytest.raises(ConnectError):
        wrapped()

    assert len(sleeps) == 3
    assert 0.5 <= sleeps[0] <= 1.5
    assert 1.0 <= sleeps[1] <= 3.0
    assert 1.5 <= sleeps[2] <= 3.0


def test_max_attempts_one_is_single_call_no_sleep() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise ConnectError("x")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=1,
        sleep=sleeps.append,
        jitter=False,
    )

    with pytest.raises(ConnectError):
        wrapped()

    assert calls["n"] == 1
    assert sleeps == []


def test_local_ollama_llm_retries_transient() -> None:
    seq = iter([ConnectError("x"), ConnectError("y"), "answer"])

    class FakeLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            value = next(seq)
            if isinstance(value, BaseException):
                raise value
            return value

    llm = graph.LocalOllamaLLM.__new__(graph.LocalOllamaLLM)
    llm._llm = FakeLLM()
    llm._breaker = None
    llm._invoke_with_retry = retry_with_backoff(
        llm._llm.invoke,
        max_attempts=3,
        sleep=lambda _: None,
        jitter=False,
    )

    assert llm.invoke("q") == "answer"

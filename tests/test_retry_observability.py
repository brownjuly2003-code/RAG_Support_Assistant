"""Tests for retry observability hooks."""
from __future__ import annotations

import pytest

from utils.retry import retry_with_backoff


class ConnectError(Exception):
    """Transient error matched by class name."""


class _Fatal(Exception):
    """Non-retryable error."""


def test_success_first_try_emits_attempt_and_success() -> None:
    events: list[str] = []

    def fn() -> str:
        return "ok"

    wrapped = retry_with_backoff(
        fn,
        max_attempts=3,
        sleep=lambda _: None,
        on_event=events.append,
    )

    assert wrapped() == "ok"
    assert events == ["attempt", "success"]


def test_recovered_after_retries_emits_retry_sequence() -> None:
    seq = iter([ConnectError("x"), ConnectError("y"), "ok"])
    events: list[str] = []

    def fn() -> str:
        value = next(seq)
        if isinstance(value, BaseException):
            raise value
        return value

    wrapped = retry_with_backoff(
        fn,
        max_attempts=3,
        sleep=lambda _: None,
        on_event=events.append,
    )

    assert wrapped() == "ok"
    assert events == ["attempt", "retry", "attempt", "retry", "attempt", "success"]


def test_exhausted_emits_final_event() -> None:
    events: list[str] = []

    def fn() -> str:
        raise ConnectError("nope")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=3,
        sleep=lambda _: None,
        on_event=events.append,
    )

    with pytest.raises(ConnectError):
        wrapped()

    assert events == ["attempt", "retry", "attempt", "retry", "attempt", "exhausted"]
    assert events.count("success") == 0


def test_non_retryable_skips_exhausted_event() -> None:
    events: list[str] = []

    def fn() -> str:
        raise _Fatal("bad")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=5,
        sleep=lambda _: None,
        on_event=events.append,
    )

    with pytest.raises(_Fatal):
        wrapped()

    assert events == ["attempt"]


def test_callback_exception_does_not_break_retry() -> None:
    def bad_hook(event: str) -> None:
        _ = event
        raise ValueError("hook failed")

    def fn() -> str:
        return "ok"

    wrapped = retry_with_backoff(
        fn,
        max_attempts=3,
        sleep=lambda _: None,
        on_event=bad_hook,
    )

    assert wrapped() == "ok"

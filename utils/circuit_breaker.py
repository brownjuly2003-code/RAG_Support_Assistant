"""Minimal circuit breaker for Ollama calls."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout_sec: float = 30.0
    name: str = "ollama"

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_in_flight: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.monotonic() - self._opened_at >= self.reset_timeout_sec
            ):
                self._state = CircuitState.HALF_OPEN
                self._half_open_in_flight = False
            return self._state

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.monotonic() - self._opened_at >= self.reset_timeout_sec
            ):
                self._state = CircuitState.HALF_OPEN
                self._half_open_in_flight = False
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN; fast-failing to avoid cascading latency"
                )
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN; waiting for half-open probe result"
                    )
                self._half_open_in_flight = True
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def decorate(self, fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapped(*args, **kwargs) -> T:
            return self.call(fn, *args, **kwargs)

        return wrapped

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._half_open_in_flight = False
            if (
                self._state == CircuitState.HALF_OPEN
                or self._consecutive_failures >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = 0.0
            self._half_open_in_flight = False

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0
            self._half_open_in_flight = False

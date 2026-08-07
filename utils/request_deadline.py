"""Request-scoped cooperative deadline (plan §3.1b / REL-01).

Outer ``asyncio.wait_for`` and wall-budget only cancel the *wait* — worker
threads keep running. A ContextVar deadline lets provider (and later
retriever/tool) boundaries refuse to start new expensive work after the
request's wall clock has elapsed.

This is cooperative, not preemptive: an in-flight provider HTTP call is not
killed mid-socket. Callers that need hard capacity bounds still rely on
slice 3.1a (shared executor + hold semaphore until worker done).
"""
from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_deadline_var: contextvars.ContextVar["RequestDeadline | None"] = contextvars.ContextVar(
    "rag_request_deadline",
    default=None,
)


class RequestDeadlineExceeded(TimeoutError):
    """Raised when a cooperative request deadline has already elapsed."""

    def __init__(self, message: str, *, phase: str = "", source: str = "") -> None:
        super().__init__(message)
        self.phase = phase
        self.source = source


@dataclass(frozen=True, slots=True)
class RequestDeadline:
    """Monotonic wall deadline for one request/pipeline invocation."""

    expires_at: float
    source: str = "request"
    budget_sec: float = 0.0

    def remaining_sec(self, *, now: float | None = None) -> float:
        clock = time.monotonic() if now is None else now
        return max(0.0, self.expires_at - clock)

    def expired(self, *, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock >= self.expires_at

    def check(self, phase: str = "boundary") -> None:
        if self.expired():
            logger.warning(
                "Request deadline exceeded phase=%s source=%s budget_sec=%.3f",
                phase or "boundary",
                self.source,
                self.budget_sec,
            )
            raise RequestDeadlineExceeded(
                f"Request deadline exceeded at phase={phase or 'boundary'}",
                phase=phase or "boundary",
                source=self.source,
            )


def get_request_deadline() -> RequestDeadline | None:
    return _deadline_var.get()


def set_request_deadline(deadline: RequestDeadline | None) -> contextvars.Token:
    """Bind deadline for the current context; return reset token."""
    return _deadline_var.set(deadline)


def clear_request_deadline() -> None:
    _deadline_var.set(None)


def bind_request_deadline(
    timeout_sec: float | None,
    *,
    source: str = "request",
) -> RequestDeadline | None:
    """Bind a new deadline from a relative timeout; ``<=0`` / None clears."""
    if timeout_sec is None:
        clear_request_deadline()
        return None
    try:
        seconds = float(timeout_sec)
    except (TypeError, ValueError):
        clear_request_deadline()
        return None
    if seconds <= 0:
        clear_request_deadline()
        return None
    deadline = RequestDeadline(
        expires_at=time.monotonic() + seconds,
        source=source,
        budget_sec=seconds,
    )
    set_request_deadline(deadline)
    return deadline


def check_request_deadline(phase: str = "boundary") -> None:
    """Fail closed if a bound deadline has elapsed; no-op when unbound."""
    deadline = get_request_deadline()
    if deadline is None:
        return
    deadline.check(phase=phase)


def tighter_timeout_sec(*candidates: float | None) -> float:
    """Return the minimum positive timeout among candidates, or 0 if none."""
    positive: list[float] = []
    for raw in candidates:
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            positive.append(value)
    return min(positive) if positive else 0.0

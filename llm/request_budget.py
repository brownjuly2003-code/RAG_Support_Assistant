"""Per-request LLM call/token budget (plan §3.1e).

A single ContextVar budget is shared across retries, grading, fact claims,
agentic tools, and provider generate/stream paths. Exhaustion is fail-closed:
new provider work is refused and callers must not finish as route=``auto``.
"""
from __future__ import annotations

import contextvars
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_budget_var: contextvars.ContextVar["LLMRequestBudget | None"] = contextvars.ContextVar(
    "rag_llm_request_budget",
    default=None,
)


class LLMBudgetExceeded(RuntimeError):
    """Raised when the per-request LLM budget is exhausted."""

    def __init__(
        self,
        message: str,
        *,
        phase: str = "",
        reason: str = "exhausted",
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.reason = reason


@dataclass
class LLMRequestBudget:
    """Mutable counters for one request/pipeline invocation.

    Thread-safe so stream + parity worker can share one budget object (3.1f).
    """

    max_calls: int = 0
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_total_tokens: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    source: str = "request"
    _enabled: bool = field(default=True, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return int(self.input_tokens) + int(self.output_tokens)

    def snapshot(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "source": self.source,
                "calls": self.calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": int(self.input_tokens) + int(self.output_tokens),
                "max_calls": self.max_calls,
                "max_input_tokens": self.max_input_tokens,
                "max_output_tokens": self.max_output_tokens,
                "max_total_tokens": self.max_total_tokens,
            }

    def _limit_active(self, limit: int) -> bool:
        return int(limit) > 0

    def check_can_start_call(
        self,
        *,
        estimated_input_tokens: int = 0,
        phase: str = "provider",
    ) -> None:
        """Refuse a new provider call if any active limit is already exhausted."""
        if not self._enabled:
            return
        with self._lock:
            if self._limit_active(self.max_calls) and self.calls >= self.max_calls:
                self._raise("max_calls", phase=phase)
            est_in = max(0, int(estimated_input_tokens or 0))
            if self._limit_active(self.max_input_tokens) and (
                self.input_tokens + est_in > self.max_input_tokens
            ):
                self._raise("max_input_tokens", phase=phase)
            total = int(self.input_tokens) + int(self.output_tokens)
            if self._limit_active(self.max_total_tokens) and (
                total + est_in > self.max_total_tokens
            ):
                self._raise("max_total_tokens", phase=phase)
            # Output is unknown pre-call; still block if already at/over output caps.
            if self._limit_active(self.max_output_tokens) and (
                self.output_tokens >= self.max_output_tokens
            ):
                self._raise("max_output_tokens", phase=phase)

    def charge(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        phase: str = "provider",
    ) -> None:
        """Record one completed (or started) call and its token usage."""
        if not self._enabled:
            return
        with self._lock:
            self.calls += 1
            self.input_tokens += max(0, int(input_tokens or 0))
            self.output_tokens += max(0, int(output_tokens or 0))
            # Soft log when over after charge (call already happened).
            if self._limit_active(self.max_calls) and self.calls > self.max_calls:
                logger.warning(
                    "LLM budget over max_calls after charge phase=%s snapshot=%s",
                    phase,
                    {
                        "source": self.source,
                        "calls": self.calls,
                        "input_tokens": self.input_tokens,
                        "output_tokens": self.output_tokens,
                    },
                )

    def _raise(self, reason: str, *, phase: str) -> None:
        logger.warning(
            "LLM budget exceeded reason=%s phase=%s snapshot=%s",
            reason,
            phase,
            self.snapshot(),
        )
        raise LLMBudgetExceeded(
            f"LLM request budget exceeded ({reason}) at phase={phase}",
            phase=phase,
            reason=reason,
        )


def get_llm_request_budget() -> LLMRequestBudget | None:
    return _budget_var.get()


def set_llm_request_budget(budget: LLMRequestBudget | None) -> contextvars.Token:
    return _budget_var.set(budget)


def clear_llm_request_budget() -> None:
    _budget_var.set(None)


def bind_llm_request_budget(
    *,
    max_calls: int = 0,
    max_input_tokens: int = 0,
    max_output_tokens: int = 0,
    max_total_tokens: int = 0,
    source: str = "request",
) -> LLMRequestBudget | None:
    """Bind a new budget. All-zero limits mean tracking-disabled (no enforcement)."""
    limits = (max_calls, max_input_tokens, max_output_tokens, max_total_tokens)
    if all(int(x or 0) <= 0 for x in limits):
        clear_llm_request_budget()
        return None
    budget = LLMRequestBudget(
        max_calls=max(0, int(max_calls or 0)),
        max_input_tokens=max(0, int(max_input_tokens or 0)),
        max_output_tokens=max(0, int(max_output_tokens or 0)),
        max_total_tokens=max(0, int(max_total_tokens or 0)),
        source=source,
    )
    set_llm_request_budget(budget)
    return budget


def bind_llm_request_budget_from_settings(
    settings: Any | None = None,
    *,
    source: str = "request",
) -> LLMRequestBudget | None:
    if settings is None:
        try:
            from config.settings import get_settings

            settings = get_settings()
        except Exception:
            clear_llm_request_budget()
            return None
    return bind_llm_request_budget(
        max_calls=int(getattr(settings, "llm_max_calls_per_request", 0) or 0),
        max_input_tokens=int(getattr(settings, "llm_max_input_tokens_per_request", 0) or 0),
        max_output_tokens=int(getattr(settings, "llm_max_output_tokens_per_request", 0) or 0),
        max_total_tokens=int(getattr(settings, "llm_max_total_tokens_per_request", 0) or 0),
        source=source,
    )


def check_llm_request_budget(
    *,
    estimated_input_tokens: int = 0,
    phase: str = "provider",
) -> None:
    budget = get_llm_request_budget()
    if budget is None:
        return
    budget.check_can_start_call(
        estimated_input_tokens=estimated_input_tokens,
        phase=phase,
    )


def charge_llm_request_budget(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    phase: str = "provider",
) -> None:
    budget = get_llm_request_budget()
    if budget is None:
        return
    budget.charge(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        phase=phase,
    )

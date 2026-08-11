"""Single owner for the trace start/log/finish lifecycle."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from utils.pii import redact_pii


class TraceLifecycleBackend(Protocol):
    """Storage operations required by :class:`TraceService`."""

    def start_trace(
        self,
        trace_id: str | None = None,
        tenant_id: str = "default",
        *,
        correlation_id: str | None = None,
    ) -> str: ...

    def log_step(self, trace_id: str, node_name: str, state: Any) -> None: ...

    def finish_trace(self, trace_id: str, final_state: Any) -> None: ...


class TraceService:
    """Own trace lifecycle delegation and pre-persistence PII redaction."""

    def __init__(
        self,
        backend: TraceLifecycleBackend,
        *,
        redact_text: Callable[[str], str] = redact_pii,
    ) -> None:
        self._backend = backend
        self._redact_text = redact_text

    def start_trace(
        self,
        trace_id: str | None = None,
        tenant_id: str = "default",
        *,
        correlation_id: str | None = None,
    ) -> str:
        return self._backend.start_trace(
            trace_id,
            tenant_id,
            correlation_id=correlation_id,
        )

    def log_step(self, trace_id: str, node_name: str, state: Any) -> None:
        state_to_dict = getattr(self._backend, "_state_to_dict", None)
        if not callable(state_to_dict):
            self._backend.log_step(trace_id, node_name, state)
            return

        safe_state = state_to_dict(state)
        serialized = json.dumps(safe_state, ensure_ascii=False)
        redacted_state = json.loads(self._redact_text(serialized))
        self._backend.log_step(trace_id, node_name, redacted_state)

    def finish_trace(self, trace_id: str, final_state: Any) -> None:
        self._backend.finish_trace(trace_id, final_state)


__all__ = ["TraceLifecycleBackend", "TraceService"]

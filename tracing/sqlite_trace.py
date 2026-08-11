"""Canonical public API for SQLite tracing.

Wraps `tracing._base_trace` and adds PII redaction to `log_step`.
Production code must import from this module — the root-level
`sqlite_trace.py` shim is kept only for backward compatibility with
external consumers and emits a `DeprecationWarning` on use.
"""

from __future__ import annotations

from typing import Any

from tracing import _base_trace as _sqlite_trace
from tracing.service import TraceService

# Re-exports from _base_trace (canonical home) so that production code
# can rely on `tracing.sqlite_trace` as a stable public API.
list_recent_traces = _sqlite_trace.list_recent_traces
get_trace_detail = _sqlite_trace.get_trace_detail
purge_old_traces = _sqlite_trace.purge_old_traces
get_metrics_snapshot = _sqlite_trace.get_metrics_snapshot
save_feedback = _sqlite_trace.save_feedback
get_feedback_stats = _sqlite_trace.get_feedback_stats
_get_connection = _sqlite_trace._get_connection

trace_service = TraceService(_sqlite_trace)


def start_trace(
    trace_id: str | None = None,
    tenant_id: str = "default",
    *,
    correlation_id: str | None = None,
) -> str:
    """Start a trace through the shared lifecycle owner."""
    return trace_service.start_trace(
        trace_id,
        tenant_id,
        correlation_id=correlation_id,
    )


def log_step(trace_id: str, node_name: str, state: Any) -> None:
    """Log a step through the shared lifecycle owner."""
    trace_service.log_step(trace_id, node_name, state)


def finish_trace(trace_id: str, final_state: Any) -> None:
    """Finish a trace through the shared lifecycle owner."""
    trace_service.finish_trace(trace_id, final_state)


__all__ = [
    "start_trace",
    "finish_trace",
    "log_step",
    "list_recent_traces",
    "get_trace_detail",
    "purge_old_traces",
    "get_metrics_snapshot",
    "save_feedback",
    "get_feedback_stats",
]

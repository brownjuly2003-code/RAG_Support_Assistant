"""Canonical public API for SQLite tracing.

Wraps `tracing._base_trace` and adds PII redaction to `log_step`.
Production code must import from this module — the root-level
`sqlite_trace.py` shim is kept only for backward compatibility with
external consumers and emits a `DeprecationWarning` on use.
"""
from __future__ import annotations

import json as _json
from typing import Any

from tracing import _base_trace as _sqlite_trace

from utils.pii import redact_pii

# Re-exports from _base_trace (canonical home) so that production code
# can rely on `tracing.sqlite_trace` as a stable public API.
start_trace = _sqlite_trace.start_trace
finish_trace = _sqlite_trace.finish_trace
list_recent_traces = _sqlite_trace.list_recent_traces
get_trace_detail = _sqlite_trace.get_trace_detail
purge_old_traces = _sqlite_trace.purge_old_traces
get_metrics_snapshot = _sqlite_trace.get_metrics_snapshot
save_feedback = _sqlite_trace.save_feedback
get_feedback_stats = _sqlite_trace.get_feedback_stats
_get_connection = _sqlite_trace._get_connection


def log_step(trace_id: str, node_name: str, state: Any) -> None:
    """Persist a trace step after redacting PII in the state snapshot."""
    if not hasattr(_sqlite_trace, "_state_to_dict"):
        _sqlite_trace.log_step(trace_id, node_name, state)
        return

    safe_state = _sqlite_trace._state_to_dict(state)
    state_json = _json.dumps(safe_state, ensure_ascii=False)
    state_json = redact_pii(state_json)
    _sqlite_trace.log_step(trace_id, node_name, _json.loads(state_json))


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

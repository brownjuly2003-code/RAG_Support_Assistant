"""Tracing helpers with PII redaction for state snapshots."""
from __future__ import annotations

import json as _json
from typing import Any

import sqlite_trace as _sqlite_trace

from utils.pii import redact_pii

start_trace = _sqlite_trace.start_trace
finish_trace = _sqlite_trace.finish_trace


def log_step(trace_id: str, node_name: str, state: Any) -> None:
    """Persist a trace step after redacting PII in the state snapshot."""
    if not hasattr(_sqlite_trace, "_state_to_dict"):
        _sqlite_trace.log_step(trace_id, node_name, state)
        return

    safe_state = _sqlite_trace._state_to_dict(state)
    state_json = _json.dumps(safe_state, ensure_ascii=False)
    state_json = redact_pii(state_json)
    _sqlite_trace.log_step(trace_id, node_name, _json.loads(state_json))

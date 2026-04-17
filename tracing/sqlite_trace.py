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
    if not all(
        hasattr(_sqlite_trace, attr_name)
        for attr_name in ("_state_to_dict", "_now_iso", "_get_connection")
    ):
        _sqlite_trace.log_step(trace_id, node_name, state)
        return

    safe_state = _sqlite_trace._state_to_dict(state)
    state_json = _json.dumps(safe_state, ensure_ascii=False)
    state_json = redact_pii(state_json)
    ts = _sqlite_trace._now_iso()

    with _sqlite_trace._get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(step_order), -1) FROM trace_steps WHERE trace_id = ?",
            (trace_id,),
        )
        row = cur.fetchone()
        last_order = row[0] if row is not None else -1
        step_order = last_order + 1
        cur.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, step_order, node_name, state_json, ts),
        )
        conn.commit()

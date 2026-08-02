"""OBS-01: separate external request correlation from internal trace PK."""
from __future__ import annotations

import importlib
import importlib.util
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return parsed.version == 4


@pytest.fixture
def real_trace_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Load a fresh copy of tracing._base_trace against an isolated SQLite file."""
    import config.settings as settings_module

    source_path = Path(__file__).resolve().parent.parent / "tracing" / "_base_trace.py"
    module_path = tmp_path / "sqlite_trace_correlation.py"
    module_path.write_text(
        source_path.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )

    previous_module = sys.modules.pop("sqlite_trace_correlation", None)
    settings_module._settings = None
    monkeypatch.setenv("TRACING_DB_PATH", str(tmp_path / "traces.db"))

    spec = importlib.util.spec_from_file_location("sqlite_trace_correlation", module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules["sqlite_trace_correlation"] = module
    spec.loader.exec_module(module)

    try:
        yield module
    finally:
        sys.modules.pop("sqlite_trace_correlation", None)
        if previous_module is not None:
            sys.modules["sqlite_trace_correlation"] = previous_module
        settings_module._settings = None


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    return [row[2] for row in conn.execute(f"PRAGMA index_info('{index_name}')").fetchall()]


def _correlation_indexes(conn: sqlite3.Connection) -> list[str]:
    names: list[str] = []
    for row in conn.execute("PRAGMA index_list(traces)").fetchall():
        index_name = row[1]
        cols = _index_columns(conn, index_name)
        if cols == ["correlation_id"]:
            names.append(index_name)
    return names


def test_start_trace_same_correlation_yields_distinct_internal_ids(
    real_trace_module,
) -> None:
    correlation = "client-retry-corr-001"
    tenant = "acme-corp"

    first = real_trace_module.start_trace(
        correlation_id=correlation,
        tenant_id=tenant,
    )
    second = real_trace_module.start_trace(
        correlation_id=correlation,
        tenant_id=tenant,
    )

    assert first != second
    assert _is_uuid4(first)
    assert _is_uuid4(second)

    with sqlite3.connect(str(real_trace_module._get_db_path())) as conn:
        rows = conn.execute(
            """
            SELECT trace_id, correlation_id, tenant_id
            FROM traces
            WHERE correlation_id = ?
            ORDER BY started_at, trace_id
            """,
            (correlation,),
        ).fetchall()

    assert len(rows) == 2
    assert {rows[0][0], rows[1][0]} == {first, second}
    assert rows[0][1] == correlation
    assert rows[1][1] == correlation
    assert rows[0][2] == tenant
    assert rows[1][2] == tenant


def test_legacy_trace_id_alias_is_correlation_not_primary_key(
    real_trace_module,
) -> None:
    external = "legacy-external-req-42"

    internal = real_trace_module.start_trace(trace_id=external)

    assert internal != external
    assert _is_uuid4(internal)

    with sqlite3.connect(str(real_trace_module._get_db_path())) as conn:
        row = conn.execute(
            """
            SELECT trace_id, correlation_id
            FROM traces
            WHERE trace_id = ?
            """,
            (internal,),
        ).fetchone()
        collision = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE trace_id = ?",
            (external,),
        ).fetchone()[0]

    assert row is not None
    assert row[0] == internal
    assert row[1] == external
    assert collision == 0


def test_conflicting_correlation_and_legacy_alias_raise(
    real_trace_module,
) -> None:
    with pytest.raises(ValueError, match="correlation"):
        real_trace_module.start_trace(
            trace_id="ext-a",
            correlation_id="ext-b",
        )


def test_equal_correlation_and_legacy_alias_accepted(
    real_trace_module,
) -> None:
    external = "same-external-id"
    internal = real_trace_module.start_trace(
        trace_id=external,
        correlation_id=external,
    )
    assert _is_uuid4(internal)

    with sqlite3.connect(str(real_trace_module._get_db_path())) as conn:
        row = conn.execute(
            "SELECT correlation_id FROM traces WHERE trace_id = ?",
            (internal,),
        ).fetchone()
    assert row == (external,)


def test_init_db_migrates_old_traces_table_and_indexes_correlation(
    real_trace_module,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-traces.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE traces (
                trace_id        TEXT PRIMARY KEY,
                started_at      TEXT NOT NULL,
                finished_at     TEXT,
                tenant_id       TEXT NOT NULL DEFAULT 'default',
                final_route     TEXT,
                final_quality   INTEGER,
                final_relevance REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO traces (
                trace_id, started_at, finished_at, tenant_id,
                final_route, final_quality, final_relevance
            ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL)
            """,
            ("historic-internal-1", "2020-01-01T00:00:00+00:00", "default"),
        )
        conn.commit()

    original_get_db_path = real_trace_module._get_db_path
    try:
        real_trace_module._get_db_path = lambda: db_path
        real_trace_module._init_db()
    finally:
        real_trace_module._get_db_path = original_get_db_path

    with sqlite3.connect(str(db_path)) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(traces)").fetchall()]
        historic = conn.execute(
            "SELECT correlation_id FROM traces WHERE trace_id = ?",
            ("historic-internal-1",),
        ).fetchone()
        corr_indexes = _correlation_indexes(conn)

    assert "correlation_id" in columns
    assert columns[-1] == "correlation_id"
    assert historic == (None,)
    assert corr_indexes, "expected an index whose indexed column is exactly correlation_id"


def test_list_and_detail_expose_correlation_id(real_trace_module) -> None:
    correlation = "list-detail-corr"
    tenant = "tenant-list"
    internal = real_trace_module.start_trace(
        correlation_id=correlation,
        tenant_id=tenant,
    )

    recent = real_trace_module.list_recent_traces(limit=10, tenant_id=tenant)
    assert len(recent) == 1
    assert recent[0]["trace_id"] == internal
    assert recent[0]["correlation_id"] == correlation
    assert "started_at" in recent[0]
    assert "finished_at" in recent[0]

    foreign = real_trace_module.list_recent_traces(limit=10, tenant_id="other-tenant")
    assert foreign == []

    detail = real_trace_module.get_trace_detail(internal, tenant_id=tenant)
    assert detail is not None
    assert detail["trace_id"] == internal
    assert detail["correlation_id"] == correlation
    assert "started_at" in detail
    assert "finished_at" in detail
    assert "steps" in detail
    assert "feedback" in detail

    assert (
        real_trace_module.get_trace_detail(internal, tenant_id="other-tenant") is None
    )


def test_graph_boundary_passes_correlation_uses_internal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_module = importlib.import_module("agent.graph")
    seen: dict[str, Any] = {}

    def _start_trace(
        trace_id: str | None = None,
        tenant_id: str = "default",
        *,
        correlation_id: str | None = None,
    ) -> str:
        seen["trace_id_arg"] = trace_id
        seen["correlation_id"] = correlation_id
        seen["tenant_id"] = tenant_id
        return "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

    class FakeGraph:
        def invoke(self, state):
            seen["state"] = dict(state)
            return state

    monkeypatch.setattr(graph_module, "start_trace", _start_trace)
    monkeypatch.setattr(graph_module, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph_module, "build_support_graph", lambda **kwargs: FakeGraph())

    result = graph_module.run_qa_pipeline(
        question="hello?",
        retriever=object(),
        trace_id="external-request-77",
        tenant_id="acme",
    )

    assert seen["correlation_id"] == "external-request-77"
    assert seen["trace_id_arg"] is None
    assert seen["tenant_id"] == "acme"
    assert seen["state"]["trace_id"] == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    assert result["trace_id"] == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def test_start_trace_for_request_positional_only_legacy_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy positional-only stubs must not receive trace_id= as a keyword."""
    graph_module = importlib.import_module("agent.graph")
    seen: dict[str, Any] = {}

    def legacy_start_trace(trace_id=None, /):
        seen["args"] = (trace_id,)
        return "pos-only-internal-id"

    monkeypatch.setattr(graph_module, "start_trace", legacy_start_trace)

    result = graph_module._start_trace_for_request(
        "ext-pos-only-legacy-1",
        tenant_id="acme",
    )

    assert result == "pos-only-internal-id"
    assert seen["args"] == ("ext-pos-only-legacy-1",)


def test_api_ask_repeated_request_id_creates_distinct_traces(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Two /api/ask with the same X-Request-Id must both succeed with distinct PKs.

    Fake session isolates RAG/provider work, but still calls the real SQLite
    ``start_trace`` so a PK-collision on the external id would surface here.
    """
    import config.settings as settings_module
    import tracing._base_trace as base_trace

    api_app = importlib.import_module("api.app")
    db_path = tmp_path / "api-traces.db"
    original_get_db_path = base_trace._get_db_path
    monkeypatch.setenv("TRACING_DB_PATH", str(db_path))
    settings_module._settings = None
    # Fixture-managed: pytest restores the original getter at teardown.
    monkeypatch.setattr(base_trace, "_get_db_path", lambda: db_path)
    assert base_trace._get_db_path is not original_get_db_path
    base_trace._init_db()

    class _RealTraceSession:
        def ask(
            self,
            question: str,
            trace_id: str | None = None,
            tenant_id: str = "default",
            **kwargs: Any,
        ) -> dict[str, Any]:
            _ = question, kwargs
            # Mirror production boundary: external request id → correlation.
            internal = base_trace.start_trace(
                correlation_id=trace_id,
                tenant_id=tenant_id,
            )
            return {
                "answer": "ok",
                "quality_score": 90,
                "route": "auto",
                "graded_docs": [],
                "trace_id": internal,
                "suggested_questions": [],
            }

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        _ = session_id, tenant_id
        return ("00000000-0000-0000-0000-000000000099", _RealTraceSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    external = "retry-same-request-id-01"
    headers = {
        "Authorization": f"Bearer {create_access_token('u1', 'admin', 'acme')}",
        "X-Request-Id": external,
    }

    first = client.post("/api/ask", json={"question": "q1"}, headers=headers)
    second = client.post("/api/ask", json={"question": "q2"}, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.headers["X-Request-Id"] == external
    assert second.headers["X-Request-Id"] == external

    first_trace = first.json()["trace_id"]
    second_trace = second.json()["trace_id"]
    assert first_trace != second_trace
    assert _is_uuid4(first_trace)
    assert _is_uuid4(second_trace)
    assert first_trace != external
    assert second_trace != external

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT trace_id, correlation_id
            FROM traces
            WHERE correlation_id = ?
            ORDER BY started_at, trace_id
            """,
            (external,),
        ).fetchall()

    assert len(rows) == 2
    assert {rows[0][0], rows[1][0]} == {first_trace, second_trace}
    assert rows[0][1] == external
    assert rows[1][1] == external

    # Same restore path pytest uses on fixture teardown — no process-global leak.
    monkeypatch.undo()
    assert base_trace._get_db_path is original_get_db_path

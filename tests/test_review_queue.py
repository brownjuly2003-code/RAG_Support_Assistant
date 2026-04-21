from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant: str = "default", role: str = "admin", user_id: str | None = None) -> dict[str, str]:
    subject = user_id or str(uuid.uuid4())
    return {"Authorization": f"Bearer {create_access_token(subject, role, tenant)}"}


def _init_trace_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE traces (
                trace_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                tenant_id TEXT NOT NULL,
                final_route TEXT,
                final_quality REAL,
                final_relevance REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                state_json TEXT,
                ts TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                session_id TEXT,
                rating TEXT,
                reason TEXT,
                ts TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _insert_trace(
    db_path: Path,
    trace_id: str,
    *,
    tenant_id: str = "default",
    days_ago: int = 1,
    final_route: str = "auto",
    final_quality: float | None = 85,
    steps: list[dict[str, object]] | None = None,
    feedback: list[str] | None = None,
) -> None:
    started_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    finished_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces (
                trace_id,
                started_at,
                finished_at,
                tenant_id,
                final_route,
                final_quality,
                final_relevance
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trace_id, started_at, finished_at, tenant_id, final_route, final_quality, None),
        )
        for index, state in enumerate(steps or [{}]):
            conn.execute(
                """
                INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trace_id, index, f"step-{index}", json.dumps(state), started_at),
            )
        for rating in feedback or []:
            conn.execute(
                """
                INSERT INTO feedback (trace_id, session_id, rating, reason, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trace_id, f"session-{trace_id}", rating, "", started_at),
            )
        conn.commit()


class _Result:
    def __init__(self, rows: list[dict[str, object]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _BuilderSession:
    def __init__(self) -> None:
        self.traces: dict[str, dict[str, object]] = {}
        self.review_rows: list[dict[str, object]] = []

    async def __aenter__(self) -> "_BuilderSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        data = params or {}
        if "INSERT INTO traces" in sql:
            trace_id = str(data["trace_id"])
            if trace_id in self.traces:
                return _Result(rowcount=0)
            self.traces[trace_id] = dict(data)
            return _Result(rowcount=1)
        if "INSERT INTO review_queue" in sql:
            trace_id = str(data["trace_id"])
            if any(row["trace_id"] == trace_id for row in self.review_rows):
                return _Result(rowcount=0)
            self.review_rows.append(
                {
                    "id": len(self.review_rows) + 1,
                    "trace_id": trace_id,
                    "tenant_id": str(data["tenant_id"]),
                    "reason": str(data["reason"]),
                    "status": str(data["status"]),
                }
            )
            return _Result(rowcount=1)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


class _ApiSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def __aenter__(self) -> "_ApiSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        data = params or {}
        if "SELECT id, trace_id, tenant_id, reason, status" in sql:
            tenant_id = str(data["tenant_id"])
            status = data.get("status")
            reason = data.get("reason")
            limit = int(data["limit"])
            offset = int(data["offset"])
            filtered = [
                dict(row)
                for row in self.rows
                if row["tenant_id"] == tenant_id
                and (status is None or row["status"] == status)
                and (reason is None or row["reason"] == reason)
            ]
            filtered.sort(key=lambda row: str(row["created_at"]), reverse=True)
            return _Result(rows=filtered[offset:offset + limit])
        if "UPDATE review_queue" in sql:
            review_id = int(data["review_id"])
            tenant_id = str(data["tenant_id"])
            for row in self.rows:
                if row["id"] == review_id and row["tenant_id"] == tenant_id:
                    row["status"] = data["status"]
                    row["reviewer_notes"] = data["reviewer_notes"]
                    row["reviewed_by"] = data["reviewed_by"]
                    row["reviewed_at"] = data["reviewed_at"]
                    return _Result(rowcount=1)
            return _Result(rowcount=0)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


def test_review_queue_migration_upgrade_creates_table_and_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "012_review_queue.py"
    )
    spec = importlib.util.spec_from_file_location("migration_012_review_queue", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    enum_events: list[tuple[str, str]] = []
    table_calls: list[str] = []
    index_calls: list[tuple[str, tuple[str, ...]]] = []

    class _FakeEnum:
        def __init__(self, *values: str, name: str) -> None:
            self.values = values
            self.name = name

        def create(self, bind, checkfirst: bool = True) -> None:
            _ = bind, checkfirst
            enum_events.append(("create", self.name))

        def drop(self, bind, checkfirst: bool = True) -> None:
            _ = bind, checkfirst
            enum_events.append(("drop", self.name))

    monkeypatch.setattr(module.postgresql, "ENUM", _FakeEnum)
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.op, "create_table", lambda name, *args, **kwargs: table_calls.append(name))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table_name, columns, **kwargs: index_calls.append((table_name, tuple(columns))),
    )

    module.upgrade()

    assert ("create", "review_queue_reason") in enum_events
    assert ("create", "review_queue_status") in enum_events
    assert table_calls == ["review_queue"]
    assert ("review_queue", ("tenant_id", "status", "created_at")) in index_calls


def test_review_queue_migration_downgrade_drops_table_and_enums(monkeypatch: pytest.MonkeyPatch) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "012_review_queue.py"
    )
    spec = importlib.util.spec_from_file_location("migration_012_review_queue", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events: list[tuple[str, str]] = []

    class _FakeEnum:
        def __init__(self, *values: str, name: str) -> None:
            self.name = name

        def create(self, bind, checkfirst: bool = True) -> None:
            _ = bind, checkfirst

        def drop(self, bind, checkfirst: bool = True) -> None:
            _ = bind, checkfirst
            events.append(("drop_enum", self.name))

    monkeypatch.setattr(module.postgresql, "ENUM", _FakeEnum)
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.op, "drop_index", lambda name, table_name=None: events.append(("drop_index", name)))
    monkeypatch.setattr(module.op, "drop_table", lambda name: events.append(("drop_table", name)))

    module.downgrade()

    assert ("drop_index", "ix_review_queue_tenant_status_created_at") in events
    assert ("drop_table", "review_queue") in events
    assert ("drop_enum", "review_queue_status") in events
    assert ("drop_enum", "review_queue_reason") in events


def test_build_review_queue_adds_low_quality_trace(tmp_path: Path) -> None:
    from scripts import build_review_queue

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(db_path, "trace-low-quality", tenant_id="acme", final_quality=40)

    session = _BuilderSession()
    settings = SimpleNamespace(
        tracing_db_path=db_path,
        quality_threshold=80,
        fact_verification_enabled=True,
        fact_verification_min_score=70,
        slow_trace_threshold_ms=10000,
        review_queue_enabled=True,
    )

    result = asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert result["inserted"] == 1
    assert session.review_rows == [
        {
            "id": 1,
            "trace_id": "trace-low-quality",
            "tenant_id": "acme",
            "reason": "low_quality",
            "status": "pending",
        }
    ]


def test_build_review_queue_skips_normal_quality_trace(tmp_path: Path) -> None:
    from scripts import build_review_queue

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(db_path, "trace-good", tenant_id="acme", final_quality=95)

    session = _BuilderSession()
    settings = SimpleNamespace(
        tracing_db_path=db_path,
        quality_threshold=80,
        fact_verification_enabled=True,
        fact_verification_min_score=70,
        slow_trace_threshold_ms=10000,
        review_queue_enabled=True,
    )

    result = asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert result["inserted"] == 0
    assert session.review_rows == []


def test_build_review_queue_is_idempotent(tmp_path: Path) -> None:
    from scripts import build_review_queue

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(db_path, "trace-idempotent", tenant_id="acme", final_quality=30)

    session = _BuilderSession()
    settings = SimpleNamespace(
        tracing_db_path=db_path,
        quality_threshold=80,
        fact_verification_enabled=True,
        fact_verification_min_score=70,
        slow_trace_threshold_ms=10000,
        review_queue_enabled=True,
    )

    first = asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )
    second = asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert len(session.review_rows) == 1


def test_build_review_queue_marks_escalated_trace(tmp_path: Path) -> None:
    from scripts import build_review_queue

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(db_path, "trace-escalated", tenant_id="acme", final_quality=90, final_route="human")

    session = _BuilderSession()
    settings = SimpleNamespace(
        tracing_db_path=db_path,
        quality_threshold=80,
        fact_verification_enabled=True,
        fact_verification_min_score=70,
        slow_trace_threshold_ms=10000,
        review_queue_enabled=True,
    )

    asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert session.review_rows[0]["reason"] == "escalated"


def test_build_review_queue_marks_slow_trace(tmp_path: Path) -> None:
    from scripts import build_review_queue

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "trace-slow",
        tenant_id="acme",
        final_quality=90,
        steps=[{"duration_ms": 15001}],
    )

    session = _BuilderSession()
    settings = SimpleNamespace(
        tracing_db_path=db_path,
        quality_threshold=80,
        fact_verification_enabled=True,
        fact_verification_min_score=70,
        slow_trace_threshold_ms=10000,
        review_queue_enabled=True,
    )

    asyncio.run(
        build_review_queue.run_once(
            days=7,
            tenant="all",
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert session.review_rows[0]["reason"] == "slow_trace"


def test_admin_review_queue_endpoint_filters_by_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    db_path = tmp_path / "traces.db"
    _init_trace_db(db_path)
    _insert_trace(db_path, "trace-acme", tenant_id="acme", final_quality=45, steps=[{"duration_ms": 1234}])
    _insert_trace(db_path, "trace-beta", tenant_id="beta", final_quality=20, steps=[{"duration_ms": 9999}])

    settings = api_app.get_settings()
    settings.tracing_db_path = db_path
    settings.review_queue_enabled = True

    rows = [
        {
            "id": 1,
            "trace_id": "trace-acme",
            "tenant_id": "acme",
            "reason": "low_quality",
            "status": "pending",
            "reviewer_notes": "",
            "created_at": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc).isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
        },
        {
            "id": 2,
            "trace_id": "trace-beta",
            "tenant_id": "beta",
            "reason": "low_quality",
            "status": "pending",
            "reviewer_notes": "",
            "created_at": datetime(2026, 4, 21, 11, 0, tzinfo=timezone.utc).isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
        },
    ]

    monkeypatch.setattr("db.engine.async_session", lambda: _ApiSession(rows))
    monkeypatch.setattr(api_app, "_refresh_review_queue_metrics", lambda tenant: asyncio.sleep(0), raising=False)

    response = client_with_key.get(
        "/api/admin/review-queue?status=pending&limit=10",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["trace_id"] == "trace-acme"
    assert body["items"][0]["tenant_id"] == "acme"
    assert body["items"][0]["quality"] == 45.0
    assert body["items"][0]["duration_ms"] == 1234


def test_admin_review_queue_post_updates_status_and_reviewer(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.review_queue_enabled = True

    reviewer_id = str(uuid.uuid4())
    rows = [
        {
            "id": 7,
            "trace_id": "trace-7",
            "tenant_id": "acme",
            "reason": "low_quality",
            "status": "pending",
            "reviewer_notes": "",
            "created_at": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc).isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
        }
    ]

    monkeypatch.setattr("db.engine.async_session", lambda: _ApiSession(rows))
    monkeypatch.setattr(api_app, "_refresh_review_queue_metrics", lambda tenant: asyncio.sleep(0), raising=False)

    response = client_with_key.post(
        "/api/admin/review-queue/7",
        headers=_token("acme", "admin", reviewer_id),
        json={
            "status": "confirmed_bad",
            "reviewer_notes": "hallucinated refund policy",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert rows[0]["status"] == "confirmed_bad"
    assert rows[0]["reviewer_notes"] == "hallucinated refund policy"
    assert rows[0]["reviewed_by"] == reviewer_id
    assert rows[0]["reviewed_at"] is not None

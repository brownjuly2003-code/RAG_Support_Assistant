from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


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
        conn.commit()


def _insert_trace(
    db_path: Path,
    trace_id: str,
    *,
    tenant_id: str,
    final_route: str,
    final_quality: int,
    states: list[dict[str, object]],
) -> None:
    started_at = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc).isoformat()
    finished_at = datetime(2026, 4, 21, 10, 1, tzinfo=timezone.utc).isoformat()
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
        for index, state in enumerate(states):
            conn.execute(
                """
                INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trace_id, index, f"step-{index}", json.dumps(state), started_at),
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

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(
        self,
        review_rows: list[dict[str, object]],
        *,
        users: dict[str, str] | None = None,
    ) -> None:
        self.review_rows = review_rows
        self.users = users or {}
        self.commit_count = 0

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        data = params or {}

        if "SELECT id, trace_id, tenant_id, reason, status, created_at" in sql:
            filtered = [dict(row) for row in self.review_rows]
            status = data.get("status")
            tenant_id = data.get("tenant_id")
            if status is not None:
                filtered = [row for row in filtered if row["status"] == status]
            if tenant_id is not None:
                filtered = [row for row in filtered if row["tenant_id"] == tenant_id]
            filtered.sort(key=lambda row: str(row["created_at"]), reverse=True)
            return _Result(rows=filtered[: int(data["limit"])])

        if "SELECT id FROM users" in sql:
            username = str(data["username"]).lower()
            user_id = self.users.get(username)
            if user_id is None:
                return _Result(rows=[])
            return _Result(rows=[{"id": user_id}])

        if "SELECT id, tenant_id, status FROM review_queue" in sql:
            review_id = int(data["review_id"])
            tenant_id = str(data["tenant_id"])
            rows = [
                {
                    "id": row["id"],
                    "tenant_id": row["tenant_id"],
                    "status": row["status"],
                }
                for row in self.review_rows
                if int(row["id"]) == review_id and str(row["tenant_id"]) == tenant_id
            ]
            return _Result(rows=rows)

        if "UPDATE review_queue" in sql:
            review_id = int(data["review_id"])
            tenant_id = str(data["tenant_id"])
            for row in self.review_rows:
                if int(row["id"]) == review_id and str(row["tenant_id"]) == tenant_id and row["status"] == "pending":
                    row["status"] = data["status"]
                    row["reviewer_notes"] = data["reviewer_notes"]
                    row["reviewed_by"] = data["reviewed_by"]
                    row["reviewed_at"] = data["reviewed_at"]
                    return _Result(rowcount=1)
            return _Result(rowcount=0)

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        self.commit_count += 1


def test_review_export_creates_expected_jsonl_structure(tmp_path: Path) -> None:
    from scripts import review_export

    db_path = tmp_path / "traces.db"
    out_path = tmp_path / "review_batch.jsonl"
    exported_at = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "trace-1",
        tenant_id="acme",
        final_route="auto",
        final_quality=65,
        states=[
            {
                "question": "How do I reset my password?",
                "context_docs": [
                    {
                        "page_content": "Open Settings > Security > Reset password.",
                        "metadata": {"title": "Password Reset", "source": "kb://reset"},
                    }
                ],
            },
            {
                "question": "How do I reset my password?",
                "answer": "Open Settings > Security > Reset password. [1]",
                "route": "auto",
                "quality_score": 65,
                "factuality_score": 72,
                "duration_ms": 3400,
                "graded_docs": [
                    {
                        "page_content": "Open Settings > Security > Reset password.",
                        "metadata": {"title": "Password Reset", "source": "kb://reset"},
                    }
                ],
                "tool_calls": [{"name": "search_kb", "args": {"query": "reset password"}}],
                "citations": [{"index": 1, "title": "Password Reset"}],
            },
        ],
    )
    session = _Session(
        [
            {
                "id": 101,
                "trace_id": "trace-1",
                "tenant_id": "acme",
                "reason": "low_quality",
                "status": "pending",
                "created_at": datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc).isoformat(),
            }
        ]
    )

    result = asyncio.run(
        review_export.run_once(
            status="pending",
            tenant="all",
            limit=50,
            out=out_path,
            session_factory=lambda: session,
            settings=SimpleNamespace(tracing_db_path=str(db_path)),
            now=exported_at,
        )
    )

    assert result["count"] == 1
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# review_batch exported 2026-04-22T10:00:00+00:00")
    payload = json.loads(lines[1])
    assert payload == {
        "review_id": 101,
        "trace_id": "trace-1",
        "tenant_id": "acme",
        "reason": "low_quality",
        "exported_at": "2026-04-22T10:00:00+00:00",
        "query": "How do I reset my password?",
        "answer": "Open Settings > Security > Reset password. [1]",
        "final_route": "auto",
        "final_quality": 65,
        "fact_score": 72,
        "duration_ms": 3400,
        "retrieved_docs": [
            {
                "title": "Password Reset",
                "excerpt": "Open Settings > Security > Reset password.",
                "source": "kb://reset",
            }
        ],
        "tool_calls": [{"tool": "search_kb", "args": {"query": "reset password"}}],
        "citations": ["[1]"],
        "review": {"verdict": None, "notes": "", "fix_hint": "", "tags": []},
    }


def test_review_export_filters_by_status_and_tenant(tmp_path: Path) -> None:
    from scripts import review_export

    db_path = tmp_path / "traces.db"
    out_path = tmp_path / "review_batch.jsonl"
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "trace-acme",
        tenant_id="acme",
        final_route="auto",
        final_quality=60,
        states=[{"question": "acme", "answer": "answer acme"}],
    )
    _insert_trace(
        db_path,
        "trace-beta",
        tenant_id="beta",
        final_route="human",
        final_quality=30,
        states=[{"question": "beta", "answer": "answer beta"}],
    )
    session = _Session(
        [
            {
                "id": 1,
                "trace_id": "trace-acme",
                "tenant_id": "acme",
                "reason": "low_quality",
                "status": "pending",
                "created_at": "2026-04-22T09:00:00+00:00",
            },
            {
                "id": 2,
                "trace_id": "trace-beta",
                "tenant_id": "beta",
                "reason": "escalated",
                "status": "pending",
                "created_at": "2026-04-22T08:00:00+00:00",
            },
            {
                "id": 3,
                "trace_id": "trace-acme",
                "tenant_id": "acme",
                "reason": "manual",
                "status": "confirmed_bad",
                "created_at": "2026-04-22T07:00:00+00:00",
            },
        ]
    )

    result = asyncio.run(
        review_export.run_once(
            status="pending",
            tenant="acme",
            limit=50,
            out=out_path,
            session_factory=lambda: session,
            settings=SimpleNamespace(tracing_db_path=str(db_path)),
            now=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        )
    )

    assert result["count"] == 1
    payload = json.loads(out_path.read_text(encoding="utf-8").splitlines()[1])
    assert payload["review_id"] == 1
    assert payload["tenant_id"] == "acme"


def test_review_import_good_verdict_sets_confirmed_good(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import review_import

    reviewer_id = str(uuid.uuid4())
    monkeypatch.setenv("REVIEWER_EMAIL", "reviewer@example.com")
    batch_path = tmp_path / "batch.jsonl"
    batch_path.write_text(
        "\n".join(
            [
                "# review_batch exported 2026-04-22T10:00:00Z",
                json.dumps(
                    {
                        "review_id": 7,
                        "tenant_id": "acme",
                        "review": {
                            "verdict": "good",
                            "notes": "Looks correct",
                            "fix_hint": "Keep prompt as-is",
                            "tags": ["tier-1"],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "id": 7,
            "tenant_id": "acme",
            "status": "pending",
            "reviewer_notes": "",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    ]
    session = _Session(rows, users={"reviewer@example.com": reviewer_id})

    result = asyncio.run(
        review_import.run_once(
            batch_path,
            dry_run=False,
            tenant_override=None,
            confirm=True,
            session_factory=lambda: session,
        )
    )

    assert result["updated"] == 1
    assert rows[0]["status"] == "confirmed_good"
    assert rows[0]["reviewer_notes"] == "Looks correct\nKeep prompt as-is"
    assert rows[0]["reviewed_by"] == reviewer_id
    assert rows[0]["reviewed_at"] is not None


def test_review_import_skips_null_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import review_import

    monkeypatch.setenv("REVIEWER_EMAIL", "reviewer@example.com")
    batch_path = tmp_path / "batch.jsonl"
    batch_path.write_text(
        "\n".join(
            [
                "# review_batch exported 2026-04-22T10:00:00Z",
                json.dumps({"review_id": 7, "tenant_id": "acme", "review": {"verdict": None, "notes": "", "fix_hint": ""}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "id": 7,
            "tenant_id": "acme",
            "status": "pending",
            "reviewer_notes": "",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    ]
    session = _Session(rows, users={"reviewer@example.com": str(uuid.uuid4())})

    result = asyncio.run(
        review_import.run_once(
            batch_path,
            dry_run=False,
            tenant_override=None,
            confirm=True,
            session_factory=lambda: session,
        )
    )

    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert rows[0]["status"] == "pending"


def test_review_import_dry_run_does_not_change_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import review_import

    monkeypatch.setenv("REVIEWER_EMAIL", "reviewer@example.com")
    batch_path = tmp_path / "batch.jsonl"
    batch_path.write_text(
        "\n".join(
            [
                "# review_batch exported 2026-04-22T10:00:00Z",
                json.dumps({"review_id": 9, "tenant_id": "acme", "review": {"verdict": "bad", "notes": "Wrong answer", "fix_hint": ""}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "id": 9,
            "tenant_id": "acme",
            "status": "pending",
            "reviewer_notes": "",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    ]
    session = _Session(rows, users={"reviewer@example.com": str(uuid.uuid4())})

    result = asyncio.run(
        review_import.run_once(
            batch_path,
            dry_run=True,
            tenant_override=None,
            confirm=True,
            session_factory=lambda: session,
        )
    )

    assert result["updated"] == 0
    assert result["dry_run"] is True
    assert rows[0]["status"] == "pending"
    assert session.commit_count == 0


def test_review_import_skips_non_pending_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import review_import

    monkeypatch.setenv("REVIEWER_EMAIL", "reviewer@example.com")
    batch_path = tmp_path / "batch.jsonl"
    batch_path.write_text(
        "\n".join(
            [
                "# review_batch exported 2026-04-22T10:00:00Z",
                json.dumps(
                    {
                        "review_id": 5,
                        "tenant_id": "acme",
                        "review": {"verdict": "bad", "notes": "Still wrong", "fix_hint": ""},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "id": 5,
            "tenant_id": "acme",
            "status": "confirmed_bad",
            "reviewer_notes": "already reviewed",
            "reviewed_by": str(uuid.uuid4()),
            "reviewed_at": "2026-04-22T09:00:00+00:00",
        }
    ]
    session = _Session(rows, users={"reviewer@example.com": str(uuid.uuid4())})

    result = asyncio.run(
        review_import.run_once(
            batch_path,
            dry_run=False,
            tenant_override=None,
            confirm=True,
            session_factory=lambda: session,
        )
    )

    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert result["warnings"] == 1
    assert rows[0]["status"] == "confirmed_bad"

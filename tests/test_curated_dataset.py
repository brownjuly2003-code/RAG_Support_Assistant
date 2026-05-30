from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
        conn.commit()


def _insert_trace(
    db_path: Path,
    trace_id: str,
    *,
    tenant_id: str = "default",
    final_route: str = "auto",
    final_quality: float = 85.0,
    state: dict[str, object] | None = None,
) -> None:
    started_at = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc).isoformat()
    finished_at = datetime(2026, 4, 21, 10, 2, tzinfo=timezone.utc).isoformat()

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
        conn.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, 0, "answer", json.dumps(state or {}), finished_at),
        )
        conn.commit()


class _Result:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _CuratedBuilderSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def __aenter__(self) -> "_CuratedBuilderSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        data = params or {}
        if "FROM review_queue" not in sql:
            raise AssertionError(f"Unexpected SQL: {sql}")

        tenant_id = data.get("tenant_id")
        include_bad = "confirmed_bad" in sql
        filtered: list[dict[str, object]] = []
        for row in self.rows:
            if row["status"] not in {"confirmed_good", "confirmed_bad"}:
                continue
            if row["status"] == "confirmed_bad" and not include_bad:
                continue
            if tenant_id is not None and row["tenant_id"] != tenant_id:
                continue
            filtered.append(dict(row))
        filtered.sort(key=lambda item: str(item["created_at"]))
        return _Result(rows=filtered)

    async def commit(self) -> None:
        return None


def test_build_curated_dataset_creates_jsonl_from_confirmed_cases(tmp_path: Path) -> None:
    from scripts import build_curated_dataset

    db_path = tmp_path / "traces.db"
    out_path = tmp_path / "curated_cases.jsonl"
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "case-1",
        tenant_id="acme",
        final_route="auto",
        final_quality=88,
        state={
            "question": "How do I reset my password?",
            "answer": "Reset your password from account settings using the password reset form.",
            "route": "auto",
            "channel": "web",
            "quality_score": 88,
            "factuality_score": 91,
            "citations": [{"doc_id": "faq-reset"}],
            "retrieved_docs": [{"title": "Password reset guide"}],
        },
    )

    session = _CuratedBuilderSession(
        [
            {
                "trace_id": "case-1",
                "tenant_id": "acme",
                "status": "confirmed_good",
                "reviewer_notes": "",
                "created_at": datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
                "reviewed_at": datetime(2026, 4, 21, 12, 5, tzinfo=timezone.utc),
            }
        ]
    )
    settings = SimpleNamespace(tracing_db_path=db_path, project_root=tmp_path)

    result = asyncio.run(
        build_curated_dataset.run_once(
            tenant="all",
            since=None,
            out=out_path,
            include_bad=False,
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert result["written"] == 1
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    case = json.loads(lines[0])
    assert case["tenant_id"] == "acme"
    assert case["human_verdict"] == "good"
    assert case["input"]["query"] == "How do I reset my password?"
    assert case["input"]["channel"] == "web"
    assert case["expected"]["route"] == "auto"
    assert case["expected"]["citations_min_count"] == 1
    assert case["expected"]["answer_contains"] != []


def test_build_curated_dataset_include_bad_adds_confirmed_bad_cases(tmp_path: Path) -> None:
    from scripts import build_curated_dataset

    db_path = tmp_path / "traces.db"
    out_path = tmp_path / "curated_cases.jsonl"
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "case-good",
        tenant_id="acme",
        state={
            "question": "How do I cancel my subscription?",
            "answer": "Cancel the subscription from the billing page.",
            "route": "auto",
            "channel": "email",
            "citations": [{"doc_id": "billing"}],
        },
    )
    _insert_trace(
        db_path,
        "case-bad",
        tenant_id="acme",
        final_route="human",
        state={
            "question": "Where is my refund?",
            "answer": "Your refund is instant and guaranteed today.",
            "route": "human",
            "channel": "telegram",
            "citations": [],
        },
    )

    session = _CuratedBuilderSession(
        [
            {
                "trace_id": "case-good",
                "tenant_id": "acme",
                "status": "confirmed_good",
                "reviewer_notes": "",
                "created_at": datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
                "reviewed_at": datetime(2026, 4, 21, 12, 5, tzinfo=timezone.utc),
            },
            {
                "trace_id": "case-bad",
                "tenant_id": "acme",
                "status": "confirmed_bad",
                "reviewer_notes": "hallucinated refund timing",
                "created_at": datetime(2026, 4, 21, 13, 0, tzinfo=timezone.utc),
                "reviewed_at": datetime(2026, 4, 21, 13, 5, tzinfo=timezone.utc),
            },
        ]
    )
    settings = SimpleNamespace(tracing_db_path=db_path, project_root=tmp_path)

    asyncio.run(
        build_curated_dataset.run_once(
            tenant="all",
            since=None,
            out=out_path,
            include_bad=True,
            session_factory=lambda: session,
            settings=settings,
        )
    )

    cases = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 2
    bad_case = next(item for item in cases if item["source_trace_id"] == "case-bad")
    assert bad_case["human_verdict"] == "bad"
    assert bad_case["expected"]["route"] == "human"
    assert bad_case["expected"]["answer_contains"] == []
    assert bad_case["expected"]["answer_not_contains"] == []


def test_build_curated_dataset_is_idempotent(tmp_path: Path) -> None:
    from scripts import build_curated_dataset

    db_path = tmp_path / "traces.db"
    out_path = tmp_path / "curated_cases.jsonl"
    _init_trace_db(db_path)
    _insert_trace(
        db_path,
        "case-dedup",
        tenant_id="acme",
        state={
            "question": "How do I update my email?",
            "answer": "Update your email address from profile settings.",
            "route": "auto",
            "channel": "web",
            "citations": [{"doc_id": "profile"}],
        },
    )

    session = _CuratedBuilderSession(
        [
            {
                "trace_id": "case-dedup",
                "tenant_id": "acme",
                "status": "confirmed_good",
                "reviewer_notes": "",
                "created_at": datetime(2026, 4, 21, 14, 0, tzinfo=timezone.utc),
                "reviewed_at": datetime(2026, 4, 21, 14, 5, tzinfo=timezone.utc),
            }
        ]
    )
    settings = SimpleNamespace(tracing_db_path=db_path, project_root=tmp_path)

    asyncio.run(
        build_curated_dataset.run_once(
            tenant="all",
            since=None,
            out=out_path,
            include_bad=False,
            session_factory=lambda: session,
            settings=settings,
        )
    )
    asyncio.run(
        build_curated_dataset.run_once(
            tenant="all",
            since=None,
            out=out_path,
            include_bad=False,
            session_factory=lambda: session,
            settings=settings,
        )
    )

    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 1


def test_load_curated_cases_parses_jsonl_models(tmp_path: Path) -> None:
    from evaluation.dataset import CuratedCase, load_curated_cases

    path = tmp_path / "curated_cases.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "trace-a",
                        "tenant_id": "acme",
                        "input": {"query": "Q1", "context_hint": "doc", "channel": "web"},
                        "expected": {
                            "answer_contains": ["foo"],
                            "answer_not_contains": [],
                            "route": "auto",
                            "min_quality": 70,
                            "min_factuality": 70,
                            "citations_min_count": 1,
                        },
                        "human_verdict": "good",
                        "reviewer_notes": "",
                        "source_trace_id": "a",
                        "created_at": "2026-04-21T10:00:00+00:00",
                        "tags": ["billing"],
                    }
                )
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    cases = load_curated_cases(path)

    assert len(cases) == 1
    assert isinstance(cases[0], CuratedCase)
    assert cases[0].tags == ["billing"]
    assert cases[0].created_at == datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)


def test_checked_in_curated_cases_have_expanded_ru_seed_coverage() -> None:
    from scripts.regression_eval import load_curated_cases

    cases = load_curated_cases(PROJECT_ROOT / "evaluation" / "curated_cases.jsonl")
    case_ids = [case.case_id for case in cases]

    assert len(cases) >= 35
    assert len(case_ids) == len(set(case_ids))
    assert sum(any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in case.query) for case in cases) >= 30


def test_split_cases_is_deterministic() -> None:
    from evaluation.dataset import CuratedCase, split_cases

    def _case(case_id: str) -> CuratedCase:
        return CuratedCase.model_validate(
            {
                "case_id": case_id,
                "tenant_id": "acme",
                "input": {"query": case_id, "context_hint": "", "channel": "web"},
                "expected": {
                    "answer_contains": [],
                    "answer_not_contains": [],
                    "route": "auto",
                    "min_quality": 70,
                    "min_factuality": 70,
                    "citations_min_count": 1,
                },
                "human_verdict": "good",
                "reviewer_notes": "",
                "source_trace_id": case_id,
                "created_at": "2026-04-21T10:00:00+00:00",
            }
        )

    original = [_case(f"trace-{index}") for index in range(6)]
    reversed_cases = list(reversed(original))

    train_a, eval_a = split_cases(original, ratio=0.5)
    train_b, eval_b = split_cases(reversed_cases, ratio=0.5)

    assert [case.case_id for case in train_a] == [case.case_id for case in train_b]
    assert [case.case_id for case in eval_a] == [case.case_id for case in eval_b]


def test_filter_cases_filters_by_tenant_since_and_tags() -> None:
    from evaluation.dataset import CuratedCase, filter_cases

    cases = [
        CuratedCase.model_validate(
            {
                "case_id": "trace-a",
                "tenant_id": "acme",
                "input": {"query": "Q1", "context_hint": "", "channel": "web"},
                "expected": {
                    "answer_contains": [],
                    "answer_not_contains": [],
                    "route": "auto",
                    "min_quality": 70,
                    "min_factuality": 70,
                    "citations_min_count": 1,
                },
                "human_verdict": "good",
                "reviewer_notes": "",
                "source_trace_id": "a",
                "created_at": "2026-04-21T10:00:00+00:00",
                "tags": ["billing"],
            }
        ),
        CuratedCase.model_validate(
            {
                "case_id": "trace-b",
                "tenant_id": "beta",
                "input": {"query": "Q2", "context_hint": "", "channel": "email"},
                "expected": {
                    "answer_contains": [],
                    "answer_not_contains": [],
                    "route": "human",
                    "min_quality": 70,
                    "min_factuality": 70,
                    "citations_min_count": 1,
                },
                "human_verdict": "bad",
                "reviewer_notes": "",
                "source_trace_id": "b",
                "created_at": "2026-04-20T10:00:00+00:00",
                "tags": ["refunds"],
            }
        ),
    ]

    filtered = filter_cases(cases, tenant="acme", tags=["billing"], since="2026-04-21")

    assert [case.case_id for case in filtered] == ["trace-a"]


def test_admin_curated_dataset_stats_returns_counts(
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    evaluation_dir = tmp_path / "evaluation"
    evaluation_dir.mkdir(parents=True)
    curated_path = evaluation_dir / "curated_cases.jsonl"
    curated_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "trace-a",
                        "tenant_id": "acme",
                        "input": {"query": "Q1", "context_hint": "", "channel": "web"},
                        "expected": {
                            "answer_contains": ["foo"],
                            "answer_not_contains": [],
                            "route": "auto",
                            "min_quality": 70,
                            "min_factuality": 70,
                            "citations_min_count": 1,
                        },
                        "human_verdict": "good",
                        "reviewer_notes": "",
                        "source_trace_id": "a",
                        "created_at": "2026-04-21T10:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "case_id": "trace-b",
                        "tenant_id": "acme",
                        "input": {"query": "Q2", "context_hint": "", "channel": "email"},
                        "expected": {
                            "answer_contains": [],
                            "answer_not_contains": [],
                            "route": "human",
                            "min_quality": 70,
                            "min_factuality": 70,
                            "citations_min_count": 1,
                        },
                        "human_verdict": "bad",
                        "reviewer_notes": "",
                        "source_trace_id": "b",
                        "created_at": "2026-04-21T11:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "case_id": "trace-c",
                        "tenant_id": "beta",
                        "input": {"query": "Q3", "context_hint": "", "channel": "telegram"},
                        "expected": {
                            "answer_contains": ["bar"],
                            "answer_not_contains": [],
                            "route": "auto",
                            "min_quality": 70,
                            "min_factuality": 70,
                            "citations_min_count": 1,
                        },
                        "human_verdict": "good",
                        "reviewer_notes": "",
                        "source_trace_id": "c",
                        "created_at": "2026-04-21T12:00:00+00:00",
                    }
                ),
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    settings = api_app.get_settings()
    settings.project_root = tmp_path

    response = client_with_key.get(
        "/api/admin/curated-dataset/stats",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert body["verdict_counts"] == {"good": 2, "bad": 1}
    assert body["tenant_counts"]["acme"] == {"good": 1, "bad": 1, "total": 2}
    assert body["tenant_counts"]["beta"] == {"good": 1, "bad": 0, "total": 1}
    assert body["channel_counts"] == {"web": 1, "email": 1, "telegram": 1}


def test_admin_curated_dataset_rebuild_returns_job_id_and_tracks_queue_state(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.project_root = tmp_path

    tracker_events: list[tuple[str, dict[str, object], int]] = []
    scheduled: list[object] = []

    def _fake_cache_json_set(key: str, value: dict[str, object], ttl_seconds: int = 3600) -> None:
        tracker_events.append((key, value, ttl_seconds))

    def _fake_create_task(coro):
        scheduled.append(coro)
        return object()

    monkeypatch.setattr(api_app, "cache_json_set", _fake_cache_json_set)
    monkeypatch.setattr(api_app.asyncio, "create_task", _fake_create_task)

    response = client_with_key.post(
        "/api/admin/curated-dataset/rebuild?tenant=all&include_bad=true",
        headers=_token("acme", "admin"),
    )

    for coroutine in scheduled:
        coroutine.close()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    assert tracker_events[0][0].endswith(body["job_id"])
    assert tracker_events[0][1]["status"] == "queued"


class _CuratedStatusResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_CuratedStatusResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)


class _CuratedStatusSession:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    async def __aenter__(self) -> "_CuratedStatusSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _CuratedStatusResult:
        sql = " ".join(str(statement).split()).upper()
        values = dict(params or {})
        if "FROM CURATED_CASE_STATUS" not in sql:
            raise AssertionError(f"Unexpected SQL: {statement}")
        rows = list(self.rows)
        tenant_id = values.get("tenant_id")
        if tenant_id is not None:
            rows = [row for row in rows if row.get("tenant_id") == tenant_id]
        return _CuratedStatusResult(rows)

    async def commit(self) -> None:
        return None


def test_curated_case_status_migration_upgrade_creates_table_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "017_curated_case_status.py"
    )
    spec = importlib.util.spec_from_file_location("migration_017_curated_case_status", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    table_calls: list[str] = []
    index_calls: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(module.op, "create_table", lambda name, *args, **kwargs: table_calls.append(name))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table_name, columns, **kwargs: index_calls.append((table_name, tuple(columns))),
    )

    module.upgrade()

    assert table_calls == ["curated_case_status"]
    assert ("curated_case_status", ("tenant_id",)) in index_calls
    assert ("curated_case_status", ("status",)) in index_calls


def test_admin_curated_dataset_stale_lists_stale_cases(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    evaluation_dir = tmp_path / "evaluation"
    evaluation_dir.mkdir(parents=True)
    curated_path = evaluation_dir / "curated_cases.jsonl"
    curated_path.write_text(
        json.dumps(
            {
                "case_id": "case-stale-1",
                "tenant_id": "acme",
                "input": {"query": "Q1", "context_hint": "", "channel": "web"},
                "expected": {
                    "answer_contains": ["foo"],
                    "answer_not_contains": [],
                    "route": "auto",
                    "min_quality": 70,
                    "min_factuality": 70,
                    "citations_min_count": 1,
                },
                "human_verdict": "good",
                "reviewer_notes": "",
                "source_trace_id": "trace-1",
                "created_at": "2025-01-01T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
        newline="\n",
    )

    settings = api_app.get_settings()
    settings.project_root = tmp_path
    monkeypatch.setattr(
        "db.engine.async_session",
        lambda: _CuratedStatusSession(
            [
                {
                    "case_id": "case-stale-1",
                    "tenant_id": "acme",
                    "status": "stale_needs_review",
                    "staleness_reason": "quality_drop",
                    "last_checked_at": "2026-04-22T12:00:00+00:00",
                }
            ]
        ),
    )

    response = client_with_key.get(
        "/api/admin/curated-dataset/stale",
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["case_id"] == "case-stale-1"
    assert payload["items"][0]["status"] == "stale_needs_review"
    assert payload["items"][0]["staleness_reason"] == "quality_drop"

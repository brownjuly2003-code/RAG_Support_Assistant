from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant: str = "default", role: str = "admin", user_id: str = "admin-user") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role, tenant)}"}


class _Result:
    def __init__(self, rows: list[dict[str, object]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _PersistSession:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.committed = False

    async def __aenter__(self) -> "_PersistSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        self.executed.append((str(statement), dict(params or {})))
        return _Result(rowcount=1)

    async def commit(self) -> None:
        self.committed = True


class _EndpointSession:
    def __init__(
        self,
        *,
        trends_rows: list[dict[str, object]] | None = None,
        worst_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.trends_rows = trends_rows or []
        self.worst_rows = worst_rows or []

    async def __aenter__(self) -> "_EndpointSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        if "AVG(score)" in sql:
            return _Result(rows=self.trends_rows)
        if "ORDER BY score ASC" in sql:
            return _Result(rows=self.worst_rows)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


class _SnapshotSession:
    def __init__(self) -> None:
        self.aggregate_rows = [
            {
                "evaluator_name": "citation_coverage",
                "mean_score": 0.55,
                "verdict": "low",
                "verdict_count": 2,
            },
            {
                "evaluator_name": "citation_coverage",
                "mean_score": 0.55,
                "verdict": "ok",
                "verdict_count": 8,
            },
            {
                "evaluator_name": "language_mismatch",
                "mean_score": 0.10,
                "verdict": "mismatch",
                "verdict_count": 1,
            },
        ]
        self.worst_rows = {
            "citation_coverage": [
                {
                    "trace_id": "trace-2",
                    "score": 0.0,
                    "verdict": "missing",
                    "evaluated_at": datetime(2026, 4, 20, 5, 0, tzinfo=timezone.utc),
                },
                {
                    "trace_id": "trace-1",
                    "score": 0.2,
                    "verdict": "low",
                    "evaluated_at": datetime(2026, 4, 20, 4, 0, tzinfo=timezone.utc),
                },
            ],
            "language_mismatch": [
                {
                    "trace_id": "trace-3",
                    "score": 1.0,
                    "verdict": "mismatch",
                    "evaluated_at": datetime(2026, 4, 20, 6, 0, tzinfo=timezone.utc),
                }
            ],
        }

    async def __aenter__(self) -> "_SnapshotSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        params = params or {}
        if "COUNT(*) AS verdict_count" in sql:
            return _Result(rows=self.aggregate_rows)
        if "ORDER BY score ASC" in sql:
            evaluator_name = str(params["evaluator_name"])
            return _Result(rows=self.worst_rows[evaluator_name])
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        return None


def test_evaluate_citation_coverage_scores_fraction() -> None:
    from evaluation.online_evaluators import evaluate_citation_coverage

    result = evaluate_citation_coverage(
        {"answer": "Первое утверждение [1]. Второе без сноски. Третье тоже [2]."}
    )

    assert result["score"] == pytest.approx(2 / 3, abs=0.01)
    assert result["verdict"] == "partial"


def test_evaluate_answer_length_anomaly_marks_outlier() -> None:
    from evaluation.online_evaluators import evaluate_answer_length_anomaly

    result = evaluate_answer_length_anomaly(
        {"answer": "слово " * 60},
        mean=20,
        std=10,
    )

    assert result["score"] == 1.0
    assert result["verdict"] == "anomaly"
    assert result["metadata"]["z_score"] > 2.0


def test_evaluate_retrieval_hit_rate_uses_rerank_scores() -> None:
    from evaluation.online_evaluators import evaluate_retrieval_hit_rate

    result = evaluate_retrieval_hit_rate(
        {
            "retrieved_docs": [
                {"metadata": {"relevance_score": 0.9}},
                {"metadata": {"relevance_score": 0.6}},
                {"metadata": {"relevance_score": 0.2}},
                {"metadata": {}},
            ]
        }
    )

    assert result["score"] == pytest.approx(2 / 3, abs=0.01)
    assert result["metadata"]["scored_docs"] == 3


def test_evaluate_tool_use_efficiency_uses_tool_token_budget() -> None:
    from evaluation.online_evaluators import evaluate_tool_use_efficiency

    result = evaluate_tool_use_efficiency(
        {
            "answer": "final answer tokens go here",
            "answer_final_tokens": 20,
            "tool_calls": [
                {"name": "search", "total_tokens": 50},
                {"name": "lookup", "total_tokens": 30},
            ],
        }
    )

    assert result["score"] == pytest.approx(0.2, abs=0.001)
    assert result["verdict"] == "inefficient"


@pytest.mark.parametrize(
    ("answer", "expected_score"),
    [
        ("Извините, я не знаю точный ответ на этот вопрос.", 1.0),
        ("Вот инструкция по возврату товара [1].", 0.0),
    ],
)
def test_evaluate_refusal_detected(answer: str, expected_score: float) -> None:
    from evaluation.online_evaluators import evaluate_refusal_detected

    result = evaluate_refusal_detected({"answer": answer})

    assert result["score"] == expected_score


def test_evaluate_pii_leak_suspicion_detects_phone_and_email() -> None:
    from evaluation.online_evaluators import evaluate_pii_leak_suspicion

    result = evaluate_pii_leak_suspicion(
        {"answer": "Свяжитесь по +1 (555) 123-45-67 или support@example.com"}
    )

    assert result["score"] > 0.0
    assert sorted(result["metadata"]["matches"]) == ["email", "phone"]


def test_evaluate_language_mismatch_detects_ru_query_and_en_answer() -> None:
    from evaluation.online_evaluators import evaluate_language_mismatch

    result = evaluate_language_mismatch(
        {"question": "Как вернуть заказ?", "answer": "Please contact support manager."}
    )

    assert result["score"] == 1.0
    assert result["verdict"] == "mismatch"


def test_runner_captures_evaluator_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from evaluation import evaluator_runner

    monkeypatch.setattr(
        evaluator_runner,
        "ONLINE_EVALUATORS",
        {
            "ok_eval": lambda state: {"score": 1.0, "verdict": "ok", "metadata": {}},
            "boom_eval": lambda state: (_ for _ in ()).throw(RuntimeError("boom")),
        },
        raising=False,
    )

    results = evaluator_runner.run_online_evaluators({"trace_id": "trace-1"})

    assert results["ok_eval"]["score"] == 1.0
    assert results["boom_eval"]["score"] == 0.0
    assert results["boom_eval"]["metadata"]["error"] == "boom"


def test_persist_online_evaluations_inserts_rows() -> None:
    from evaluation.evaluator_runner import persist_online_evaluations

    session = _PersistSession()
    asyncio.run(
        persist_online_evaluations(
            "trace-123",
            {
                "citation_coverage": {
                    "score": 0.5,
                    "verdict": "partial",
                    "metadata": {"cited_sentences": 1},
                }
            },
            session_factory=lambda: session,
        )
    )

    assert session.committed is True
    assert len(session.executed) == 1
    sql, params = session.executed[0]
    assert "INSERT INTO trace_evaluations" in sql
    assert params["trace_id"] == "trace-123"
    assert params["evaluator_name"] == "citation_coverage"


def test_persist_online_evaluations_uses_independent_sessions_per_evaluator() -> None:
    from evaluation.evaluator_runner import persist_online_evaluations

    class _TrackingSession(_PersistSession):
        active_execute_count = 0
        max_active_execute_count = 0

        async def execute(self, statement, params: dict[str, object] | None = None) -> _Result:
            type(self).active_execute_count += 1
            type(self).max_active_execute_count = max(
                type(self).max_active_execute_count,
                type(self).active_execute_count,
            )
            try:
                await asyncio.sleep(0.01)
                return await super().execute(statement, params)
            finally:
                type(self).active_execute_count -= 1

    sessions: list[_TrackingSession] = []

    def _session_factory() -> _TrackingSession:
        session = _TrackingSession()
        sessions.append(session)
        return session

    asyncio.run(
        persist_online_evaluations(
            "trace-456",
            {
                "citation_coverage": {"score": 0.5, "verdict": "partial", "metadata": {}},
                "retrieval_hit_rate": {"score": 1.0, "verdict": "ok", "metadata": {}},
            },
            session_factory=_session_factory,
        )
    )

    assert len(sessions) == 2
    assert all(session.committed for session in sessions)
    assert _TrackingSession.max_active_execute_count == 2


def test_online_evaluations_migration_upgrade_creates_table_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "014_trace_evaluations.py"
    )
    spec = importlib.util.spec_from_file_location("migration_013_trace_evaluations", migration_path)
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

    assert table_calls == ["trace_evaluations"]
    assert ("trace_evaluations", ("trace_id",)) in index_calls
    assert ("trace_evaluations", ("evaluator_name", "evaluated_at")) in index_calls


def test_online_evaluations_migration_downgrade_drops_table_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "014_trace_evaluations.py"
    )
    spec = importlib.util.spec_from_file_location("migration_013_trace_evaluations", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "drop_index", lambda name, table_name=None: events.append(("drop_index", name)))
    monkeypatch.setattr(module.op, "drop_table", lambda name: events.append(("drop_table", name)))

    module.downgrade()

    assert ("drop_index", "ix_trace_evaluations_trace_id") in events
    assert ("drop_index", "ix_trace_evaluations_evaluator_name_evaluated_at") in events
    assert ("drop_table", "trace_evaluations") in events


def test_run_qa_pipeline_persists_online_evaluations_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    class _CompiledGraph:
        def invoke(self, initial_state):
            return {**initial_state, "answer": "ready", "route": "auto", "quality_score": 91}

    settings = type("Settings", (), {"quality_threshold": 80, "online_evaluators_enabled": True})()
    persisted: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(graph, "get_settings", lambda: settings, raising=False)
    monkeypatch.setattr(graph, "start_trace", lambda trace_id=None, tenant_id="default": "trace-online")
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _CompiledGraph())
    monkeypatch.setattr(
        graph,
        "run_online_evaluators",
        lambda state: {"citation_coverage": {"score": 1.0, "verdict": "ok", "metadata": {}}},
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "persist_online_evaluations",
        lambda trace_id, results: persisted.append((trace_id, results)),
        raising=False,
    )

    result = graph.run_qa_pipeline(question="test", retriever=object(), llm=object())

    assert result["answer"] == "ready"
    assert persisted == [
        (
            "trace-online",
            {"citation_coverage": {"score": 1.0, "verdict": "ok", "metadata": {}}},
        )
    ]


def test_run_qa_pipeline_skips_online_evaluations_when_feature_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    class _CompiledGraph:
        def invoke(self, initial_state):
            return {**initial_state, "answer": "ready", "route": "auto", "quality_score": 91}

    settings = type("Settings", (), {"quality_threshold": 80, "online_evaluators_enabled": False})()
    monkeypatch.setattr(graph, "get_settings", lambda: settings, raising=False)
    monkeypatch.setattr(graph, "start_trace", lambda trace_id=None, tenant_id="default": "trace-off")
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _CompiledGraph())

    called = {"run": 0, "persist": 0}
    monkeypatch.setattr(
        graph,
        "run_online_evaluators",
        lambda state: called.__setitem__("run", called["run"] + 1),
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "persist_online_evaluations",
        lambda trace_id, results: called.__setitem__("persist", called["persist"] + 1),
        raising=False,
    )

    graph.run_qa_pipeline(question="test", retriever=object(), llm=object())

    assert called == {"run": 0, "persist": 0}


def test_admin_evaluations_trends_endpoint_returns_timeseries(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    monkeypatch.setattr(
        "db.engine.async_session",
        lambda: _EndpointSession(
            trends_rows=[
                {"bucket": "2026-04-19", "mean_score": 0.45, "runs": 10},
                {"bucket": "2026-04-20", "mean_score": 0.62, "runs": 12},
            ]
        ),
    )

    response = client_with_key.get(
        "/api/admin/evaluations/trends?evaluator=citation_coverage&days=30",
        headers=_token("default", "admin"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "evaluator": "citation_coverage",
        "days": 30,
        "points": [
            {"date": "2026-04-19", "mean_score": 0.45, "runs": 10},
            {"date": "2026-04-20", "mean_score": 0.62, "runs": 12},
        ],
    }


def test_admin_evaluations_worst_endpoint_returns_lowest_scores(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    monkeypatch.setattr(
        "db.engine.async_session",
        lambda: _EndpointSession(
            worst_rows=[
                {
                    "trace_id": "trace-1",
                    "score": 0.0,
                    "verdict": "missing",
                    "metadata": {"cited_sentences": 0},
                    "evaluated_at": "2026-04-20T01:00:00+00:00",
                },
                {
                    "trace_id": "trace-2",
                    "score": 0.1,
                    "verdict": "low",
                    "metadata": {"cited_sentences": 1},
                    "evaluated_at": "2026-04-20T02:00:00+00:00",
                },
            ]
        ),
    )

    response = client_with_key.get(
        "/api/admin/evaluations/worst?evaluator=citation_coverage&limit=2",
        headers=_token("default", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["trace_id"] == "trace-1"
    assert response.json()["items"][0]["score"] == 0.0
    assert response.json()["limit"] == 2


def test_eval_daily_snapshot_writes_report_json(tmp_path: Path) -> None:
    from scripts import eval_daily_snapshot

    output_dir = tmp_path / "eval_daily"
    result = asyncio.run(
        eval_daily_snapshot.run_once(
            target_date=date(2026, 4, 20),
            output_dir=output_dir,
            session_factory=lambda: _SnapshotSession(),
        )
    )

    report_path = output_dir / "2026-04-20.json"
    assert result["path"] == str(report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-04-20"
    assert payload["evaluators"]["citation_coverage"]["mean_score"] == 0.55
    assert payload["evaluators"]["citation_coverage"]["verdict_counts"]["low"] == 2
    assert payload["evaluators"]["citation_coverage"]["worst_traces"][0]["trace_id"] == "trace-2"


def test_run_qa_pipeline_persists_via_main_loop_without_dispose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-5: with a registered main loop, online-eval persistence is bridged onto
    it via run_coroutine_threadsafe and the shared engine pool is NOT disposed."""
    import threading

    import agent.graph as graph
    import db.engine as db_engine
    from utils.event_loop import set_main_loop

    class _CompiledGraph:
        def invoke(self, initial_state):
            return {**initial_state, "answer": "ready", "route": "auto", "quality_score": 91}

    class _FakeEngine:
        def __init__(self) -> None:
            self.dispose_calls = 0

        async def dispose(self) -> None:
            self.dispose_calls += 1

    fake_engine = _FakeEngine()
    settings = type(
        "Settings",
        (),
        {
            "quality_threshold": 80,
            "online_evaluators_enabled": True,
            "online_evaluators_timeout_sec": 5.0,
        },
    )()
    persisted: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(graph, "get_settings", lambda: settings, raising=False)
    monkeypatch.setattr(graph, "start_trace", lambda trace_id=None, tenant_id="default": "trace-loop")
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _CompiledGraph())
    monkeypatch.setattr(db_engine, "engine", fake_engine, raising=False)
    monkeypatch.setattr(
        graph,
        "run_online_evaluators",
        lambda state: {"citation_coverage": {"score": 1.0, "verdict": "ok", "metadata": {}}},
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "persist_online_evaluations",
        lambda trace_id, results: persisted.append((trace_id, results)),
        raising=False,
    )

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        set_main_loop(loop)
        result = graph.run_qa_pipeline(question="test", retriever=object(), llm=object())
    finally:
        set_main_loop(None)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()

    assert result["answer"] == "ready"
    assert persisted == [
        ("trace-loop", {"citation_coverage": {"score": 1.0, "verdict": "ok", "metadata": {}}})
    ]
    # Bridged onto the main loop -> the shared asyncpg pool must survive.
    assert fake_engine.dispose_calls == 0

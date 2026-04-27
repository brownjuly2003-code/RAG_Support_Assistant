from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


class _MockRetriever:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def get_relevant_documents(self, query: str) -> list[Any]:
        _ = query
        class _Doc:
            def __init__(self, page_content: str, metadata: dict[str, Any]) -> None:
                self.page_content = page_content
                self.metadata = metadata
        return [_Doc(d["page_content"], d["metadata"]) for d in self._docs]


class _MockLLM:
    provider_id = "mock"
    model_name = "mock-model"
    supports_structured_output = False

    def invoke(self, prompt: str) -> str:
        _ = prompt
        return "85"


def _load_seed_docs(project_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for name in ("warranty.md", "returns_policy.md", "errors_e10_e30.md"):
        path = project_root / "docs" / name
        if path.exists():
            docs.append(
                {
                    "page_content": path.read_text(encoding="utf-8"),
                    "metadata": {"source": name, "doc_id": name.replace(".md", "")},
                }
            )
    return docs


def _write_curated_cases(path: Path) -> None:
    cases = [
        {
            "case_id": "case-warranty-live",
            "tenant_id": "default",
            "query": "What is the warranty period?",
            "expected": {
                "answer_contains": ["warranty"],
                "route": "auto",
                "min_quality": 70,
            },
        },
        {
            "case_id": "case-returns-live",
            "tenant_id": "default",
            "query": "How do I return a product?",
            "expected": {
                "answer_contains": ["return"],
                "route": "auto",
                "min_quality": 70,
            },
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")


@pytest.mark.integration
def test_regression_eval_live_no_asyncpg_race_no_fk_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("docker")
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    if shutil.which("alembic") is None:
        pytest.skip("alembic not available")

    # Codex audit 2026-04-27 H7: docker CLI присутствует, но daemon
    # может быть не запущен (типично на Windows без Docker Desktop).
    # Используем subprocess с явным timeout, потому что docker SDK на
    # некоторых платформах висит на socket read без honor-а timeout.
    import subprocess  # noqa: PLC0415

    try:
        _result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=5,
            text=True,
        )
        if _result.returncode != 0:
            pytest.skip(f"docker daemon unavailable: {_result.stderr.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        pytest.skip(f"docker daemon unavailable: {exc}")

    from testcontainers.postgres import PostgresContainer

    project_root = Path(__file__).resolve().parent.parent.parent

    with PostgresContainer(
        image="postgres:16-alpine",
        username="rag",
        password="rag_test",
        dbname="rag_regression_test",
        driver="psycopg2",
    ) as postgres:
        db_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://", 1
        )
        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        env["DB_ENCRYPTION_KEY"] = "regression-test-key"

        import subprocess

        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(project_root),
            env=env,
        )

        # Ingest seed docs
        import sys

        sys.path.insert(0, str(project_root))

        # Override DB URL for the ingestion without leaking into later tests.
        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("DB_ENCRYPTION_KEY", "regression-test-key")

        # Reset any cached settings/engine so they pick up the new DATABASE_URL
        import config.settings as _settings_module
        import db.engine as _engine_module

        monkeypatch.setattr(_settings_module, "_settings", None)
        # engine is created at import time; we need to recreate it
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.ext.asyncio import AsyncSession

        test_engine = create_async_engine(db_url, echo=False, pool_size=5, max_overflow=10)
        monkeypatch.setattr(_engine_module, "engine", test_engine)
        monkeypatch.setattr(
            _engine_module,
            "async_session",
            async_sessionmaker(
                test_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            ),
        )

        from ingestion.pipeline import IngestPipeline

        seed_docs = _load_seed_docs(project_root)
        # IngestPipeline ingests files from disk; write temp files
        with tempfile.TemporaryDirectory() as tmp_docs:
            tmp_docs_path = Path(tmp_docs)
            for doc in seed_docs:
                (tmp_docs_path / doc["metadata"]["source"]).write_text(
                    doc["page_content"], encoding="utf-8"
                )
            IngestPipeline().ingest(tmp_docs_path, tenant_id="default")

        # Write curated cases
        with tempfile.TemporaryDirectory() as tmp_cases:
            cases_path = Path(tmp_cases) / "curated_cases.jsonl"
            _write_curated_cases(cases_path)

            # Capture logs from agent.graph
            agent_logger = logging.getLogger("agent.graph")
            original_level = agent_logger.level
            agent_logger.setLevel(logging.WARNING)
            log_capture = []

            class _Handler(logging.Handler):
                def emit(self, record: logging.LogRecord) -> None:
                    log_capture.append(record.getMessage())

            handler = _Handler()
            agent_logger.addHandler(handler)

            try:
                from scripts import regression_eval
                import agent.graph as agent_graph
                from agent.graph import run_qa_pipeline
                from config.settings import get_settings

                monkeypatch.setattr(
                    agent_graph,
                    "run_online_evaluators",
                    lambda trace_state: {
                        "citation_coverage": {
                            "score": 1.0,
                            "verdict": "ok",
                            "metadata": {"trace_id": trace_state["trace_id"]},
                        }
                    },
                )
                settings = get_settings()
                settings.online_evaluators_enabled = True
                settings.fact_verification_enabled = False
                settings.self_rag_max_iterations = 0
                settings.quality_threshold = 80

                retriever = _MockRetriever(seed_docs)
                mock_llm = _MockLLM()

                def _executor(case, target: str):
                    _ = target
                    result = run_qa_pipeline(
                        question=case.query,
                        retriever=retriever,
                        llm=mock_llm,
                        max_iterations=0,
                        trace_id=f"provider-benchmark-{uuid.uuid4()}",
                        tenant_id=case.tenant_id,
                    )
                    from scripts.regression_eval import CaseRunResult

                    return CaseRunResult(
                        answer=str(result.get("answer") or ""),
                        quality_score=float(result.get("quality_score") or 0.0),
                        factuality_score=float(result.get("factuality_score") or 0.0),
                        citations=[],
                        duration_ms=100,
                        cost_usd=0.0,
                        route=str(result.get("route") or "unknown"),
                        trace_id=str(result.get("trace_id") or ""),
                    )

                report = regression_eval.run_regression(
                    baseline="baseline-mock",
                    candidate="candidate-mock",
                    dataset_path=cases_path,
                    tenant="all",
                    max_cases=2,
                    allow_paid_apis=False,
                    executor=_executor,
                )

                # Persist the report to also exercise persist_regression_result
                import asyncio

                async def _persist_and_check_db() -> tuple[int, int]:
                    await regression_eval.persist_regression_result(
                        session_factory=_engine_module.async_session,
                        report=report,
                        report_path=Path("reports/regression/test.json"),
                    )
                    async with _engine_module.async_session() as session:
                        te_result = await session.execute(
                            text("SELECT COUNT(*) FROM trace_evaluations")
                        )
                        te_count = te_result.scalar() or 0

                        er_result = await session.execute(
                            text("SELECT COUNT(*) FROM eval_results")
                        )
                        er_count = er_result.scalar() or 0
                        return te_count, er_count

                te_count, er_count = asyncio.run(_persist_and_check_db())
            finally:
                agent_logger.removeHandler(handler)
                agent_logger.setLevel(original_level)

            # Assert no InterfaceError or FK violations in logs
            log_text = "\n".join(log_capture)
            assert "InterfaceError" not in log_text, f"InterfaceError found in logs: {log_text}"
            assert "another operation is in progress" not in log_text, f"Race found in logs: {log_text}"
            assert "ForeignKeyViolationError" not in log_text, f"FK violation found in logs: {log_text}"

            # Assert trace_evaluations rows exist
            assert te_count > 0, "No trace_evaluations rows found"
            assert er_count > 0, "No eval_results rows found"

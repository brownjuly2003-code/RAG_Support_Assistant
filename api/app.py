"""
api/app.py

FastAPI REST API for the RAG Support Assistant.

Endpoints:
    POST /api/ask          - Ask a question (with optional session)
    POST /api/upload       - Upload a document (PDF/DOCX/TXT)
    GET  /api/sessions/{session_id}/history - Get conversation history
    DELETE /api/sessions/{session_id}       - Clear a session
    GET  /api/health       - Health check (real dependency probes)
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json as _json
import logging
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, cast

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ExceptionHandler
from api import _shared as _api_shared
from api.correlation import (
    generate_request_id,
    get_current_tenant as _get_current_tenant,
    get_request_id,
    sanitize_request_id,
    set_current_tenant,
    set_request_id,
)
from auth.oidc import (  # noqa: F401
    get_oauth_client as get_oidc_client,
    list_sso_providers,
    resolve_oidc_user,
)
from cache.redis_cache import (
    cache_delete_pattern as _cache_delete_pattern,
    cache_json_get as _cache_json_get,
    cache_json_set,
)
from api.rate_limit import RateLimitExceeded, _rate_limit_rejected, limiter
from db.audit import log_audit  # re-exported as api.app.log_audit for late-binding by routers  # noqa: F401
from monitoring import prometheus as prometheus_metrics

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging — JSON structured, set up before anything else
# ---------------------------------------------------------------------------
try:
    from config.logging_config import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
cache_delete_pattern = _cache_delete_pattern
cache_json_get = _cache_json_get
get_current_tenant = _get_current_tenant

if TYPE_CHECKING:
    from api.routers.conversation import Citation as CitationModel
    from config.settings import Settings


async def _stream_ollama(
    prompt: str,
    model: str,
    base_url: str,
) -> AsyncGenerator[str, None]:
    """Стримит токены из Ollama /api/generate."""
    payload = {"model": model, "prompt": prompt, "stream": True}
    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{base_url}/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = _json.loads(line)
                except (ValueError, _json.JSONDecodeError):
                    continue
                token = chunk.get("response", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break

# ---------------------------------------------------------------------------
# Safe imports with fallbacks
# ---------------------------------------------------------------------------

# LangChain Document
try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        from dataclasses import dataclass as _dc

        @_dc
        class Document:  # type: ignore[no-redef]
            page_content: str
            metadata: dict

# graph.py - ConversationSession and run_qa_pipeline
_ConversationSession = None
_run_qa_pipeline = None
try:
    from agent.graph import ConversationSession, run_qa_pipeline
    _ConversationSession = ConversationSession
    _run_qa_pipeline = run_qa_pipeline
except ImportError:
    logger.info("RAG pipeline not available - graph module not found")

# manager.py - vector store utilities
_build_vector_store = None
_get_retriever = None
_get_embeddings = None
try:
    from vectordb.manager import build_vector_store, get_retriever, get_embeddings
    _build_vector_store = build_vector_store
    _get_retriever = get_retriever
    _get_embeddings = get_embeddings
except ImportError:
    try:
        from vectordb.manager import build_vector_store, get_retriever, get_embeddings
        _build_vector_store = build_vector_store
        _get_retriever = get_retriever
        _get_embeddings = get_embeddings
    except ImportError:
        pass

# Document loader
_DocumentLoader = None
try:
    from ingestion.loader import DocumentLoader
    _DocumentLoader = DocumentLoader
except ImportError:
    pass

# Chroma for loading existing store
_Chroma = None
try:
    from langchain_chroma import Chroma
    _Chroma = Chroma
except ImportError:
    pass

# Settings
try:
    from config.settings import get_settings
except ImportError:
    def get_settings() -> Settings:
        class _S:
            project_root = PROJECT_ROOT
            data_dir = PROJECT_ROOT / "data"
            vectordb_chroma_dir = PROJECT_ROOT / "data" / "vectordb" / "chroma"
            ollama_base_url = "http://localhost:11434"
            chunk_size = 800
            chunk_overlap = 200
            api_default_page_size = 50
            quality_threshold = 80
            tracing_db_path = PROJECT_ROOT / "data" / "tracing" / "traces.db"
            session_ttl_seconds = 7200
            trace_retention_days = 90
            trace_purge_interval_sec = 86400
            shutdown_ready_delay_sec = 5.0
            api_key = ""
            require_ollama = False
            llm_cache_enabled = False
            llm_cache_ttl_seconds = 3600
            rag_env = "development"
            cors_origins = ["*"]
            session_secret_key = "dev-secret-change-in-production!"
            tenant_email_domains = ""
            google_oidc_client_id = None
            google_oidc_client_secret = None
            azure_oidc_tenant = None
            azure_oidc_client_id = None
            azure_oidc_client_secret = None
            otel_enabled = False
            otel_exporter_otlp_endpoint = "http://localhost:4317"
            otel_service_name = "rag-support-assistant"
        return cast("Settings", _S())

_build_provider_runtime = None
try:
    from llm.providers import build_provider_runtime
    _build_provider_runtime = build_provider_runtime
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

# AskRequest, AskResponse, SourceInfo, and Citation moved to api.routers.conversation


# FeedbackRequest and EscalateRequest moved to api.routers.feedback


# AgentRespondRequest moved to api.routers.agent


# KbDraftUpdateRequest moved to api.routers.admin_kb


# ReviewQueueUpdateRequest moved to api.routers.admin_review


# SessionInfo, HistoryMessage, HistoryResponse, LoginRequest, TokenResponse,
# and RefreshRequest moved to api.routers.session_auth (re-exported below).

from api.routers.system import ComponentStatus, HealthResponse  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_session_llm_state: Dict[str, Any] = {}
_sessions = _session_llm_state
_shutting_down: bool = False
_session_last_access: Dict[str, float] = {}
_db_retry_after: float = 0.0
_vector_store: Any = None
_retriever: Any = None
_chunks: List[Any] = []
_llm: Any = None
_pipeline_semaphore: asyncio.Semaphore | None = None
_vector_store_init_lock = threading.Lock()
_REVIEW_QUEUE_REASONS = _api_shared._REVIEW_QUEUE_REASONS
_REVIEW_QUEUE_STATUSES = _api_shared._REVIEW_QUEUE_STATUSES
_load_review_queue_trace_details = _api_shared._load_review_queue_trace_details
_refresh_review_queue_metrics = _api_shared._refresh_review_queue_metrics
_review_queue_enabled = _api_shared._review_queue_enabled
_reviewed_by_uuid = _api_shared._reviewed_by_uuid
_serialize_timestamp = _api_shared._serialize_timestamp
_regression_jobs: Dict[str, Dict[str, Any]] = {}


def _get_pipeline_semaphore() -> asyncio.Semaphore:
    global _pipeline_semaphore

    if _pipeline_semaphore is None:
        settings = get_settings()
        size = int(getattr(settings, "max_concurrent_pipelines", 8))
        _pipeline_semaphore = asyncio.Semaphore(size)

    return _pipeline_semaphore


def _list_tenant_documents(tenant_id: str) -> list[dict[str, Any]]:
    from vectordb import manager as tenant_manager  # noqa: PLC0415

    documents: dict[str, dict[str, Any]] = {}
    cached_chunks = getattr(tenant_manager, "_chunks_cache", {}).get(tenant_id) or []
    for index, chunk in enumerate(cached_chunks):
        metadata = getattr(chunk, "metadata", {}) or {}
        doc_id = str(
            metadata.get("doc_id")
            or metadata.get("source")
            or metadata.get("file_name")
            or f"doc-{index}"
        )
        entry = documents.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "title": str(metadata.get("title") or metadata.get("source") or doc_id),
                "source": str(metadata.get("source") or doc_id),
                "last_updated": metadata.get("last_updated"),
                "categories": list(metadata.get("categories") or ["uncategorized"]),
            },
        )
        if not entry.get("last_updated") and metadata.get("last_updated"):
            entry["last_updated"] = metadata.get("last_updated")
    return list(documents.values())


def _touch_tenant_document(tenant_id: str, doc_id: str) -> bool:
    from datetime import datetime, timezone  # noqa: PLC0415

    from vectordb import manager as tenant_manager  # noqa: PLC0415

    touched = False
    now_iso = datetime.now(timezone.utc).isoformat()
    cached_chunks = getattr(tenant_manager, "_chunks_cache", {}).get(tenant_id) or []
    for chunk in cached_chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        chunk_doc_id = str(metadata.get("doc_id") or metadata.get("source") or "")
        if chunk_doc_id == doc_id:
            metadata["last_updated"] = now_iso
            touched = True
    return touched


def _project_root_path() -> Path:
    return Path(getattr(get_settings(), "project_root", PROJECT_ROOT))


def _serialize_regression_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job)
    payload["created_at"] = _serialize_timestamp(payload.get("created_at"))
    payload["started_at"] = _serialize_timestamp(payload.get("started_at"))
    payload["finished_at"] = _serialize_timestamp(payload.get("finished_at"))
    return payload


def _read_regression_report_assets(report_path: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not report_path:
        return None, None

    json_path = _project_root_path() / Path(report_path)
    if not json_path.exists():
        return None, None

    try:
        report_payload = _json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        report_payload = None

    markdown_path = json_path.with_suffix(".md")
    try:
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else None
    except OSError:
        markdown = None
    return report_payload, markdown


def _load_provider_admin_snapshot(tenant_id: str) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    import os  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415

    from config.provider_schema import load_provider_registry  # noqa: PLC0415

    settings = get_settings()
    registry = load_provider_registry(getattr(settings, "provider_registry_path"))
    db_path = Path(getattr(settings, "tracing_db_path", ""))
    cutoff_1m = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    cutoff_1d = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    stats_by_provider: dict[str, dict[str, Any]] = {}

    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    trace_steps.provider_name,
                    COUNT(CASE WHEN trace_steps.ts >= ? THEN 1 END) AS requests_1m,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN trace_steps.ts >= ?
                                THEN COALESCE(trace_steps.prompt_tokens, 0) + COALESCE(trace_steps.completion_tokens, 0)
                                ELSE 0
                            END
                        ),
                        0
                    ) AS tokens_1m,
                    MAX(trace_steps.ts) AS last_success_at,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN trace_steps.ts >= ? THEN COALESCE(trace_steps.cost_usd, 0.0)
                                ELSE 0.0
                            END
                        ),
                        0.0
                    ) AS cost_24h
                FROM trace_steps
                JOIN traces ON traces.trace_id = trace_steps.trace_id
                WHERE trace_steps.provider_name IS NOT NULL
                  AND traces.tenant_id = ?
                GROUP BY trace_steps.provider_name
                """,
                (cutoff_1m, cutoff_1m, cutoff_1d, tenant_id),
            ).fetchall()

        for provider_name, requests_1m, tokens_1m, last_success_at, cost_24h in rows:
            stats_by_provider[str(provider_name)] = {
                "requests_1m": int(requests_1m or 0),
                "tokens_1m": int(tokens_1m or 0),
                "last_success_at": last_success_at,
                "cost_24h": round(float(cost_24h or 0.0), 6),
            }

    providers = []
    for provider in registry.providers:
        stats = stats_by_provider.get(
            provider.id,
            {
                "requests_1m": 0,
                "tokens_1m": 0,
                "last_success_at": None,
                "cost_24h": 0.0,
            },
        )
        configured = provider.kind != "paid"
        if provider.api_key_env:
            configured = configured or bool((os.getenv(provider.api_key_env, "") or "").strip())
        providers.append(
            {
                "id": provider.id,
                "label": provider.label,
                "kind": provider.kind,
                "enabled": provider.enabled,
                "configured": configured,
                "api_key_env": provider.api_key_env,
                "default_models": provider.default_models.model_dump(mode="json"),
                "capabilities": provider.capabilities.model_dump(mode="json"),
                "rate_limits": provider.rate_limits.model_dump(mode="json"),
                "models": [model.model_dump(mode="json") for model in provider.models],
                "usage_1m": {
                    "requests": stats["requests_1m"],
                    "tokens": stats["tokens_1m"],
                    "requests_pct": round(
                        (stats["requests_1m"] / provider.rate_limits.requests_per_minute) * 100,
                        2,
                    )
                    if provider.rate_limits.requests_per_minute
                    else 0.0,
                    "tokens_pct": round(
                        (stats["tokens_1m"] / provider.rate_limits.tokens_per_minute) * 100,
                        2,
                    )
                    if provider.rate_limits.tokens_per_minute
                    else 0.0,
                },
                "cost_24h_usd": stats["cost_24h"],
                "last_success_at": stats["last_success_at"],
            }
        )

    profiles = {
        profile_name: {
            "description": profile.description,
            "fast": profile.fast.model_dump(mode="json"),
            "strong": profile.strong.model_dump(mode="json"),
        }
        for profile_name, profile in registry.routing_profiles.items()
    }
    return {
        "default_profile": registry.default_profile,
        "active_profile": str(getattr(settings, "llm_provider_profile", registry.default_profile)),
        "profiles": profiles,
        "providers": providers,
    }


async def _list_regression_run_rows(limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    async with async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        run_id,
                        created_at,
                        value,
                        sample_size,
                        drift_alert,
                        baseline_experiment_id,
                        candidate_experiment_id,
                        report_path
                    FROM eval_results
                    WHERE kind = 'regression'
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).mappings().all()
    return [dict(row) for row in rows]


async def _get_regression_run_row(run_id: str) -> dict[str, Any] | None:
    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    async with async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        run_id,
                        created_at,
                        value,
                        sample_size,
                        drift_alert,
                        baseline_experiment_id,
                        candidate_experiment_id,
                        report_path
                    FROM eval_results
                    WHERE kind = 'regression' AND run_id = :run_id
                    LIMIT 1
                    """
                ),
                {"run_id": run_id},
            )
        ).mappings().all()
    if not rows:
        return None
    return dict(rows[0])


def _serialize_regression_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row.get("run_id") or ""),
        "status": "completed",
        "result": "fail" if bool(row.get("drift_alert")) else "pass",
        "created_at": _serialize_timestamp(row.get("created_at")),
        "baseline": str(row.get("baseline_experiment_id") or "current"),
        "candidate": str(row.get("candidate_experiment_id") or "current"),
        "candidate_pass_rate": float(row.get("value") or 0.0),
        "sample_size": int(row.get("sample_size") or 0),
        "report_path": row.get("report_path"),
    }


async def _run_regression_job(run_id: str, baseline: str, candidate: str) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from scripts import regression_eval  # noqa: PLC0415

    job = _regression_jobs.setdefault(
        run_id,
        {
            "run_id": run_id,
            "status": "queued",
            "baseline": baseline,
            "candidate": candidate,
            "created_at": datetime.now(timezone.utc),
        },
    )
    job["status"] = "running"
    job["started_at"] = datetime.now(timezone.utc)

    started_monotonic = time.monotonic()
    try:
        report = await asyncio.to_thread(
            regression_eval.run_regression,
            baseline=baseline,
            candidate=candidate,
            dataset_path=_project_root_path() / "evaluation" / "curated_cases.jsonl",
            project_root=_project_root_path(),
        )
        _markdown_path, json_path = await asyncio.to_thread(
            regression_eval.write_report_files,
            report,
            project_root=_project_root_path(),
        )
        await regression_eval.persist_regression_result(
            session_factory=async_session,
            report=report,
            report_path=json_path.relative_to(_project_root_path()),
        )

        result = "pass" if bool(report["gate"]["passed"]) else "fail"
        duration_sec = max(time.monotonic() - started_monotonic, 0.0)
        prometheus_metrics.record_regression_run(result, duration_sec)
        prometheus_metrics.set_regression_last_pass_rate(
            report["baseline"],
            report["candidate"],
            float(report["aggregate"]["candidate_pass_rate"]),
        )

        job.update(
            {
                "status": "completed",
                "result": result,
                "finished_at": datetime.now(timezone.utc),
                "exit_code": int(report["exit_code"]),
                "report_path": str(json_path.relative_to(_project_root_path()).as_posix()),
                "aggregate": report["aggregate"],
                "gate": report["gate"],
            }
        )
    except Exception as exc:
        duration_sec = max(time.monotonic() - started_monotonic, 0.0)
        prometheus_metrics.record_regression_run("fail", duration_sec)
        job.update(
            {
                "status": "error",
                "finished_at": datetime.now(timezone.utc),
                "error": str(exc),
            }
        )


def _curated_dataset_path() -> Path:
    return Path(getattr(get_settings(), "project_root", PROJECT_ROOT)) / "evaluation" / "curated_cases.jsonl"


def _curated_dataset_job_key(job_id: str) -> str:
    return f"curated-dataset-job:{job_id}"


def _store_curated_dataset_job(job_id: str, payload: dict[str, Any]) -> None:
    cache_json_set(_curated_dataset_job_key(job_id), payload, ttl_seconds=86400)


def _curated_dataset_summary(path: Path | None = None) -> dict[str, Any]:
    from evaluation.dataset import load_curated_cases  # noqa: PLC0415

    dataset_path = path or _curated_dataset_path()
    cases = load_curated_cases(dataset_path)

    verdict_counts = {"good": 0, "bad": 0}
    tenant_counts: dict[str, dict[str, int]] = {}
    channel_counts: dict[str, int] = {}

    for case in cases:
        verdict_counts[case.human_verdict] = verdict_counts.get(case.human_verdict, 0) + 1

        tenant_bucket = tenant_counts.setdefault(
            case.tenant_id,
            {"good": 0, "bad": 0, "total": 0},
        )
        tenant_bucket[case.human_verdict] = tenant_bucket.get(case.human_verdict, 0) + 1
        tenant_bucket["total"] += 1

        channel = str(case.input.channel or "web")
        channel_counts[channel] = channel_counts.get(channel, 0) + 1

    for tenant_id, counts in tenant_counts.items():
        prometheus_metrics.set_curated_dataset_size("good", tenant_id, counts.get("good", 0))
        prometheus_metrics.set_curated_dataset_size("bad", tenant_id, counts.get("bad", 0))

    last_build_timestamp = dataset_path.stat().st_mtime if dataset_path.exists() else 0.0
    prometheus_metrics.set_curated_dataset_last_build_timestamp(last_build_timestamp)

    return {
        "count": len(cases),
        "verdict_counts": verdict_counts,
        "tenant_counts": tenant_counts,
        "channel_counts": channel_counts,
    }


async def _run_curated_dataset_rebuild(
    *,
    job_id: str,
    tenant: str,
    since: str | None,
    include_bad: bool,
) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    from scripts import build_curated_dataset  # noqa: PLC0415

    dataset_path = _curated_dataset_path()
    _store_curated_dataset_job(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "tenant": tenant,
            "since": since,
            "include_bad": include_bad,
            "progress": 25,
            "out": str(dataset_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        result = await build_curated_dataset.run_once(
            tenant=tenant,
            since=since,
            out=dataset_path,
            include_bad=include_bad,
            settings=get_settings(),
        )
        summary = _curated_dataset_summary(dataset_path)
        _store_curated_dataset_job(
            job_id,
            {
                "job_id": job_id,
                "status": "completed",
                "tenant": tenant,
                "since": since,
                "include_bad": include_bad,
                "progress": 100,
                "out": str(dataset_path),
                "result": result,
                "summary": summary,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        _store_curated_dataset_job(
            job_id,
            {
                "job_id": job_id,
                "status": "failed",
                "tenant": tenant,
                "since": since,
                "include_bad": include_bad,
                "progress": 100,
                "out": str(dataset_path),
                "error": str(exc),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def _load_recent_trace_summaries(tenant_id: str, days: int) -> list[dict[str, Any]]:
    import json  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from tracing import sqlite_trace  # noqa: PLC0415

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    settings = get_settings()
    model_prices = getattr(settings, "llm_model_prices", {}) or {}
    default_input_price = float(getattr(settings, "llm_input_price_per_1m_tokens", 0.0) or 0.0)
    default_output_price = float(getattr(settings, "llm_output_price_per_1m_tokens", 0.0) or 0.0)
    input_price_case = "?"
    output_price_case = "?"
    input_price_params: list[Any] = [default_input_price]
    output_price_params: list[Any] = [default_output_price]

    if model_prices:
        input_price_case = (
            "CASE latest.model_name "
            + " ".join("WHEN ? THEN ?" for _ in model_prices.items())
            + " ELSE ? END"
        )
        output_price_case = (
            "CASE latest.model_name "
            + " ".join("WHEN ? THEN ?" for _ in model_prices.items())
            + " ELSE ? END"
        )
        input_price_params = []
        output_price_params = []
        for model_name, prices in model_prices.items():
            input_price_params.extend(
                [str(model_name), float(prices.get("input", default_input_price) or 0.0)]
            )
            output_price_params.extend(
                [str(model_name), float(prices.get("output", default_output_price) or 0.0)]
            )
        input_price_params.append(default_input_price)
        output_price_params.append(default_output_price)

    summaries: list[dict[str, Any]] = []
    with sqlite_trace._get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                f"""
                SELECT
                    traces.trace_id,
                    traces.started_at,
                    traces.final_route,
                    traces.final_quality,
                    latest.state_json,
                    latest.model_name,
                    COALESCE(
                        NULLIF(latest.cost_usd, 0.0),
                        (
                            (
                                COALESCE(latest.prompt_tokens, 0) * {input_price_case}
                            ) + (
                                COALESCE(latest.completion_tokens, 0) * {output_price_case}
                            )
                        ) / 1000000.0
                    ) AS cost_usd
                FROM traces
                LEFT JOIN trace_steps AS latest
                    ON latest.id = (
                        SELECT step.id
                        FROM trace_steps AS step
                        WHERE step.trace_id = traces.trace_id
                        ORDER BY step.step_order DESC, step.id DESC
                        LIMIT 1
                    )
                WHERE traces.tenant_id = ? AND traces.started_at >= ?
                ORDER BY traces.started_at DESC
                """,
                (
                    *input_price_params,
                    *output_price_params,
                    tenant_id,
                    cutoff,
                ),
            )
        except sqlite3.OperationalError:
            cur.execute(
                """
                SELECT
                    traces.trace_id,
                    traces.started_at,
                    traces.final_route,
                    traces.final_quality,
                    latest.state_json,
                    NULL AS model_name,
                    0.0 AS cost_usd
                FROM traces
                LEFT JOIN trace_steps AS latest
                    ON latest.id = (
                        SELECT step.id
                        FROM trace_steps AS step
                        WHERE step.trace_id = traces.trace_id
                        ORDER BY step.step_order DESC, step.id DESC
                        LIMIT 1
                    )
                WHERE traces.tenant_id = ? AND traces.started_at >= ?
                ORDER BY traces.started_at DESC
                """,
                (tenant_id, cutoff),
            )
        for trace_id, started_at, final_route, final_quality, state_json, model_name, cost_usd in cur.fetchall():
            state: dict[str, Any] = {}
            if state_json:
                try:
                    state = json.loads(state_json)
                except Exception:
                    state = {}
            docs = state.get("graded_docs") or state.get("context_docs") or []
            categories: set[str] = set()
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                metadata = doc.get("metadata", {}) or {}
                for item in metadata.get("categories") or []:
                    categories.add(str(item))
                if not categories and metadata.get("primary_category"):
                    categories.add(str(metadata.get("primary_category")))
            summaries.append(
                {
                    "trace_id": trace_id,
                    "created_at": datetime.fromisoformat(started_at),
                    "route": final_route or state.get("route") or "unknown",
                    "quality_score": int(final_quality or state.get("quality_score") or 0),
                    "categories": sorted(categories) or ["uncategorized"],
                    "cost_usd": float(cost_usd or 0.0),
                    "model_name": str(model_name or state.get("model_name") or "unknown"),
                }
            )
    return summaries


async def _record_citation_stats(tenant_id: str, citations: list[CitationModel]) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import DocumentStats  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    async with async_session() as db:
        for citation in citations:
            doc_id = str(citation.doc_id or "").strip()
            if not doc_id:
                continue
            result = await db.execute(
                select(DocumentStats).where(
                    DocumentStats.tenant_id == tenant_id,
                    DocumentStats.doc_id == doc_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                db.add(
                    DocumentStats(
                        tenant_id=tenant_id,
                        doc_id=doc_id,
                        citation_count=1,
                        last_cited_at=now,
                    )
                )
            else:
                row.citation_count += 1
                row.last_cited_at = now
        await db.commit()


def _cache_key(tenant: str, question: str) -> str:
    normalized_question = question.strip().lower()
    question_hash = hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()[:16]
    return f"llm_resp:{tenant or 'default'}:{question_hash}"


async def _get_or_create_session(
    session_id: Optional[str],
    tenant_id: str = "default",
) -> tuple:
    global _retriever, _llm, _db_retry_after

    if not session_id:
        session_id = uuid.uuid4().hex
    else:
        try:
            session_id = uuid.UUID(session_id).hex
        except (TypeError, ValueError, AttributeError):
            pass

    db_history: List[Dict[str, str]] = []
    if time.monotonic() >= _db_retry_after:
        try:
            from datetime import datetime, timezone

            from sqlalchemy import select

            from db.engine import async_session
            from db.models import Message, Session as DBSession

            async with async_session() as db:
                session_uuid = uuid.UUID(session_id)
                result = await asyncio.wait_for(
                    db.execute(select(DBSession).where(DBSession.id == session_uuid)),
                    timeout=0.5,
                )
                db_session = result.scalar_one_or_none()
                if db_session is None:
                    db.add(DBSession(id=session_uuid, tenant_id=tenant_id))
                else:
                    db_session.last_access = datetime.now(timezone.utc)
                    if not db_session.tenant_id or db_session.tenant_id == "default":
                        db_session.tenant_id = tenant_id
                await asyncio.wait_for(db.commit(), timeout=0.5)

                history_result = await asyncio.wait_for(
                    db.execute(
                        select(Message.role, Message.content)
                        .where(Message.session_id == session_uuid)
                        .order_by(Message.created_at)
                    ),
                    timeout=0.5,
                )
                db_history = [
                    {"role": role, "content": content}
                    for role, content in history_result.all()
                ]
                _db_retry_after = 0.0
        except Exception as exc:
            _db_retry_after = time.monotonic() + 60.0
            logger.warning("DB session fallback to memory: %s", exc)

    session_retriever = _retriever
    settings = get_settings()
    chroma_dir = getattr(settings, "vectordb_chroma_dir", None)
    has_persisted_store = (
        chroma_dir is not None
        and Path(chroma_dir).exists()
        and any(Path(chroma_dir).iterdir())
    )
    if _get_retriever is not None and (_retriever is not None or _vector_store is not None or has_persisted_store):
        try:
            retriever_params = inspect.signature(_get_retriever).parameters
            if "tenant_id" in retriever_params or any(
                param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                for param in retriever_params.values()
            ):
                session_retriever = _get_retriever(tenant_id=tenant_id)
        except Exception as exc:
            logger.warning("Failed to resolve retriever for tenant %s: %s", tenant_id, exc)

    existing_session = _session_llm_state.get(session_id)
    tenant_mismatch = (
        hasattr(existing_session, "ask")
        and getattr(existing_session, "_tenant_id", "default") != tenant_id
    )

    if session_id not in _session_llm_state or tenant_mismatch:
        if _ConversationSession is not None and session_retriever is not None:
            session = _ConversationSession(
                retriever=session_retriever,
                llm=_llm,
                max_iterations=max(0, int(getattr(settings, "self_rag_max_iterations", 2) or 0)),
                max_history=20,
            )
            setattr(session, "_tenant_id", tenant_id)
            if session_id not in _session_llm_state and db_history and hasattr(session, "_history"):
                max_history = getattr(session, "_max_history", 20)
                session._history = db_history[-(max_history * 2):]
            _session_llm_state[session_id] = session
        else:
            _session_llm_state[session_id] = {"history": list(db_history), "tenant_id": tenant_id}
    elif (
        existing_session is not None
        and hasattr(existing_session, "_retriever")
        and session_retriever is not None
    ):
        setattr(existing_session, "_retriever", session_retriever)
        setattr(existing_session, "_tenant_id", tenant_id)
    elif isinstance(existing_session, dict):
        existing_session["tenant_id"] = tenant_id

    import time as _time
    _session_last_access[session_id] = _time.monotonic()
    return session_id, _session_llm_state[session_id]


# ---------------------------------------------------------------------------
# Startup logic
# ---------------------------------------------------------------------------

def _is_embedding_dimension_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "dimension" in message and ("embedding" in message or "expecting" in message or "got" in message)


def _validate_vector_store_embedding_compatibility(vector_store: Any, embeddings: Any) -> None:
    if not hasattr(embeddings, "embed_query"):
        return

    collection = getattr(vector_store, "_collection", None)
    if collection is not None and hasattr(collection, "count"):
        try:
            if int(collection.count()) == 0:
                return
        except Exception:
            pass

    try:
        probe_vector = embeddings.embed_query("embedding compatibility probe")
        if collection is not None and hasattr(collection, "query"):
            collection.query(query_embeddings=[probe_vector], n_results=1)
            return
        if hasattr(vector_store, "similarity_search_by_vector"):
            vector_store.similarity_search_by_vector(probe_vector, k=1)
    except Exception as exc:
        if _is_embedding_dimension_error(exc):
            raise
        logger.warning("Could not validate existing Chroma embedding compatibility: %s", exc)


def initialize_vector_store() -> None:
    global _vector_store, _retriever, _chunks

    if _vector_store is not None and _retriever is not None:
        return

    with _vector_store_init_lock:
        if _vector_store is not None and _retriever is not None:
            return

        settings = get_settings()
        chroma_dir = settings.vectordb_chroma_dir
        collection_name = f"{getattr(settings, 'vectordb_collection_prefix', 'rag_docs')}_default"

        if _Chroma is not None and chroma_dir.exists() and any(chroma_dir.iterdir()):
            try:
                if _get_embeddings is not None:
                    embeddings = _get_embeddings()
                else:
                    logger.warning("get_embeddings not available, skipping vector store load")
                    return

                vector_store = _Chroma(
                    persist_directory=str(chroma_dir),
                    embedding_function=embeddings,
                    collection_name=collection_name,
                )
                try:
                    _validate_vector_store_embedding_compatibility(vector_store, embeddings)
                except Exception as exc:
                    logger.error(
                        "Existing Chroma store at %s is incompatible with embedding model %s: %s. "
                        "Rebuild the vector store before running RAG.",
                        chroma_dir,
                        getattr(settings, "embedding_model", "unknown"),
                        exc,
                    )
                    _vector_store = None
                    _retriever = None
                    return

                _vector_store = vector_store

                if _get_retriever is not None:
                    retriever_params = inspect.signature(_get_retriever).parameters
                    if "tenant_id" in retriever_params or any(
                        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                        for param in retriever_params.values()
                    ):
                        _retriever = _get_retriever(_vector_store, chunks=None, tenant_id="default")
                    else:
                        _retriever = _get_retriever(_vector_store, chunks=None)
                else:
                    _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

                logger.info("Vector store loaded from %s", chroma_dir)
                return
            except Exception as exc:
                logger.error("Failed to load existing Chroma: %s", exc, exc_info=True)

        logger.info("No existing vector store found. Upload documents via /api/upload to create one.")


def _rebuild_vector_store_from_docs(
    docs: List[Any],
    tenant_id: str = "default",
) -> bool:
    global _vector_store, _retriever, _chunks

    if _build_vector_store is None:
        logger.warning("build_vector_store not available")
        return False

    with _vector_store_init_lock:
        try:
            settings = get_settings()
            chunk_config = {
                "chunk_size": getattr(settings, "chunk_size", 800),
                "chunk_overlap": getattr(settings, "chunk_overlap", 200),
            }
            build_params = inspect.signature(_build_vector_store).parameters
            if "tenant_id" in build_params or any(
                param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                for param in build_params.values()
            ):
                _vector_store, _chunks = _build_vector_store(
                    docs,
                    chunk_config,
                    tenant_id=tenant_id,
                )
            else:
                _vector_store, _chunks = _build_vector_store(docs, chunk_config)

            if _get_retriever is not None:
                retriever_params = inspect.signature(_get_retriever).parameters
                if "tenant_id" in retriever_params or any(
                    param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                    for param in retriever_params.values()
                ):
                    _retriever = _get_retriever(_vector_store, chunks=_chunks, tenant_id=tenant_id)
                else:
                    _retriever = _get_retriever(_vector_store, chunks=_chunks)
            elif hasattr(_vector_store, "as_retriever"):
                _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

            for sid, session in _sessions.items():
                if hasattr(session, "_retriever") and getattr(session, "_tenant_id", "default") == tenant_id:
                    session._retriever = _retriever

            logger.info("Vector store rebuilt: %d chunks", len(_chunks))
            return True
        except Exception as exc:
            logger.error("Failed to rebuild vector store: %s", exc, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Health probe helpers
# ---------------------------------------------------------------------------

async def _probe_ollama(base_url: str) -> ComponentStatus:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
        return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


async def _probe_gracekelly(base_url: str, timeout_sec: float = 2.0) -> ComponentStatus:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/healthz/ready")
            resp.raise_for_status()
        return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


async def _probe_chromadb(chroma_dir: Path) -> ComponentStatus:
    t0 = time.monotonic()
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir))
        client.list_collections()
        return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


async def _probe_sqlite(db_path: Path) -> ComponentStatus:
    t0 = time.monotonic()
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path), timeout=1)
        conn.execute("SELECT 1")
        conn.close()
        return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


async def _probe_postgres() -> ComponentStatus:
    t0 = time.monotonic()
    try:
        import os

        if not os.getenv("DATABASE_URL"):
            return ComponentStatus(
                status="unavailable",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                detail="DATABASE_URL not configured",
            )

        from db.engine import async_session, get_pool_stats
        from sqlalchemy import text

        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=1.0)

        try:
            stats = get_pool_stats()
            from monitoring.prometheus import record_db_pool_stats

            record_db_pool_stats(
                stats["size"],
                stats["checked_out"],
                stats["overflow"],
            )
        except Exception:
            pass

        return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except ImportError as exc:
        return ComponentStatus(
            status="unavailable",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            detail=f"driver missing: {exc}",
        )
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


async def _probe_redis() -> ComponentStatus:
    t0 = time.monotonic()
    try:
        import os
        import redis

        from config.settings import get_settings

        if not os.getenv("REDIS_URL"):
            return ComponentStatus(
                status="unavailable",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                detail="REDIS_URL not configured",
            )

        settings = get_settings()
        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        ok = await asyncio.wait_for(asyncio.to_thread(client.ping), timeout=1.5)
        if ok:
            return ComponentStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
        return ComponentStatus(
            status="error",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            detail="PING returned falsy",
        )
    except ImportError as exc:
        return ComponentStatus(
            status="unavailable",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            detail=f"redis lib missing: {exc}",
        )
    except Exception as exc:
        return ComponentStatus(status="error", latency_ms=round((time.monotonic() - t0) * 1000, 1), detail=str(exc))


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

def _run_alembic_upgrade() -> None:
    """Apply pending alembic migrations. Idempotent.

    Gated on AUTO_MIGRATE env (default "true"). In production, migration
    failures abort startup unless AUTO_MIGRATE_FAIL_OPEN=true is explicit.
    """
    import os

    if os.getenv("AUTO_MIGRATE", "true").strip().lower() not in ("1", "true", "yes"):
        return

    project_root = Path(__file__).resolve().parent.parent
    cfg_path = project_root / "alembic.ini"
    if not cfg_path.exists():
        logger.warning("alembic.ini not found at %s; skipping auto-migrate", cfg_path)
        return
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(cfg_path))
        cfg.set_main_option("script_location", str(project_root / "alembic"))
        command.upgrade(cfg, "head")
        logger.info("alembic upgrade head: OK")
    except Exception as exc:  # noqa: BLE001
        fail_open = os.getenv("AUTO_MIGRATE_FAIL_OPEN", "false").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if getattr(get_settings(), "rag_env", "development") == "production" and not fail_open:
            logger.error("alembic auto-migrate failed in production: %s", exc)
            raise RuntimeError("alembic auto-migrate failed in production") from exc
        logger.warning("alembic auto-migrate skipped: %s", exc)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    global _shutting_down
    settings = get_settings()
    app.state.settings = settings
    settings.ensure_dirs()

    try:
        settings.validate()
    except RuntimeError as exc:
        logger.error("Startup validation failed: %s", exc)
        raise SystemExit(1) from exc

    await asyncio.get_running_loop().run_in_executor(None, _run_alembic_upgrade)

    try:
        from db.engine import engine as db_engine  # noqa: PLC0415
        from tracing.otel import init_otel  # noqa: PLC0415

        init_otel(
            app=app,
            service_name=getattr(settings, "otel_service_name", "rag-support-assistant"),
            endpoint=getattr(settings, "otel_exporter_otlp_endpoint", "http://localhost:4317"),
            enabled=getattr(settings, "otel_enabled", False),
            sqlalchemy_engine=getattr(db_engine, "sync_engine", db_engine),
            request_id_getter=get_request_id,
        )
    except Exception as exc:
        logger.warning("OTel initialization skipped: %s", exc)

    _shutting_down = False
    initialize_vector_store()
    async def _cleanup_sessions() -> None:
        import time as _time
        settings = get_settings()
        while True:
            await asyncio.sleep(600)
            cutoff = _time.monotonic() - settings.session_ttl_seconds
            stale = [sid for sid, ts in _session_last_access.items() if ts < cutoff]
            for sid in stale:
                _sessions.pop(sid, None)
                _session_last_access.pop(sid, None)
            if stale:
                logger.info("Cleaned up %d stale sessions", len(stale))

    async def _purge_old_traces_periodically() -> None:
        settings = get_settings()
        interval = max(60, getattr(settings, "trace_purge_interval_sec", 86400))
        retention = getattr(settings, "trace_retention_days", 90)
        if retention <= 0:
            logger.info("Trace retention disabled (TRACE_RETENTION_DAYS=0)")
            return

        while True:
            await asyncio.sleep(interval)
            try:
                from tracing.sqlite_trace import purge_old_traces

                result = await asyncio.to_thread(purge_old_traces, retention)
                for table, count in (
                    ("traces", result["traces_deleted"]),
                    ("trace_steps", result["steps_deleted"]),
                    ("feedback", result["feedback_deleted"]),
                ):
                    prometheus_metrics.record_traces_purged(table, count)
                if result["traces_deleted"]:
                    logger.info(
                        "Trace retention purge: traces=%d steps=%d feedback=%d",
                        result["traces_deleted"],
                        result["steps_deleted"],
                        result["feedback_deleted"],
                    )
            except Exception as exc:
                logger.warning("Trace retention purge failed: %s", exc)

    async def _purge_old_audit_periodically() -> None:
        settings = get_settings()
        interval = max(60, getattr(settings, "audit_purge_interval_sec", 86400))
        retention = getattr(settings, "audit_retention_days", 180)
        if retention <= 0:
            logger.info("Audit retention disabled (AUDIT_RETENTION_DAYS=0)")
            return

        while True:
            await asyncio.sleep(interval)
            try:
                from db.audit import purge_old_audit

                deleted = await purge_old_audit(retention)
                if deleted:
                    try:
                        prometheus_metrics.record_audit_purged(deleted)
                    except Exception:
                        pass
                    logger.info("Audit retention purge: %d rows", deleted)
            except Exception as exc:
                logger.warning("Audit retention purge failed: %s", exc)

    cleanup_task = asyncio.create_task(_cleanup_sessions())
    purge_task = asyncio.create_task(_purge_old_traces_periodically())
    audit_purge_task = asyncio.create_task(_purge_old_audit_periodically())
    logger.info("RAG Support Assistant started")
    try:
        yield
    finally:
        _shutting_down = True
        delay = float(getattr(settings, "shutdown_ready_delay_sec", 0.0))
        if delay > 0:
            logger.info(
                "Shutdown: flipping readiness to 503, draining for %.1fs",
                delay,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                pass
        cleanup_task.cancel()
        purge_task.cancel()
        audit_purge_task.cancel()
        logger.info("RAG Support Assistant shutting down")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["RAG API"])

# Sub-routers extracted from this monolith. See api/routers/ and DEPRECATIONS.md.
from api.routers.admin_kb import router as _admin_kb_router  # noqa: E402
from api.routers.admin_experiments import router as _admin_experiments_router  # noqa: E402
from api.routers.admin_evaluations import router as _admin_evaluations_router  # noqa: E402
from api.routers.admin_ops import router as _admin_ops_router  # noqa: E402
from api.routers.admin_review import router as _admin_review_router  # noqa: E402
from api.routers.analytics import router as _analytics_router  # noqa: E402
from api.routers.agent import router as _agent_router  # noqa: E402
from api.routers.auth_sso import router as _auth_sso_router  # noqa: E402
from api.routers import conversation as _conversation_router_module  # noqa: E402
from api.routers.feedback import router as _feedback_router  # noqa: E402
from api.routers.misc import email_inbound_webhook, router as _misc_router  # noqa: E402
from api.routers import root_pages as _root_pages_router_module  # noqa: E402
from api.routers import session_auth as _session_auth_router_module  # noqa: E402
from api.routers import system as _system_router_module  # noqa: E402
from api.routers import upload as _upload_router_module  # noqa: E402

AskRequest = _conversation_router_module.AskRequest
AskResponse = _conversation_router_module.AskResponse
Citation = _conversation_router_module.Citation
SourceInfo = _conversation_router_module.SourceInfo
ask = _conversation_router_module.ask
ask_stream = _conversation_router_module.ask_stream
chat = _conversation_router_module.chat
chat_stream = _conversation_router_module.chat_stream
_conversation_router = _conversation_router_module.router
health_check = _system_router_module.health_check
health_liveness = _system_router_module.health_liveness
health_readiness = _system_router_module.health_readiness
_system_router = _system_router_module.router
TaskStatusResponse = _upload_router_module.TaskStatusResponse
UploadResponse = _upload_router_module.UploadResponse
_upload_router = _upload_router_module.router
LoginRequest = _session_auth_router_module.LoginRequest
TokenResponse = _session_auth_router_module.TokenResponse
RefreshRequest = _session_auth_router_module.RefreshRequest
SessionInfo = _session_auth_router_module.SessionInfo
HistoryMessage = _session_auth_router_module.HistoryMessage
HistoryResponse = _session_auth_router_module.HistoryResponse
login = _session_auth_router_module.login
refresh_token = _session_auth_router_module.refresh_token
get_session_history = _session_auth_router_module.get_session_history
list_sessions = _session_auth_router_module.list_sessions
clear_session = _session_auth_router_module.clear_session
_session_auth_router = _session_auth_router_module.router
agent_dashboard = _root_pages_router_module.agent_dashboard
admin_trace_detail_redirect = _root_pages_router_module.admin_trace_detail_redirect
prometheus_metrics_endpoint = _root_pages_router_module.prometheus_metrics_endpoint
_root_pages_router = _root_pages_router_module.router

router.include_router(_system_router)
router.include_router(_agent_router)
router.include_router(_admin_kb_router)
router.include_router(_admin_experiments_router)
router.include_router(_admin_evaluations_router)
router.include_router(_admin_ops_router)
router.include_router(_admin_review_router)
router.include_router(_analytics_router)
router.include_router(_auth_sso_router)
router.include_router(_conversation_router)
router.include_router(_feedback_router)
router.include_router(_misc_router)
router.include_router(_session_auth_router)
router.include_router(_upload_router)


# /ask, /ask/stream, /chat, and /chat/stream moved to api.routers.conversation

# /feedback, /feedback/stats, and /escalate moved to api.routers.feedback
# /agent/tickets/* and /agent/similar moved to api.routers.agent


# /api/metrics moved to api.routers.system
# /agent, /admin/traces/{trace_id}, and /metrics moved to api.routers.root_pages


# /admin/circuit-breaker/reset, /admin/audit, /admin/traces/*,
# and /admin/audit-log moved to api.routers.admin_ops
# /admin/review-queue/* moved to api.routers.admin_review
# /admin/curated-dataset/*, /admin/thresholds/*,
# /admin/improvement-backlog/*, and /admin/recommendations/* moved to api.routers.admin_kb
# /admin/kb-gaps, /admin/categories, and /admin/kb-drafts/* moved to api.routers.admin_kb
# /admin/experiments/* moved to api.routers.admin_experiments
# /admin/evaluations/* and /admin/regression-runs/* moved to api.routers.admin_evaluations
# /admin/stale-docs/* moved to api.routers.admin_kb
# /analytics/* moved to api.routers.analytics
# /channels/email/inbound and /admin/providers moved to api.routers.misc
# /upload and /tasks/{task_id} moved to api.routers.upload


# /auth/sso/* moved to api.routers.auth_sso




# /health/live, /health/ready, and /health moved to api.routers.system


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_app_settings = get_settings()
_docs_enabled = getattr(_app_settings, "rag_env", "development") != "production"
app = FastAPI(
    title="RAG Support Assistant API",
    version="0.3.0",
    lifespan=_lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Session + CORS
app.add_middleware(
    SessionMiddleware,
    secret_key=getattr(_app_settings, "session_secret_key", "dev-secret-change-in-production!"),
    same_site="lax",
    https_only=getattr(_app_settings, "rag_env", "development") == "production",
)
_cors_settings = _app_settings
if "*" in _cors_settings.cors_origins:
    if _cors_settings.rag_env == "development":
        logger.warning(
            "CORS_ORIGINS='*' - OK for development, but set explicit origins "
            "before deploying to production (RAG_ENV=production will refuse to start)."
        )
    else:
        logger.error(
            "CORS_ORIGINS='*' in RAG_ENV=%s - tighten before production",
            _cors_settings.rag_env,
        )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
    max_age=_cors_settings.cors_max_age_sec,
)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if getattr(get_settings(), "rag_env", "development") == "production":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


@app.middleware("http")
async def _log_requests(request: Request, call_next: Any) -> Any:
    t0 = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - t0) * 1000, 1)
    logger.info(
        "req_id=%s %s %s -> %d (%.1fms)",
        get_request_id() or "-",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def _extract_route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path_format: str | None = getattr(route, "path_format", None)
        if path_format:
            return path_format

        path: str | None = getattr(route, "path", None)
        if path:
            return path

    return "unknown"


@app.middleware("http")
async def _http_metrics(request: Request, call_next: Any) -> Any:
    import time as _time

    t0 = _time.monotonic()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        try:
            prometheus_metrics.record_http_request(
                request.method,
                _extract_route_template(request),
                500,
                _time.monotonic() - t0,
            )
        except Exception:
            pass
        raise

    try:
        prometheus_metrics.record_http_request(
            request.method,
            _extract_route_template(request),
            status,
            _time.monotonic() - t0,
        )
    except Exception:
        pass

    return response


@app.middleware("http")
async def _request_id(request: Request, call_next: Any) -> Any:
    incoming = sanitize_request_id(request.headers.get("X-Request-Id"))
    req_id = incoming or generate_request_id()
    set_request_id(req_id)

    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = get_request_id() or req_id
        return response
    finally:
        set_request_id(None)


@app.middleware("http")
async def _body_size_limit(request: Request, call_next: Any) -> Any:
    if request.url.path == "/api/upload":
        return await call_next(request)

    settings = get_settings()
    limit = getattr(settings, "max_request_body_bytes", 1024 * 1024)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            size = int(content_length)
        except ValueError:
            size = -1
        if size > limit:
            try:
                prometheus_metrics.record_body_size_rejection("content_length_too_large")
            except Exception:
                pass
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large ({size} bytes, limit {limit})"},
            )

    return await call_next(request)


@app.middleware("http")
async def _tenant_context(request: Request, call_next: Any) -> Any:
    tenant = "default"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.jwt_handler import verify_token

            token = auth_header[7:]
            payload = verify_token(token, expected_type="access")
            if payload is not None:
                tenant = payload.get("tenant", "default")
        except Exception:
            pass

    set_current_tenant(tenant)
    try:
        return await call_next(request)
    finally:
        set_current_tenant(None)


@app.middleware("http")
async def _cookie_auth_bridge(request: Request, call_next: Any) -> Any:
    if "authorization" not in request.headers:
        access_token = request.cookies.get("access_token")
        if access_token:
            headers = list(request.scope.get("headers", []))
            headers.append((b"authorization", f"Bearer {access_token}".encode("utf-8")))
            request.scope["headers"] = headers
    return await call_next(request)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cast(ExceptionHandler, _rate_limit_rejected))
app.include_router(router)
app.add_api_route("/webhook/email", email_inbound_webhook, methods=["POST"])
_static_dir = PROJECT_ROOT / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
app.include_router(_root_pages_router)

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
import re
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from api.correlation import (
    generate_request_id,
    get_current_tenant,
    get_request_id,
    sanitize_request_id,
    set_current_tenant,
    set_request_id,
)
from auth.dependencies import get_current_user, require_role
from auth.oidc import (
    get_oauth_client as get_oidc_client,
    list_sso_providers,
    resolve_oidc_user,
)
from cache.redis_cache import cache_delete_pattern, cache_json_get, cache_json_set
from db.audit import log_audit
from monitoring import prometheus as prometheus_metrics
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
except ImportError:
    class RateLimitExceeded(Exception):
        pass

    class Limiter:  # type: ignore[no-redef]
        def __init__(self, key_func):
            self.key_func = key_func

        def limit(self, value: str):
            _ = value

            def decorator(func):
                return func

            return decorator

    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    def get_remote_address(request: Request | None) -> str:
        if request is None or request.client is None:
            return "unknown"
        return request.client.host


def _rate_limit_rejected(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    try:
        prometheus_metrics.record_rate_limit_rejection(request.url.path)
    except Exception:
        pass
    return _rate_limit_exceeded_handler(request, exc)

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
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Safe imports with fallbacks
# ---------------------------------------------------------------------------

# LangChain Document
try:
    from langchain_core.documents import Document  # type: ignore
except ImportError:
    try:
        from langchain.schema import Document  # type: ignore
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
        from manager import build_vector_store, get_retriever, get_embeddings
        _build_vector_store = build_vector_store
        _get_retriever = get_retriever
        _get_embeddings = get_embeddings
    except ImportError:
        pass

# Document loader
_DocumentLoader = None
try:
    from loader import DocumentLoader
    _DocumentLoader = DocumentLoader
except ImportError:
    try:
        from ingestion.loader import DocumentLoader
        _DocumentLoader = DocumentLoader
    except ImportError:
        pass

# Chroma for loading existing store
_Chroma = None
try:
    from langchain_chroma import Chroma  # type: ignore
    _Chroma = Chroma
except ImportError:
    pass

# Settings
try:
    from config.settings import get_settings
except ImportError:
    def get_settings():  # type: ignore[misc]
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
        return _S()

_build_provider_runtime = None
try:
    from llm.providers import build_provider_runtime
    _build_provider_runtime = build_provider_runtime
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    confirm: Optional[bool] = None
    tenant_id: str = Field(
        default="default",
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )


class SourceInfo(BaseModel):
    source: str = ""
    page_content: str = ""


class Citation(BaseModel):
    index: int
    doc_id: str = ""
    title: str = ""
    excerpt: str = ""


class AskResponse(BaseModel):
    answer: str
    quality_score: int = 50
    route: str = "auto"
    sources: List[SourceInfo] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    suggested_questions: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    action_summary: str = ""


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., max_length=100)
    session_id: str = Field(..., max_length=100)
    rating: str = Field(..., pattern=r"^(up|down)$")
    reason: Optional[str] = Field(default="", max_length=500)


class EscalateRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    question: str = Field(default="", max_length=2000)
    reason: str = Field(default="user_request", max_length=200)


class AgentRespondRequest(BaseModel):
    response: str = Field(..., min_length=1, max_length=5000)


class KbDraftUpdateRequest(BaseModel):
    draft_content: str = Field(..., min_length=1, max_length=20000)


class ReviewQueueUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        pattern=r"^(pending|in_review|confirmed_good|confirmed_bad|dismissed)$",
    )
    reviewer_notes: str = Field(default="", max_length=5000)
    reviewed_by: Optional[str] = Field(default=None, max_length=64)


class SessionInfo(BaseModel):
    session_id: str
    message_count: int


class HistoryMessage(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[HistoryMessage]
    tenant_id: str = "default"


class ComponentStatus(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    components: Dict[str, ComponentStatus]
    vector_store_loaded: bool
    sessions_count: int
    pipeline_available: bool
    circuit_breakers: List[Dict[str, Any]] = Field(default_factory=list)
    features: Dict[str, bool] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    status: str
    filename: str
    message: str
    tenant_id: str = "default"
    assigned_categories: List[str] = Field(default_factory=list)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None
    meta: Optional[dict] = None


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


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
_REVIEW_QUEUE_REASONS = (
    "thumbs_down",
    "low_quality",
    "escalated",
    "fact_fail",
    "slow_trace",
    "manual",
)
_REVIEW_QUEUE_STATUSES = (
    "pending",
    "in_review",
    "confirmed_good",
    "confirmed_bad",
    "dismissed",
)
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


def _experiments_dir() -> Path:
    return Path(getattr(get_settings(), "project_root", PROJECT_ROOT)) / "evaluation" / "experiments"


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


def _review_queue_enabled() -> bool:
    return bool(getattr(get_settings(), "review_queue_enabled", True))


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


def _serialize_timestamp(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _reviewed_by_uuid(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        return str(uuid.UUID(str(raw_value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _load_review_queue_trace_details(trace_ids: list[str]) -> dict[str, dict[str, Any]]:
    import json  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415

    if not trace_ids:
        return {}

    db_path = Path(getattr(get_settings(), "tracing_db_path", ""))
    if not db_path.exists():
        return {}

    unique_trace_ids = list(dict.fromkeys(trace_ids))
    placeholders = ", ".join("?" for _ in unique_trace_ids)
    details: dict[str, dict[str, Any]] = {
        trace_id: {
            "quality": None,
            "duration_ms": None,
            "fact_score": None,
            "trace_url": f"/admin/traces/{trace_id}",
        }
        for trace_id in unique_trace_ids
    }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trace_rows = conn.execute(
            f"""
            SELECT trace_id, final_quality
            FROM traces
            WHERE trace_id IN ({placeholders})
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in trace_rows:
            trace_id = str(row["trace_id"])
            if row["final_quality"] is not None:
                details[trace_id]["quality"] = float(row["final_quality"])

        step_rows = conn.execute(
            f"""
            SELECT trace_id, state_json
            FROM trace_steps
            WHERE trace_id IN ({placeholders})
            ORDER BY trace_id ASC, step_order ASC, id ASC
            """,
            tuple(unique_trace_ids),
        ).fetchall()
        for row in step_rows:
            trace_id = str(row["trace_id"])
            state_json = row["state_json"]
            try:
                state = json.loads(state_json) if state_json else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                state = {}
            if not isinstance(state, dict):
                continue

            raw_duration = state.get("duration_ms")
            try:
                duration_ms = int(float(raw_duration)) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current_duration = details[trace_id]["duration_ms"]
                details[trace_id]["duration_ms"] = (
                    duration_ms
                    if current_duration is None
                    else max(int(current_duration), duration_ms)
                )

            raw_fact_score = state.get("factuality_score", state.get("fact_score"))
            try:
                fact_score = float(raw_fact_score) if raw_fact_score is not None else None
            except (TypeError, ValueError):
                fact_score = None
            if fact_score is not None:
                details[trace_id]["fact_score"] = fact_score

    return details


async def _refresh_review_queue_metrics(_tenant: str | None = None) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    try:
        pending_counts = {reason: 0 for reason in _REVIEW_QUEUE_REASONS}
        confirmed_counts = {"good": 0, "bad": 0}
        oldest_pending_seconds = 0.0

        async with async_session() as db:
            pending_rows = (
                await db.execute(
                    text(
                        """
                        SELECT reason, COUNT(*) AS total
                        FROM review_queue
                        WHERE status = 'pending'
                        GROUP BY reason
                        """
                    )
                )
            ).mappings().all()
            for row in pending_rows:
                reason = str(row["reason"])
                if reason in pending_counts:
                    pending_counts[reason] = int(row["total"] or 0)

            confirmed_rows = (
                await db.execute(
                    text(
                        """
                        SELECT status, COUNT(*) AS total
                        FROM review_queue
                        WHERE status IN ('confirmed_good', 'confirmed_bad')
                        GROUP BY status
                        """
                    )
                )
            ).mappings().all()
            for row in confirmed_rows:
                status = str(row["status"])
                if status == "confirmed_good":
                    confirmed_counts["good"] = int(row["total"] or 0)
                elif status == "confirmed_bad":
                    confirmed_counts["bad"] = int(row["total"] or 0)

            oldest_rows = (
                await db.execute(
                    text(
                        """
                        SELECT MIN(created_at) AS oldest_pending
                        FROM review_queue
                        WHERE status = 'pending'
                        """
                    )
                )
            ).mappings().all()
            oldest_pending = oldest_rows[0]["oldest_pending"] if oldest_rows else None
            if oldest_pending is not None:
                if isinstance(oldest_pending, str):
                    oldest_pending = datetime.fromisoformat(oldest_pending)
                if oldest_pending.tzinfo is None:
                    oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
                oldest_pending_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - oldest_pending).total_seconds(),
                )

        for reason, count in pending_counts.items():
            prometheus_metrics.set_review_queue_pending(reason, count)
        for verdict, count in confirmed_counts.items():
            prometheus_metrics.set_review_queue_confirmed(verdict, count)
        prometheus_metrics.set_review_queue_oldest_pending(oldest_pending_seconds)
    except Exception:
        return None


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

    import sqlite_trace  # noqa: PLC0415

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


async def _record_citation_stats(tenant_id: str, citations: list[Citation]) -> None:
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
                    db.add(DBSession(id=session_uuid))
                else:
                    db_session.last_access = datetime.now(timezone.utc)
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
                max_iterations=2,
                max_history=20,
            )
            setattr(session, "_tenant_id", tenant_id)
            if session_id not in _session_llm_state and db_history and hasattr(session, "_history"):
                max_history = getattr(session, "_max_history", 20)
                session._history = db_history[-(max_history * 2):]
            _session_llm_state[session_id] = session
        else:
            _session_llm_state[session_id] = {"history": list(db_history), "tenant_id": tenant_id}
    elif hasattr(existing_session, "_retriever") and session_retriever is not None:
        existing_session._retriever = session_retriever
        setattr(existing_session, "_tenant_id", tenant_id)
    elif isinstance(existing_session, dict):
        existing_session["tenant_id"] = tenant_id

    import time as _time
    _session_last_access[session_id] = _time.monotonic()
    return session_id, _session_llm_state[session_id]


# ---------------------------------------------------------------------------
# Startup logic
# ---------------------------------------------------------------------------

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

                _vector_store = _Chroma(
                    persist_directory=str(chroma_dir),
                    embedding_function=embeddings,
                    collection_name=collection_name,
                )

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


async def _probe_chromadb(chroma_dir: Path) -> ComponentStatus:
    t0 = time.monotonic()
    try:
        import chromadb  # type: ignore
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
                from sqlite_trace import purge_old_traces

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


@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> AskResponse:
    """Ask a question to the RAG assistant."""
    t0 = time.monotonic()
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    tenant = get_current_tenant() or _user.get("tenant", "default")
    session_params = inspect.signature(_get_or_create_session).parameters
    if "tenant_id" in session_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in session_params.values()
    ):
        session_result = _get_or_create_session(body.session_id, tenant)
    else:
        session_result = _get_or_create_session(body.session_id)
    if asyncio.iscoroutine(session_result):
        session_id, session = await session_result
    else:
        session_id, session = session_result

    settings = get_settings()
    cache_enabled = bool(getattr(settings, "llm_cache_enabled", False))
    llm_cache_key = _cache_key(tenant, question)
    cache_hit = False

    if hasattr(session, "ask"):
        if cache_enabled:
            cached_payload = cache_json_get(llm_cache_key)
            if isinstance(cached_payload, dict) and cached_payload.get("answer"):
                try:
                    prometheus_metrics.LLM_CACHE_HITS.labels(tenant=tenant).inc()
                except Exception:
                    pass

                answer = str(cached_payload.get("answer") or "")
                cached_sources = []
                for item in cached_payload.get("sources", [])[:5]:
                    if not isinstance(item, dict):
                        continue
                    cached_sources.append(
                        SourceInfo(
                            source=item.get("source", ""),
                            page_content=item.get("page_content", ""),
                        )
                    )
                cached_citations = []
                for item in cached_payload.get("citations", []):
                    if not isinstance(item, dict):
                        continue
                    cached_citations.append(
                        Citation(
                            index=int(item.get("index") or 0),
                            doc_id=str(item.get("doc_id") or ""),
                            title=str(item.get("title") or ""),
                            excerpt=str(item.get("excerpt") or ""),
                        )
                    )
                if not cached_citations:
                    for idx, source in enumerate(cached_sources, start=1):
                        cached_citations.append(
                            Citation(
                                index=idx,
                                doc_id=source.source or f"doc_{idx}",
                                title=source.source or f"doc_{idx}",
                                excerpt=(source.page_content or "")[:300],
                            )
                        )

                if hasattr(session, "_history"):
                    session._history.append({"role": "user", "content": question})
                    session._history.append({"role": "assistant", "content": answer})
                    max_history = getattr(session, "_max_history", 20)
                    if len(session._history) > max_history * 2:
                        session._history = session._history[-(max_history * 2):]
                elif isinstance(session, dict):
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": answer})

                response = AskResponse(
                    answer=answer,
                    quality_score=int(cached_payload.get("quality_score") or 50),
                    route=str(cached_payload.get("route") or "auto"),
                    sources=cached_sources,
                    citations=cached_citations,
                    session_id=session_id,
                    trace_id="",
                    suggested_questions=cached_payload.get("suggested_questions") or [],
                )
                cache_hit = True
            else:
                try:
                    prometheus_metrics.LLM_CACHE_MISSES.labels(tenant=tenant).inc()
                except Exception:
                    pass

        if not cache_hit:
            timeout = float(getattr(settings, "request_timeout_sec", 30.0))
            acquire_timeout = float(
                getattr(settings, "pipeline_acquire_timeout_sec", 0.5)
            )
            request_id = get_request_id()
            ask_params = inspect.signature(session.ask).parameters
            has_var_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in ask_params.values()
            )
            ask_kwargs: dict[str, Any] = {}
            if "trace_id" in ask_params or has_var_kwargs:
                ask_kwargs["trace_id"] = request_id
            if "tenant_id" in ask_params or has_var_kwargs:
                ask_kwargs["tenant_id"] = tenant
            if "confirm" in ask_params or has_var_kwargs:
                ask_kwargs["confirm"] = body.confirm
            if "user_id" in ask_params or has_var_kwargs:
                ask_kwargs["user_id"] = _user.get("sub", "anonymous")
            if "session_id" in ask_params or has_var_kwargs:
                ask_kwargs["session_id"] = session_id
            semaphore = _get_pipeline_semaphore()
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)
            except asyncio.TimeoutError:
                try:
                    prometheus_metrics.record_pipeline_rejection("busy")
                except Exception:
                    pass
                logger.warning(
                    "req_id=%s /api/ask rejected: pipeline pool saturated",
                    request_id or "-",
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server is busy processing other requests - retry in a moment",
                )
            try:
                prometheus_metrics.INFLIGHT_PIPELINES.inc()
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(session.ask, question, **ask_kwargs),
                        timeout=timeout,
                    )

                    answer = result.get("answer") or ""
                    quality = result.get("quality_score") or 50
                    route = result.get("route") or "auto"

                    sources_list = []
                    citations_list = []
                    docs = result.get("graded_docs") or result.get("context_docs") or []
                    for idx, doc in enumerate(docs, start=1):
                        if isinstance(doc, dict):
                            metadata = doc.get("metadata", {}) or {}
                            src = metadata.get("source") or metadata.get("file_name") or ""
                            content = doc.get("page_content", "")
                        else:
                            metadata = getattr(doc, "metadata", {}) or {}
                            src = metadata.get("source") or metadata.get("file_name") or ""
                            content = getattr(doc, "page_content", "")
                        sources_list.append(SourceInfo(source=src, page_content=content))
                        citations_list.append(
                            Citation(
                                index=idx,
                                doc_id=str(
                                    metadata.get("doc_id")
                                    or metadata.get("id")
                                    or src
                                    or f"doc_{idx}"
                                ),
                                title=str(
                                    metadata.get("title")
                                    or src
                                    or metadata.get("file_name")
                                    or f"doc_{idx}"
                                ),
                                excerpt=str(content or "")[:300],
                            )
                        )
                    if result.get("citations"):
                        citations_list = [
                            Citation(
                                index=int(item.get("index") or 0),
                                doc_id=str(item.get("doc_id") or ""),
                                title=str(item.get("title") or ""),
                                excerpt=str(item.get("excerpt") or ""),
                            )
                            for item in result.get("citations", [])
                            if isinstance(item, dict)
                        ]

                    response = AskResponse(
                        answer=answer,
                        quality_score=quality,
                        route=route,
                        sources=sources_list,
                        citations=citations_list,
                        session_id=session_id,
                        trace_id=result.get("trace_id") or "",
                        suggested_questions=result.get("suggested_questions") or [],
                        requires_confirmation=bool(result.get("requires_confirmation")),
                        action_summary=str(result.get("action_summary") or ""),
                    )
                    if (
                        cache_enabled
                        and response.answer
                        and response.route == "auto"
                        and not response.requires_confirmation
                        and not result.get("tool_calls")
                    ):
                        cache_json_set(
                            llm_cache_key,
                            {
                                "answer": response.answer,
                                "quality_score": response.quality_score,
                                "route": response.route,
                                "sources": [source.model_dump() for source in response.sources],
                                "suggested_questions": response.suggested_questions,
                            },
                            ttl_seconds=int(getattr(settings, "llm_cache_ttl_seconds", 3600)),
                        )
                except asyncio.TimeoutError:
                    try:
                        prometheus_metrics.record_request_timeout("/api/ask")
                    except Exception:
                        pass
                    logger.warning(
                        "req_id=%s /api/ask exceeded timeout=%.1fs",
                        request_id or "-",
                        timeout,
                    )
                    raise HTTPException(
                        status_code=504,
                        detail=f"Request exceeded {timeout:.0f}s wall-time limit",
                    )
                except Exception as exc:
                    logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
                    answer = "Не удалось обработать запрос автоматически. Ваш вопрос передан оператору."
                    if hasattr(session, "_history"):
                        session._history.append({"role": "user", "content": question})
                        session._history.append({"role": "assistant", "content": answer})
                    elif isinstance(session, dict):
                        session["history"].append({"role": "user", "content": question})
                        session["history"].append({"role": "assistant", "content": answer})
                    response = AskResponse(
                        answer=answer,
                        quality_score=0,
                        route="human",
                        sources=[],
                        citations=[],
                        session_id=session_id,
                        trace_id="",
                        suggested_questions=[],
                    )
            finally:
                try:
                    prometheus_metrics.INFLIGHT_PIPELINES.dec()
                except Exception:
                    pass
                semaphore.release()
    else:
        session["history"].append({"role": "user", "content": question})
        fallback_answer = f"[DEMO] Pipeline not available. Question received: {question}"
        session["history"].append({"role": "assistant", "content": fallback_answer})
        response = AskResponse(
            answer=fallback_answer,
            quality_score=0,
            route="human",
            sources=[],
            citations=[],
            session_id=session_id,
            trace_id="",
            suggested_questions=[],
        )

    global _db_retry_after
    if time.monotonic() >= _db_retry_after:
        try:
            from db.engine import async_session as db_session_factory
            from db.models import Message

            async with db_session_factory() as db:
                session_uuid = uuid.UUID(session_id)
                db.add(Message(session_id=session_uuid, role="user", content=question))
                db.add(Message(session_id=session_uuid, role="assistant", content=response.answer))
                await asyncio.wait_for(db.commit(), timeout=0.5)
                _db_retry_after = 0.0
        except Exception as exc:
            _db_retry_after = time.monotonic() + 60.0
            logger.warning("Failed to persist messages: %s", exc)

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="ask",
        resource=f"session:{session_id}",
        detail={
            "question_length": len(body.question),
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )
    duration = time.monotonic() - t0
    prometheus_metrics.REQUEST_DURATION.observe(duration)
    prometheus_metrics.REQUEST_COUNT.labels(route=response.route).inc()
    if response.quality_score:
        prometheus_metrics.QUALITY_SCORE.observe(response.quality_score)
    if response.route == "human":
        prometheus_metrics.ESCALATION_TOTAL.inc()
    prometheus_metrics.ACTIVE_SESSIONS.set(len(_sessions))
    if response.citations:
        asyncio.create_task(_record_citation_stats(tenant, list(response.citations)))
    if cache_hit:
        return JSONResponse(content={**response.model_dump(), "cached": True})
    return response


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
):
    return await ask(request, body, _user)


@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """SSE endpoint с реальным стримингом токенов из Ollama."""
    async def event_generator() -> AsyncGenerator[str, None]:
        global _db_retry_after
        yield "data: " + _json.dumps({"type": "status", "node": "processing"}) + "\n\n"

        tenant = get_current_tenant() or _user.get("tenant", "default")
        session_params = inspect.signature(_get_or_create_session).parameters
        if "tenant_id" in session_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in session_params.values()
        ):
            session_result = _get_or_create_session(body.session_id, tenant)
        else:
            session_result = _get_or_create_session(body.session_id)
        if asyncio.iscoroutine(session_result):
            session_id, session = await session_result
        else:
            session_id, session = session_result
        question = (body.question or "").strip()

        if not question:
            yield "data: " + _json.dumps({
                "type": "error",
                "detail": "question is required",
            }) + "\n\n"
            return

        await log_audit(
            actor=_user.get("sub", "anonymous"),
            action="ask",
            resource=f"session:{session_id}",
            detail={
                "question_length": len(body.question),
                "tenant": _user.get("tenant", "default"),
            },
            ip_address=request.client.host if request.client else None,
        )

        try:
            prompt = ""
            docs: List[Any] = []
            chat_history: List[Dict[str, str]] = []
            ask_params = inspect.signature(session.ask).parameters if hasattr(session, "ask") else {}
            ask_args = (
                (question, get_request_id(), tenant)
                if len(ask_params) >= 3
                or any(
                    param.kind == inspect.Parameter.VAR_POSITIONAL
                    for param in ask_params.values()
                )
                else (question, get_request_id())
            )

            if hasattr(session, "_retriever") and session._retriever is not None:
                docs = await asyncio.get_running_loop().run_in_executor(
                    None,
                    session._retriever.get_relevant_documents,
                    question,
                )

                if hasattr(session, "history"):
                    chat_history = session.history
                elif isinstance(session, dict):
                    chat_history = session.get("history", [])

                from agent.prompts import build_qa_prompt, build_conversational_qa_prompt  # noqa: PLC0415

                plain_docs = []
                for doc in docs[:5]:
                    if hasattr(doc, "page_content"):
                        plain_docs.append({
                            "page_content": getattr(doc, "page_content", ""),
                            "metadata": getattr(doc, "metadata", {}) or {},
                        })
                    elif isinstance(doc, dict):
                        plain_docs.append(doc)

                if chat_history:
                    prompt = build_conversational_qa_prompt(
                        question=question,
                        context_docs=plain_docs,
                        chat_history=chat_history,
                    )
                else:
                    prompt = build_qa_prompt(question=question, context_docs=plain_docs)

            if not prompt:
                raise RuntimeError("streaming prompt unavailable")

            settings = get_settings()
            full_answer = ""
            streaming_llm = getattr(session, "_llm", None)
            if not (
                streaming_llm is not None
                and callable(getattr(streaming_llm, "generate_stream", None))
            ) and _build_provider_runtime is not None:
                try:
                    runtime = _build_provider_runtime(settings)
                except Exception as runtime_exc:
                    logger.warning("Streaming runtime unavailable: %s", runtime_exc)
                else:
                    for candidate in (runtime.strong, runtime.fast):
                        if callable(getattr(candidate, "generate_stream", None)):
                            streaming_llm = candidate
                            break

            yield "data: " + _json.dumps({"type": "token_start"}) + "\n\n"
            try:
                if streaming_llm is not None and callable(getattr(streaming_llm, "generate_stream", None)):
                    async for token in streaming_llm.generate_stream(
                        [{"role": "user", "content": prompt}],
                    ):
                        full_answer += token
                        yield "data: " + _json.dumps({
                            "type": "token",
                            "token": token,
                        }) + "\n\n"
                else:
                    async for token in _stream_ollama(
                        prompt,
                        settings.ollama_model_name,
                        settings.ollama_base_url,
                    ):
                        full_answer += token
                        yield "data: " + _json.dumps({
                            "type": "token",
                            "token": token,
                        }) + "\n\n"
            except Exception as exc:
                logger.warning("Streaming error in /ask/stream: %s", exc)
                if not full_answer:
                    raise

            if not full_answer:
                raise RuntimeError("empty streaming answer")

            if hasattr(session, "_history"):
                session._history.append({"role": "user", "content": question})
                session._history.append({"role": "assistant", "content": full_answer})
                max_history = getattr(session, "_max_history", 20)
                if len(session._history) > max_history * 2:
                    session._history = session._history[-(max_history * 2):]
            elif isinstance(session, dict):
                session["history"].append({"role": "user", "content": question})
                session["history"].append({"role": "assistant", "content": full_answer})

            sources = []
            citations = []
            for idx, doc in enumerate(docs, start=1):
                if hasattr(doc, "page_content"):
                    metadata = getattr(doc, "metadata", {}) or {}
                    sources.append({
                        "source": metadata.get("source") or metadata.get("file_name") or "",
                        "page_content": getattr(doc, "page_content", ""),
                    })
                elif isinstance(doc, dict):
                    metadata = doc.get("metadata", {}) or {}
                    sources.append({
                        "source": metadata.get("source") or metadata.get("file_name") or "",
                        "page_content": doc.get("page_content", ""),
                    })
                else:
                    metadata = {}
                citations.append({
                    "index": idx,
                    "doc_id": str(
                        metadata.get("doc_id")
                        or metadata.get("id")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or f"doc_{idx}"
                    ),
                    "title": str(
                        metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or metadata.get("doc_id")
                        or f"doc_{idx}"
                    ),
                    "excerpt": str(sources[-1]["page_content"] if sources else "")[:300],
                })

            quality = 70 if len(full_answer.strip()) > 20 or sources else 40
            route = "auto" if quality >= 70 else "human"
            suggested_questions: List[str] = []
            if route == "auto":
                try:
                    from agent.prompts import build_suggested_questions_prompt  # noqa: PLC0415

                    question_llm = getattr(session, "_llm", None)
                    if question_llm is None:
                        from agent.graph import LocalOllamaLLM  # noqa: PLC0415
                        question_llm = LocalOllamaLLM(model_name=settings.ollama_model_name)

                    context_snippet = "\n\n".join(
                        source.get("page_content", "")
                        for source in sources[:2]
                        if source.get("page_content")
                    )[:500]
                    prompt = build_suggested_questions_prompt(
                        question=question,
                        answer=full_answer,
                        context_snippet=context_snippet,
                    )
                    raw_questions = await asyncio.get_running_loop().run_in_executor(
                        None,
                        question_llm.invoke,
                        prompt,
                    )
                    suggested_questions = [
                        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
                        for line in raw_questions.strip().splitlines()
                        if line.strip()
                    ][:3]
                except Exception as suggest_exc:
                    logger.warning(
                        "Failed to generate streaming suggested questions: %s",
                        suggest_exc,
                    )
            if time.monotonic() >= _db_retry_after:
                try:
                    from db.engine import async_session as db_session_factory
                    from db.models import Message

                    async with db_session_factory() as db:
                        session_uuid = uuid.UUID(session_id)
                        db.add(Message(session_id=session_uuid, role="user", content=question))
                        db.add(Message(session_id=session_uuid, role="assistant", content=full_answer))
                        await asyncio.wait_for(db.commit(), timeout=0.5)
                        _db_retry_after = 0.0
                except Exception as db_exc:
                    _db_retry_after = time.monotonic() + 60.0
                    logger.warning("Failed to persist streaming messages: %s", db_exc)
            yield "data: " + _json.dumps({
                "type": "result",
                "answer": full_answer,
                "quality_score": quality,
                "route": route,
                "session_id": session_id,
                "sources": sources,
                "citations": citations,
                "trace_id": "",
                "suggested_questions": suggested_questions,
            }) + "\n\n"
        except Exception as exc:
            logger.warning("SSE streaming path failed, fallback to sync pipeline: %s", exc, exc_info=True)
            try:
                if hasattr(session, "ask"):
                    result = await asyncio.get_running_loop().run_in_executor(
                        None, session.ask, *ask_args
                    )
                    answer = result.get("answer") or "Не удалось получить ответ."
                    quality = result.get("quality_score") or 50
                    route = result.get("route") or "auto"
                    raw_sources = result.get("graded_docs") or result.get("context_docs") or []
                    sources = []
                    citations = []
                    for idx, item in enumerate(raw_sources, start=1):
                        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
                        content = item.get("page_content", "") if isinstance(item, dict) else ""
                        sources.append({
                            "source": metadata.get("source") or metadata.get("file_name") or "",
                            "page_content": content,
                        })
                        citations.append({
                            "index": idx,
                            "doc_id": str(
                                metadata.get("doc_id")
                                or metadata.get("id")
                                or metadata.get("source")
                                or metadata.get("file_name")
                                or f"doc_{idx}"
                            ),
                            "title": str(
                                metadata.get("title")
                                or metadata.get("source")
                                or metadata.get("file_name")
                                or metadata.get("doc_id")
                                or f"doc_{idx}"
                            ),
                            "excerpt": str(content or "")[:300],
                        })
                    if result.get("citations"):
                        citations = [
                            {
                                "index": int(item.get("index") or 0),
                                "doc_id": str(item.get("doc_id") or ""),
                                "title": str(item.get("title") or ""),
                                "excerpt": str(item.get("excerpt") or ""),
                            }
                            for item in result.get("citations", [])
                            if isinstance(item, dict)
                        ]
                    trace_id = result.get("trace_id") or ""
                    suggested_questions = result.get("suggested_questions") or []
                else:
                    answer = "Сессия не инициализирована."
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": answer})
                    quality, route, sources, citations, trace_id, suggested_questions = 0, "human", [], [], "", []

                if time.monotonic() >= _db_retry_after:
                    try:
                        from db.engine import async_session as db_session_factory
                        from db.models import Message

                        async with db_session_factory() as db:
                            session_uuid = uuid.UUID(session_id)
                            db.add(Message(session_id=session_uuid, role="user", content=question))
                            db.add(Message(session_id=session_uuid, role="assistant", content=answer))
                            await asyncio.wait_for(db.commit(), timeout=0.5)
                            _db_retry_after = 0.0
                    except Exception as db_exc:
                        _db_retry_after = time.monotonic() + 60.0
                        logger.warning("Failed to persist streamed fallback messages: %s", db_exc)

                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": answer,
                    "quality_score": quality,
                    "route": route,
                    "session_id": session_id,
                    "sources": sources,
                    "citations": citations,
                    "trace_id": trace_id,
                    "suggested_questions": suggested_questions,
                }) + "\n\n"
            except Exception as sync_exc:
                logger.error("SSE fallback error: %s", sync_exc, exc_info=True)
                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": "Ошибка обработки запроса.",
                    "quality_score": 0,
                    "route": "human",
                    "session_id": session_id,
                    "sources": [],
                    "citations": [],
                    "trace_id": "",
                    "suggested_questions": [],
                }) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stream")
@limiter.limit("60/minute")
async def chat_stream(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> StreamingResponse:
    return await ask_stream(request, body, _user)


@router.post("/feedback", status_code=204)
async def post_feedback(
    request: Request,
    body: FeedbackRequest,
    _user: dict = Depends(get_current_user),
) -> None:
    """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ñ„Ð¸Ð´Ð±ÐµÐº Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð½Ð° Ð¾Ñ‚Ð²ÐµÑ‚."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating must be 'up' or 'down'")
    prometheus_metrics.FEEDBACK_COUNT.labels(rating=body.rating).inc()
    try:
        from sqlite_trace import save_feedback  # noqa: PLC0415

        save_feedback(
            trace_id=body.trace_id,
            session_id=body.session_id,
            rating=body.rating,
            reason=body.reason or "",
        )
    except Exception as exc:
        logger.warning("Failed to save feedback: %s", exc)

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="feedback",
        resource=f"trace:{body.trace_id}",
        detail={
            "rating": body.rating,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )


@router.post("/escalate")
async def escalate_to_human(
    request: Request,
    body: EscalateRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Ручная эскалация: пользователь хочет оператора."""
    from datetime import datetime, timezone

    record = {
        "entity_id": body.session_id,
        "question": body.question,
        "route": "human_request",
        "reason": body.reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        inbox_path = PROJECT_ROOT / "data" / "inbox" / "support_inbox.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write escalation: %s", exc)
        raise HTTPException(status_code=500, detail="Escalation failed")

    try:
        from db.engine import async_session  # noqa: PLC0415
        from db.models import EscalatedTicket  # noqa: PLC0415

        draft = None
        question_text = (body.question or "").strip()
        if question_text:
            draft = (
                f"Запрос пользователя: {question_text}\n\n"
                "Черновик ответа: Спасибо за обращение. Мы получили ваш запрос и передали его оператору. "
                "Проверим детали и вернёмся с решением."
            )

        async with async_session() as db:
            db.add(
                EscalatedTicket(
                    tenant_id=_user.get("tenant", "default"),
                    session_id=body.session_id,
                    user_question=question_text or "(пользователь запросил оператора)",
                    ai_draft=draft,
                    status="open",
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist escalated ticket: %s", exc)

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="escalate",
        resource=f"session:{body.session_id}",
        detail={
            "reason": body.reason,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )

    return {
        "status": "ok",
        "message": "Ваш запрос передан оператору. Мы ответим в ближайшее время.",
    }


@router.get("/agent/tickets")
async def agent_list_tickets(
    status: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import EscalatedTicket  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        stmt = (
            select(EscalatedTicket)
            .where(EscalatedTicket.tenant_id == tenant)
            .order_by(EscalatedTicket.created_at.desc())
        )
        if status:
            stmt = stmt.where(EscalatedTicket.status == status)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "tickets": [
                {
                    "id": str(row.id),
                    "tenant_id": row.tenant_id,
                    "session_id": row.session_id,
                    "user_question": row.user_question,
                    "ai_draft": row.ai_draft,
                    "operator_response": row.operator_response,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )


@router.get("/agent/tickets/{ticket_id}")
async def agent_get_ticket(
    ticket_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import EscalatedTicket, Message  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with async_session() as db:
        ticket = await db.get(EscalatedTicket, ticket_uuid)
        if ticket is None or ticket.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="ticket not found")

        messages: list[dict[str, str | None]] = []
        try:
            session_uuid = uuid.UUID(ticket.session_id)
            message_result = await db.execute(
                select(Message)
                .where(Message.session_id == session_uuid)
                .order_by(Message.created_at)
            )
            messages = [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
                for message in message_result.scalars().all()
            ]
        except Exception:
            messages = []

        similar_result = await db.execute(
            select(EscalatedTicket)
            .where(
                EscalatedTicket.tenant_id == tenant,
                EscalatedTicket.status == "resolved",
                EscalatedTicket.id != ticket_uuid,
            )
            .order_by(EscalatedTicket.resolved_at.desc(), EscalatedTicket.created_at.desc())
            .limit(3)
        )
        similar_rows = similar_result.scalars().all()

    return JSONResponse(
        content={
            "ticket": {
                "id": str(ticket.id),
                "tenant_id": ticket.tenant_id,
                "session_id": ticket.session_id,
                "user_question": ticket.user_question,
                "ai_draft": ticket.ai_draft,
                "operator_response": ticket.operator_response,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            },
            "messages": messages,
            "retrieved_docs": [],
            "quality_scores": {},
            "similar_tickets": [
                {
                    "id": str(row.id),
                    "user_question": row.user_question,
                    "operator_response": row.operator_response,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in similar_rows
            ],
        }
    )


@router.post("/agent/tickets/{ticket_id}/respond")
async def agent_respond_to_ticket(
    request: Request,
    ticket_id: str,
    body: AgentRespondRequest,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import EscalatedTicket  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with async_session() as db:
        ticket = await db.get(EscalatedTicket, ticket_uuid)
        if ticket is None or ticket.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="ticket not found")

        ticket.operator_response = body.response.strip()
        ticket.status = "resolved"
        ticket.resolved_at = datetime.now(timezone.utc)
        await db.commit()

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="agent_respond",
        resource=f"ticket:{ticket_id}",
        detail={"tenant": tenant},
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(
        content={
            "status": "ok",
            "ticket": {
                "id": str(ticket.id),
                "tenant_id": ticket.tenant_id,
                "session_id": ticket.session_id,
                "user_question": ticket.user_question,
                "ai_draft": ticket.ai_draft,
                "operator_response": ticket.operator_response,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            },
        }
    )


@router.get("/agent/similar")
async def agent_similar_tickets(
    ticket_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import EscalatedTicket  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        ticket_uuid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ticket_id")

    async with async_session() as db:
        result = await db.execute(
            select(EscalatedTicket)
            .where(
                EscalatedTicket.tenant_id == tenant,
                EscalatedTicket.status == "resolved",
                EscalatedTicket.id != ticket_uuid,
            )
            .order_by(EscalatedTicket.resolved_at.desc(), EscalatedTicket.created_at.desc())
            .limit(3)
        )
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "tickets": [
                {
                    "id": str(row.id),
                    "user_question": row.user_question,
                    "operator_response": row.operator_response,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )


@router.get("/feedback/stats")
async def feedback_stats(
    days: int = 30,
    _user: dict = Depends(require_role("agent", "admin")),
) -> dict:
    """Feedback stats for the last N days."""
    try:
        from sqlite_trace import get_feedback_stats  # noqa: PLC0415

        return get_feedback_stats(days=days)
    except Exception as exc:
        logger.warning("Failed to get feedback stats: %s", exc)
        return {
            "total": 0,
            "up": 0,
            "down": 0,
            "up_pct": 0.0,
            "by_route": {},
            "period_days": days,
        }


@router.get("/metrics")
async def get_metrics(
    _user: dict = Depends(require_role("admin")),
) -> dict:
    """Агрегированный JSON-снапшот метрик здоровья системы."""
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    try:
        from sqlite_trace import get_metrics_snapshot  # noqa: PLC0415

        metrics_params = inspect.signature(get_metrics_snapshot).parameters
        if "tenant_id" in metrics_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in metrics_params.values()
        ):
            return get_metrics_snapshot(tenant_id=tenant)
        return get_metrics_snapshot()
    except Exception as exc:
        logger.warning("Failed to get metrics: %s", exc)
        return {"error": str(exc), "generated_at": ""}


@router.post("/admin/circuit-breaker/reset")
async def admin_reset_circuit_breaker(
    request: Request,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from agent.graph import get_default_breaker

    breaker = get_default_breaker()
    if breaker is None:
        return JSONResponse(
            status_code=409,
            content={
                "status": "disabled",
                "detail": "circuit breaker disabled via CIRCUIT_BREAKER_ENABLED=false",
            },
        )

    previous = breaker.snapshot()
    breaker.reset()
    current = breaker.snapshot()

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="circuit_breaker_reset",
        resource=f"breaker/{breaker.name}",
        detail={
            "tenant": _user.get("tenant", "default"),
            "previous_state": previous["state"],
            "previous_consecutive_failures": previous["consecutive_failures"],
        },
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "reset",
            "breaker": breaker.name,
            "previous": previous,
            "current": current,
        },
    )


@router.get("/admin/audit")
async def admin_list_audit(
    limit: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    limit = getattr(get_settings(), "api_default_page_size", 50) if limit is None else limit
    limit = max(1, min(500, limit))
    tenant = _user.get("tenant") or get_current_tenant() or "default"

    try:
        from sqlalchemy import select  # noqa: PLC0415

        from db.engine import async_session  # noqa: PLC0415
        from db.models import AuditLog  # noqa: PLC0415

        async with async_session() as db:
            stmt = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant)
                .order_by(AuditLog.ts.desc())
                .limit(limit)
            )
            if actor:
                stmt = stmt.where(AuditLog.actor == actor)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            result = await db.execute(stmt)
            rows = result.scalars().all()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"audit_log unavailable: {exc}"},
        )

    return JSONResponse(
        content={
            "entries": [
                {
                    "id": row.id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "actor": row.actor,
                    "action": row.action,
                    "resource": row.resource,
                    "detail": row.detail,
                    "ip_address": row.ip_address,
                }
                for row in rows
            ]
        }
    )


@router.get("/admin/review-queue")
async def admin_list_review_queue(
    status: str = "pending",
    reason: str = "*",
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    if not _review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    normalized_status = None if status in ("", "*") else status
    normalized_reason = None if reason in ("", "*") else reason
    if normalized_status is not None and normalized_status not in _REVIEW_QUEUE_STATUSES:
        raise HTTPException(status_code=422, detail="invalid review queue status")
    if normalized_reason is not None and normalized_reason not in _REVIEW_QUEUE_REASONS:
        raise HTTPException(status_code=422, detail="invalid review queue reason")

    safe_limit = max(1, min(500, limit))
    safe_offset = max(0, offset)
    tenant = _user.get("tenant") or get_current_tenant() or "default"

    query = """
        SELECT id, trace_id, tenant_id, reason, status, reviewer_notes, created_at, reviewed_at, reviewed_by
        FROM review_queue
        WHERE tenant_id = :tenant_id
    """
    params: dict[str, Any] = {
        "tenant_id": tenant,
        "limit": safe_limit,
        "offset": safe_offset,
    }
    if normalized_status is not None:
        query += " AND status = :status"
        params["status"] = normalized_status
    if normalized_reason is not None:
        query += " AND reason = :reason"
        params["reason"] = normalized_reason
    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

    async with async_session() as db:
        rows = (await db.execute(text(query), params)).mappings().all()

    trace_details = _load_review_queue_trace_details([str(row["trace_id"]) for row in rows])
    await _refresh_review_queue_metrics(tenant)
    return JSONResponse(
        content={
            "items": [
                {
                    "id": row["id"],
                    "trace_id": row["trace_id"],
                    "tenant_id": row["tenant_id"],
                    "reason": row["reason"],
                    "status": row["status"],
                    "reviewer_notes": row["reviewer_notes"] or "",
                    "created_at": _serialize_timestamp(row["created_at"]),
                    "reviewed_at": _serialize_timestamp(row["reviewed_at"]),
                    "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] is not None else None,
                    "quality": trace_details.get(str(row["trace_id"]), {}).get("quality"),
                    "fact_score": trace_details.get(str(row["trace_id"]), {}).get("fact_score"),
                    "duration_ms": trace_details.get(str(row["trace_id"]), {}).get("duration_ms"),
                    "trace_url": trace_details.get(str(row["trace_id"]), {}).get(
                        "trace_url",
                        f"/admin/traces/{row['trace_id']}",
                    ),
                }
                for row in rows
            ],
            "count": len(rows),
            "limit": safe_limit,
            "offset": safe_offset,
        }
    )


@router.post("/admin/review-queue/{review_id}")
async def admin_update_review_queue(
    review_id: int,
    body: ReviewQueueUpdateRequest,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    if not _review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    reviewer_id = _reviewed_by_uuid(body.reviewed_by or _user.get("sub"))
    reviewed_at = datetime.now(timezone.utc) if body.status != "pending" else None

    async with async_session() as db:
        result = await db.execute(
            text(
                """
                UPDATE review_queue
                SET status = :status,
                    reviewer_notes = :reviewer_notes,
                    reviewed_by = :reviewed_by,
                    reviewed_at = :reviewed_at
                WHERE id = :review_id AND tenant_id = :tenant_id
                """
            ),
            {
                "status": body.status,
                "reviewer_notes": body.reviewer_notes.strip(),
                "reviewed_by": reviewer_id,
                "reviewed_at": reviewed_at,
                "review_id": review_id,
                "tenant_id": tenant,
            },
        )
        await db.commit()

    if int(getattr(result, "rowcount", 0) or 0) == 0:
        raise HTTPException(status_code=404, detail="review item not found")

    await _refresh_review_queue_metrics(tenant)
    return JSONResponse(content={"status": "ok"})


@router.get("/admin/review-queue/stats")
async def admin_review_queue_stats(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    if not _review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    status_counts = {item: 0 for item in _REVIEW_QUEUE_STATUSES}
    reason_counts = {item: 0 for item in _REVIEW_QUEUE_REASONS}
    oldest_pending_seconds = 0.0

    async with async_session() as db:
        status_rows = (
            await db.execute(
                text(
                    """
                    SELECT status, COUNT(*) AS total
                    FROM review_queue
                    WHERE tenant_id = :tenant_id
                    GROUP BY status
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        for row in status_rows:
            key = str(row["status"])
            if key in status_counts:
                status_counts[key] = int(row["total"] or 0)

        reason_rows = (
            await db.execute(
                text(
                    """
                    SELECT reason, COUNT(*) AS total
                    FROM review_queue
                    WHERE tenant_id = :tenant_id
                    GROUP BY reason
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        for row in reason_rows:
            key = str(row["reason"])
            if key in reason_counts:
                reason_counts[key] = int(row["total"] or 0)

        oldest_rows = (
            await db.execute(
                text(
                    """
                    SELECT MIN(created_at) AS oldest_pending
                    FROM review_queue
                    WHERE tenant_id = :tenant_id AND status = 'pending'
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        oldest_pending = oldest_rows[0]["oldest_pending"] if oldest_rows else None
        if oldest_pending is not None:
            if isinstance(oldest_pending, str):
                oldest_pending = datetime.fromisoformat(oldest_pending)
            if oldest_pending.tzinfo is None:
                oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
            oldest_pending_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - oldest_pending).total_seconds(),
            )

    await _refresh_review_queue_metrics(tenant)
    return JSONResponse(
        content={
            "status_counts": status_counts,
            "reason_counts": reason_counts,
            "oldest_pending_seconds": oldest_pending_seconds,
        }
    )


@router.get("/admin/curated-dataset/stats")
async def admin_curated_dataset_stats(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    _ = _user
    return JSONResponse(content=_curated_dataset_summary())


@router.post("/admin/curated-dataset/rebuild")
async def admin_rebuild_curated_dataset(
    tenant: str = "all",
    since: str | None = None,
    include_bad: bool = False,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    _ = _user
    job_id = str(uuid.uuid4())
    dataset_path = _curated_dataset_path()
    _store_curated_dataset_job(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "tenant": tenant,
            "since": since,
            "include_bad": include_bad,
            "progress": 0,
            "out": str(dataset_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    asyncio.create_task(
        _run_curated_dataset_rebuild(
            job_id=job_id,
            tenant=tenant,
            since=since,
            include_bad=include_bad,
        )
    )
    return JSONResponse(content={"job_id": job_id, "status": "queued"})


@router.get("/admin/thresholds/analysis")
async def admin_threshold_analysis(
    days: int = 30,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    safe_days = max(1, min(365, days))
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    cache_key = f"threshold-analysis:{tenant}:{safe_days}"
    cached_payload = cache_json_get(cache_key)
    if cached_payload is not None:
        payload = dict(cached_payload)
        payload["cached"] = True
        return JSONResponse(content=payload)

    from scripts import analyze_thresholds  # noqa: PLC0415

    settings = get_settings()
    report_path = Path(getattr(settings, "project_root", PROJECT_ROOT)) / "reports" / "threshold_recommendations.md"
    payload = await analyze_thresholds.run_once(
        days=safe_days,
        tenant=tenant,
        out=report_path,
        settings=settings,
    )
    cache_json_set(cache_key, payload, ttl_seconds=86400)
    payload = dict(payload)
    payload["cached"] = False
    return JSONResponse(content=payload)


@router.post("/admin/thresholds/refresh")
async def admin_refresh_threshold_analysis(
    days: int = 30,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from scripts import analyze_thresholds  # noqa: PLC0415

    safe_days = max(1, min(365, days))
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    settings = get_settings()
    report_path = Path(getattr(settings, "project_root", PROJECT_ROOT)) / "reports" / "threshold_recommendations.md"
    payload = await analyze_thresholds.run_once(
        days=safe_days,
        tenant=tenant,
        out=report_path,
        settings=settings,
    )
    cache_json_set(f"threshold-analysis:{tenant}:{safe_days}", payload, ttl_seconds=86400)
    payload = dict(payload)
    payload["cached"] = False
    return JSONResponse(content=payload)


@router.get("/admin/improvement-backlog/current")
async def admin_current_improvement_backlog(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from scripts import generate_improvement_backlog  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    settings = get_settings()
    project_root = Path(getattr(settings, "project_root", PROJECT_ROOT))
    week = generate_improvement_backlog.latest_persisted_week(project_root)
    if week is None:
        week = generate_improvement_backlog.default_week_spec(datetime.now(timezone.utc))

    payload = await generate_improvement_backlog.run_once(
        tenant=tenant,
        week=week,
        out=None,
        settings=settings,
    )
    return JSONResponse(content=payload)


@router.get("/admin/improvement-backlog/archive")
async def admin_improvement_backlog_archive(
    year: int | None = None,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from scripts import generate_improvement_backlog  # noqa: PLC0415

    _ = _user
    settings = get_settings()
    project_root = Path(getattr(settings, "project_root", PROJECT_ROOT))
    return JSONResponse(
        content={
            "weeks": generate_improvement_backlog.list_archive_weeks(project_root, year),
        }
    )


@router.get("/admin/traces")
async def admin_list_traces(
    limit: int | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlite_trace import list_recent_traces  # noqa: PLC0415

    limit = getattr(get_settings(), "api_default_page_size", 50) if limit is None else limit
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    trace_params = inspect.signature(list_recent_traces).parameters
    if "tenant_id" in trace_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in trace_params.values()
    ):
        traces = await asyncio.to_thread(list_recent_traces, limit, tenant_id=tenant)
    else:
        traces = await asyncio.to_thread(list_recent_traces, limit)
    return JSONResponse(content={"traces": traces})


@router.get("/admin/evaluations/trends")
async def admin_evaluation_trends(
    evaluator: str,
    days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _ = _user
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in [1, 365]")
    if not getattr(get_settings(), "online_evaluators_enabled", True):
        return JSONResponse(content={"evaluator": evaluator, "days": days, "points": []})

    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    async with async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        DATE(evaluated_at) AS bucket,
                        AVG(score) AS mean_score,
                        COUNT(*) AS runs
                    FROM trace_evaluations
                    WHERE evaluator_name = :evaluator_name
                      AND evaluated_at >= :window_start
                    GROUP BY DATE(evaluated_at)
                    ORDER BY bucket ASC
                    """
                ),
                {
                    "evaluator_name": evaluator,
                    "window_start": datetime.now(timezone.utc) - timedelta(days=days),
                },
            )
        ).mappings().all()

    return JSONResponse(
        content={
            "evaluator": evaluator,
            "days": days,
            "points": [
                {
                    "date": str(row.get("bucket") or ""),
                    "mean_score": float(row.get("mean_score") or 0.0),
                    "runs": int(row.get("runs") or 0),
                }
                for row in rows
            ],
        }
    )


@router.get("/admin/evaluations/worst")
async def admin_evaluation_worst(
    evaluator: str,
    limit: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _ = _user
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be in [1, 100]")
    if not getattr(get_settings(), "online_evaluators_enabled", True):
        return JSONResponse(content={"evaluator": evaluator, "limit": limit, "items": []})

    from sqlalchemy import text  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415

    async with async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        trace_id,
                        score,
                        verdict,
                        metadata,
                        evaluated_at
                    FROM trace_evaluations
                    WHERE evaluator_name = :evaluator_name
                    ORDER BY score ASC, evaluated_at ASC
                    LIMIT :limit
                    """
                ),
                {
                    "evaluator_name": evaluator,
                    "limit": limit,
                },
            )
        ).mappings().all()

    return JSONResponse(
        content={
            "evaluator": evaluator,
            "limit": limit,
            "items": [
                {
                    "trace_id": str(row.get("trace_id") or ""),
                    "score": float(row.get("score") or 0.0),
                    "verdict": str(row.get("verdict") or ""),
                    "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                    "evaluated_at": (
                        row.get("evaluated_at").isoformat()
                        if hasattr(row.get("evaluated_at"), "isoformat")
                        else str(row.get("evaluated_at"))
                        if row.get("evaluated_at") is not None
                        else None
                    ),
                }
                for row in rows
            ],
        }
    )


@router.get("/admin/kb-gaps")
async def admin_list_kb_gaps(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import KnowledgeGap  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        stmt = (
            select(KnowledgeGap)
            .where(KnowledgeGap.tenant_id == tenant)
            .order_by(KnowledgeGap.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "gaps": [
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "cluster_id": row.cluster_id,
                    "topic_summary": row.topic_summary,
                    "sample_questions": row.sample_questions,
                    "question_count": row.question_count,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )


@router.get("/admin/categories")
async def admin_list_categories(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from ingestion.categorizer import load_categories  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return JSONResponse(
        content={
            "categories": load_categories(
                tenant,
                config_path=get_settings().categories_config_path,
            )
        }
    )


@router.get("/admin/kb-drafts")
async def admin_list_kb_drafts(
    status: str | None = None,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        stmt = (
            select(KbDraft)
            .where(KbDraft.tenant_id == tenant)
            .order_by(KbDraft.created_at.desc())
        )
        if status:
            stmt = stmt.where(KbDraft.status == status)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "drafts": [
                {
                    "id": str(row.id),
                    "tenant_id": row.tenant_id,
                    "topic": row.topic,
                    "draft_content": row.draft_content,
                    "source_ticket_ids": row.source_ticket_ids,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                }
                for row in rows
            ]
        }
    )


@router.patch("/admin/kb-drafts/{draft_id}")
async def admin_update_kb_draft(
    draft_id: str,
    body: KbDraftUpdateRequest,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.engine import async_session  # noqa: PLC0415
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")
        draft.draft_content = body.draft_content.strip()
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.post("/admin/kb-drafts/{draft_id}/reject")
async def admin_reject_kb_draft(
    draft_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")
        draft.status = "rejected"
        draft.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.post("/admin/kb-drafts/{draft_id}/publish")
async def admin_publish_kb_draft(
    draft_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import KbDraft  # noqa: PLC0415
    from vectordb import manager as tenant_manager  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")

        doc = Document(
            page_content=draft.draft_content,
            metadata={
                "doc_id": f"kb-builder/{draft.id}",
                "source": f"kb-builder/{draft.id}",
                "title": draft.topic,
                "tenant_id": draft.tenant_id,
                "auto_generated": True,
                "generated_from_tickets": draft.source_ticket_ids,
                "categories": ["uncategorized"],
                "primary_category": "uncategorized",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        )

        if tenant_manager.Chroma is not None:
            store = tenant_manager.Chroma(
                persist_directory=str(get_settings().vectordb_chroma_dir),
                embedding_function=tenant_manager.get_embeddings(),
                collection_name=tenant_manager._collection_name(draft.tenant_id),
            )
            if hasattr(store, "add_documents"):
                store.add_documents([doc])
                if hasattr(store, "persist"):
                    store.persist()

        draft.status = "published"
        draft.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.get("/admin/experiments")
async def admin_list_experiments(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment  # noqa: PLC0415

    experiments = []
    for path in sorted(_experiments_dir().glob("*.yaml")):
        experiment = load_experiment(path)
        experiments.append(
            {
                "id": experiment.id,
                "name": experiment.name,
                "status": experiment.status,
                "latest_eval_link": None,
            }
        )
    return JSONResponse(content={"experiments": experiments})


@router.get("/admin/experiments/{experiment_id}")
async def admin_get_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    experiment = load_experiment(path)
    payload = experiment.model_dump(mode="json")
    payload["latest_eval_link"] = None
    return JSONResponse(content=payload)


@router.post("/admin/experiments/{experiment_id}/archive")
async def admin_archive_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment, save_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    experiment = load_experiment(path)
    experiment.status = "archived"
    save_experiment(experiment, path)
    return JSONResponse(content={"status": "archived", "id": experiment.id})


@router.post("/admin/experiments/{experiment_id}/regression-run")
async def admin_run_experiment_regression(
    experiment_id: str,
    baseline: str = "current",
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from datetime import datetime, timezone  # noqa: PLC0415

    if experiment_id != "current":
        candidate_path = _experiments_dir() / f"{experiment_id}.yaml"
        if not candidate_path.exists():
            raise HTTPException(status_code=404, detail="experiment not found")

    if baseline != "current":
        baseline_path = _experiments_dir() / f"{baseline}.yaml"
        if not baseline_path.exists():
            raise HTTPException(status_code=404, detail="baseline experiment not found")

    run_id = f"regression-{uuid.uuid4().hex[:12]}"
    _regression_jobs[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "baseline": baseline,
        "candidate": experiment_id,
        "created_at": datetime.now(timezone.utc),
    }
    asyncio.create_task(_run_regression_job(run_id, baseline, experiment_id))
    return JSONResponse(
        status_code=202,
        content={"job_id": run_id, "status": "queued"},
    )


@router.get("/admin/regression-runs")
async def admin_list_regression_runs(
    limit: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    normalized_limit = max(1, min(limit, 100))
    rows = await _list_regression_run_rows(normalized_limit)
    items = [_serialize_regression_row(row) for row in rows]
    known_ids = {item["run_id"] for item in items}

    pending_jobs = [
        _serialize_regression_job(job)
        for job in _regression_jobs.values()
        if str(job.get("run_id") or "") not in known_ids
    ]

    combined = pending_jobs + items
    combined.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return JSONResponse(content={"runs": combined[:normalized_limit]})


@router.get("/admin/regression-runs/{run_id}")
async def admin_get_regression_run(
    run_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    row = await _get_regression_run_row(run_id)
    if row is not None:
        report_payload, report_markdown = _read_regression_report_assets(row.get("report_path"))
        payload = _serialize_regression_row(row)
        payload["report"] = report_payload
        payload["report_markdown"] = report_markdown
        return JSONResponse(content=payload)

    job = _regression_jobs.get(run_id)
    if job is not None:
        return JSONResponse(content=_serialize_regression_job(job))

    raise HTTPException(status_code=404, detail="regression run not found")


@router.get("/admin/stale-docs")
async def admin_list_stale_docs(
    days: int = 90,
    top_cited: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from db.engine import async_session  # noqa: PLC0415
    from db.models import DocumentStats  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    documents = {item["doc_id"]: item for item in _list_tenant_documents(tenant)}

    async with async_session() as db:
        stmt = (
            select(DocumentStats)
            .where(DocumentStats.tenant_id == tenant)
            .order_by(DocumentStats.citation_count.desc())
            .limit(max(1, min(top_cited, 100)))
        )
        result = await db.execute(stmt)
        stats_rows = result.scalars().all()

    stale_documents = []
    for row in stats_rows:
        metadata = documents.get(row.doc_id)
        if not metadata or not metadata.get("last_updated"):
            continue
        try:
            last_updated = datetime.fromisoformat(str(metadata["last_updated"]))
        except ValueError:
            continue
        if last_updated >= cutoff:
            continue
        stale_documents.append(
            {
                "doc_id": row.doc_id,
                "title": metadata.get("title") or row.doc_id,
                "source": metadata.get("source") or row.doc_id,
                "last_updated": metadata.get("last_updated"),
                "citation_count": row.citation_count,
                "last_cited_at": row.last_cited_at.isoformat() if row.last_cited_at else None,
            }
        )

    try:
        prometheus_metrics.record_stale_important_docs(len(stale_documents))
    except Exception:
        pass
    return JSONResponse(content={"documents": stale_documents})


@router.post("/admin/stale-docs/{doc_id}/review")
async def admin_review_stale_doc(
    doc_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    if not _touch_tenant_document(tenant, doc_id):
        raise HTTPException(status_code=404, detail="document not found")
    return JSONResponse(content={"status": "ok"})


@router.get("/analytics/top-topics")
async def analytics_top_topics(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, dict[str, float]] = {}
    for item in summaries:
        for category in item["categories"]:
            entry = grouped.setdefault(category, {"count": 0, "quality_sum": 0.0})
            entry["count"] += 1
            entry["quality_sum"] += float(item["quality_score"] or 0)
    topics = [
        {
            "category": category,
            "count": int(values["count"]),
            "avg_quality": round(values["quality_sum"] / values["count"], 2) if values["count"] else 0.0,
        }
        for category, values in grouped.items()
    ]
    topics.sort(key=lambda item: (-item["count"], item["category"]))
    return JSONResponse(content={"topics": topics[:10]})


@router.get("/analytics/resolution-rate")
async def analytics_resolution_rate(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, dict[str, int]] = {}
    for item in summaries:
        for category in item["categories"]:
            entry = grouped.setdefault(category, {"total": 0, "resolved": 0})
            entry["total"] += 1
            if item["route"] == "auto":
                entry["resolved"] += 1
    payload = [
        {
            "category": category,
            "resolution_rate": round(values["resolved"] / values["total"], 4) if values["total"] else 0.0,
            "total": values["total"],
        }
        for category, values in grouped.items()
    ]
    payload.sort(key=lambda item: item["category"])
    return JSONResponse(content={"topics": payload})


@router.get("/analytics/cost-summary")
async def analytics_cost_summary(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    total_cost = round(sum(float(item["cost_usd"] or 0.0) for item in summaries), 6)
    per_category: dict[str, float] = {}
    per_model: dict[str, float] = {}
    for item in summaries:
        for category in item["categories"]:
            per_category[category] = round(per_category.get(category, 0.0) + float(item["cost_usd"] or 0.0), 6)
        model_name = str(item.get("model_name") or "unknown")
        per_model[model_name] = round(per_model.get(model_name, 0.0) + float(item["cost_usd"] or 0.0), 6)
    return JSONResponse(
        content={
            "summary": {
                "total_cost_usd": total_cost,
                "label": "self-hosted (no cost)" if total_cost == 0 else f"${total_cost:.2f}",
                "tooltip": "local models are not billed" if total_cost == 0 else "",
                "free_tier": total_cost == 0,
            },
            "per_category": [
                {"category": category, "cost_usd": cost}
                for category, cost in sorted(per_category.items())
            ],
            "per_model": [
                {"model_name": model_name, "cost_usd": cost}
                for model_name, cost in sorted(per_model.items())
            ],
        }
    )


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = 30,
    metric: str = "quality",
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, list[float]] = {}
    for item in summaries:
        bucket = item["created_at"].date().isoformat()
        if metric == "cost":
            value = float(item["cost_usd"] or 0.0)
        elif metric == "resolution":
            value = 1.0 if item["route"] == "auto" else 0.0
        else:
            value = float(item["quality_score"] or 0.0)
        grouped.setdefault(bucket, []).append(value)
    payload = [
        {
            "date": bucket,
            "value": round(sum(values) / len(values), 4) if values else 0.0,
        }
        for bucket, values in sorted(grouped.items())
    ]
    return JSONResponse(content={"metric": metric, "points": payload})


@router.post("/channels/email/inbound")
async def email_inbound_webhook(request: Request) -> JSONResponse:
    from channels.email_webhook import process_webhook_payload, verify_signature  # noqa: PLC0415

    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Signature") or request.headers.get("X-Webhook-Signature")
    webhook_secret = (
        getattr(settings, "email_webhook_signing_secret", None)
        or getattr(settings, "email_webhook_secret", None)
    )
    if not verify_signature(body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = _json.loads(body.decode("utf-8") or "{}")
    await process_webhook_payload(payload)
    return JSONResponse(content={"ok": True})


@router.get("/admin/providers")
async def admin_list_providers(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return JSONResponse(content=_load_provider_admin_snapshot(tenant))


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(
    trace_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")

    from sqlite_trace import get_trace_detail  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    detail_params = inspect.signature(get_trace_detail).parameters
    if "tenant_id" in detail_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in detail_params.values()
    ):
        trace = await asyncio.to_thread(get_trace_detail, trace_id, tenant_id=tenant)
    else:
        trace = await asyncio.to_thread(get_trace_detail, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(content=trace)


@router.delete("/admin/traces")
async def admin_purge_traces(
    request: Request,
    older_than_days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    from sqlite_trace import purge_old_traces

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    purge_params = inspect.signature(purge_old_traces).parameters
    if "tenant_id" in purge_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in purge_params.values()
    ):
        result = await asyncio.to_thread(
            purge_old_traces,
            older_than_days,
            tenant_id=tenant,
        )
    else:
        result = await asyncio.to_thread(purge_old_traces, older_than_days)

    for table, count in (
        ("traces", result["traces_deleted"]),
        ("trace_steps", result["steps_deleted"]),
        ("feedback", result["feedback_deleted"]),
    ):
        prometheus_metrics.record_traces_purged(table, count)

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="trace_purge",
        resource=f"traces/older_than={older_than_days}d",
        detail=(
            result
            if _user.get("tenant", "default") == "default"
            else {**result, "tenant": _user.get("tenant", "default")}
        ),
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content=result)


@router.delete("/admin/audit-log")
async def admin_purge_audit(
    request: Request,
    older_than_days: int = 90,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    from db.audit import purge_old_audit

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    audit_params = inspect.signature(purge_old_audit).parameters
    if "tenant_id" in audit_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in audit_params.values()
    ):
        deleted = await purge_old_audit(older_than_days, tenant_id=tenant)
    else:
        deleted = await purge_old_audit(older_than_days)
    try:
        prometheus_metrics.record_audit_purged(deleted)
    except Exception:
        pass

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="audit_purge",
        resource=f"audit_log/older_than={older_than_days}d",
        detail={
            "deleted": deleted,
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _user: dict = Depends(require_role("agent", "admin")),
) -> UploadResponse:
    """Upload a document (PDF/DOCX/TXT/MD) and ingest it into the vector store."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".html"}
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed))}",
        )

    import re as _re

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    safe_name = Path(file.filename.replace("\\", "/")).name
    safe_name = _re.sub(r"[^\w\-.]", "_", safe_name)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_root = PROJECT_ROOT / "data" / "uploads"
    if tenant == "default":
        upload_dir = upload_root
    else:
        upload_dir = upload_root / _re.sub(r"[^A-Za-z0-9_\-]", "_", tenant)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / safe_name
    settings = get_settings()
    upload_limit = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)
    docs = None
    assigned_categories: list[str] = []
    try:
        content = bytearray()
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > upload_limit:
                try:
                    prometheus_metrics.record_body_size_rejection("upload_too_large")
                except Exception:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds limit of {upload_limit} bytes",
                )
        file_path.write_bytes(bytes(content))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="upload",
        resource=f"document:{safe_name}",
        detail={"tenant": tenant},
        ip_address=request.client.host if request.client else None,
    )

    if _DocumentLoader is not None:
        try:
            from ingestion.categorizer import annotate_documents_with_categories

            loader = _DocumentLoader(recursive=False)
            docs = loader.load_documents(str(upload_dir))
            if docs:
                assigned_by_source = annotate_documents_with_categories(docs, tenant_id=tenant)
                assigned_categories = list(assigned_by_source.get(safe_name) or [])
        except Exception as exc:
            logger.warning("Category pre-processing failed for %s: %s", safe_name, exc)

    if tenant == "default":
        try:
            from tasks.ingest_task import ingest_document

            task = ingest_document.delay(str(file_path))
            if getattr(settings, "llm_cache_enabled", False):
                deleted = cache_delete_pattern(f"llm_resp:{tenant}:*")
                logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
            return UploadResponse(
                status="accepted",
                filename=safe_name,
                message=f"File uploaded. Processing in background. task_id={task.id}",
                assigned_categories=assigned_categories,
            )
        except Exception as exc:
            logger.info("Celery async upload unavailable, falling back to sync: %s", exc)

    if _DocumentLoader is not None and _build_vector_store is not None:
        try:
            if docs is None:
                loader = _DocumentLoader(recursive=False)
                docs = loader.load_documents(str(upload_dir))
            if docs:
                success = _rebuild_vector_store_from_docs(docs, tenant_id=tenant)
                if success:
                    if getattr(settings, "llm_cache_enabled", False):
                        deleted = cache_delete_pattern(f"llm_resp:{tenant}:*")
                        logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
                    return UploadResponse(
                        status="ok",
                        filename=safe_name,
                        message=f"File uploaded and indexed. {len(docs)} document(s) processed.",
                        assigned_categories=assigned_categories,
                    )
                else:
                    return UploadResponse(
                        status="partial",
                        filename=safe_name,
                        message="File saved but indexing failed. Check server logs.",
                        assigned_categories=assigned_categories,
                    )
            else:
                return UploadResponse(
                    status="partial",
                    filename=safe_name,
                    message="File saved but no text content could be extracted.",
                    assigned_categories=assigned_categories,
                )
        except Exception as exc:
            logger.error("Ingestion error for %s: %s", file.filename, exc, exc_info=True)
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message=f"File saved but ingestion failed: {exc}",
                assigned_categories=assigned_categories,
            )
    else:
        return UploadResponse(
            status="partial",
            filename=safe_name,
            message="File saved. Document loader or vector store builder not available for indexing.",
            assigned_categories=assigned_categories,
        )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> TaskStatusResponse:
    """Check background task status."""
    try:
        from tasks.celery_app import celery_app

        result = celery_app.AsyncResult(task_id)
        result_payload: Optional[dict] = None
        meta_payload: Optional[dict] = None

        if result.ready():
            if isinstance(result.result, dict):
                result_payload = result.result
            elif result.result is not None:
                result_payload = {"detail": str(result.result)}
            if result.status == "SUCCESS" and result_payload and result_payload.get("status") == "ok":
                initialize_vector_store()
        elif isinstance(result.info, dict):
            meta_payload = result.info
        elif result.info is not None:
            meta_payload = {"detail": str(result.info)}

        return TaskStatusResponse(
            task_id=task_id,
            status=result.status,
            result=result_payload,
            meta=meta_payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Task backend error: {exc}")


@router.get("/auth/sso/providers")
async def sso_providers() -> dict[str, list[dict[str, str]]]:
    return {"providers": list_sso_providers(get_settings())}


@router.get("/auth/sso/{provider}/login")
async def sso_login(provider: str, request: Request):
    try:
        client = get_oidc_client(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if client is None:
        raise HTTPException(status_code=404, detail="Provider not configured")

    redirect_uri = request.url_for("sso_callback", provider=provider)
    return await client.authorize_redirect(request, str(redirect_uri))


@router.get("/auth/sso/{provider}/callback", name="sso_callback")
async def sso_callback(provider: str, request: Request):
    from auth.jwt_handler import (
        ACCESS_TOKEN_TTL,
        REFRESH_TOKEN_TTL,
        create_access_token,
        create_refresh_token,
    )

    try:
        client = get_oidc_client(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if client is None:
        raise HTTPException(status_code=404, detail="Provider not configured")

    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"SSO callback failed: {exc}")

    userinfo = token.get("userinfo") if isinstance(token, dict) else None
    if userinfo is None and hasattr(client, "userinfo"):
        userinfo = await client.userinfo(token=token)
    if not isinstance(userinfo, dict):
        raise HTTPException(status_code=400, detail="OIDC userinfo is missing")

    try:
        user = await resolve_oidc_user(provider, userinfo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    access_token = create_access_token(str(user.id), user.role, user.tenant_id)
    refresh_token = create_refresh_token(str(user.id), user.role, user.tenant_id)
    secure_cookie = getattr(get_settings(), "rag_env", "development") == "production"

    response = RedirectResponse("/static/chat.html", status_code=307)
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=ACCESS_TOKEN_TTL,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=REFRESH_TOKEN_TTL,
        path="/",
    )
    await log_audit(
        actor=str(user.id),
        action="sso_login",
        resource=f"auth/{provider}",
        detail={"provider": provider, "tenant": user.tenant_id},
        ip_address=request.client.host if request.client else None,
    )
    return response


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT tokens."""
    from auth.jwt_handler import create_access_token, create_refresh_token

    import os

    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    admin_default_tenant = os.getenv("ADMIN_DEFAULT_TENANT", "default") or "default"
    login_tenant = "default" if not admin_hash else admin_default_tenant
    client_ip = request.client.host if request.client else None

    async def _record_failure(reason: str) -> None:
        try:
            prometheus_metrics.record_auth_failure(reason)
        except Exception:
            pass
        await log_audit(
            actor=body.username or "<anonymous>",
            action="login_failed",
            resource="auth",
            detail={"reason": reason, "tenant": login_tenant},
            ip_address=client_ip,
        )

    if not admin_hash:
        if body.username == "admin" and body.password == "admin":
            response = TokenResponse(
                access_token=create_access_token("admin", "admin", login_tenant),
                refresh_token=create_refresh_token("admin", "admin", login_tenant),
            )
            await log_audit(
                actor=body.username,
                action="login",
                resource="auth",
                detail={"tenant": login_tenant},
                ip_address=client_ip,
            )
            return response
        await _record_failure("bad_credentials_dev")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from passlib.hash import bcrypt

    if body.username != admin_user:
        await _record_failure("unknown_user")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.verify(body.password, admin_hash):
        await _record_failure("bad_password")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = TokenResponse(
        access_token=create_access_token(body.username, "admin", login_tenant),
        refresh_token=create_refresh_token(body.username, "admin", login_tenant),
    )
    await log_audit(
        actor=body.username,
        action="login",
        resource="auth",
        detail={"tenant": login_tenant},
        ip_address=client_ip,
    )
    return response


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest) -> TokenResponse:
    """Refresh access token."""
    from auth.jwt_handler import create_access_token, create_refresh_token, verify_token

    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return TokenResponse(
        access_token=create_access_token(
            payload["sub"],
            payload.get("role", "viewer"),
            payload.get("tenant", "default"),
        ),
        refresh_token=create_refresh_token(
            payload["sub"],
            payload.get("role", "viewer"),
            payload.get("tenant", "default"),
        ),
    )


@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> HistoryResponse:
    global _db_retry_after
    if time.monotonic() >= _db_retry_after:
        try:
            from sqlalchemy import select

            from db.engine import async_session
            from db.models import Message

            async with async_session() as db:
                result = await asyncio.wait_for(
                    db.execute(
                        select(Message)
                        .where(Message.session_id == uuid.UUID(session_id))
                        .order_by(Message.created_at)
                    ),
                    timeout=0.5,
                )
                messages = [
                    HistoryMessage(role=message.role, content=message.content)
                    for message in result.scalars()
                ]
                _db_retry_after = 0.0
                if messages:
                    return HistoryResponse(session_id=session_id, messages=messages)
        except Exception as exc:
            _db_retry_after = time.monotonic() + 60.0
            logger.warning("DB history fallback: %s", exc)

    if session_id in _sessions:
        session = _sessions[session_id]
        if hasattr(session, "history"):
            history = session.history
        elif isinstance(session, dict):
            history = session.get("history", [])
        else:
            history = []

        messages = [
            HistoryMessage(role=msg.get("role", ""), content=msg.get("content", ""))
            for msg in history
        ]
        if messages:
            return HistoryResponse(session_id=session_id, messages=messages)

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    _user: dict = Depends(require_role("agent", "admin")),
) -> list[SessionInfo]:
    result: dict[str, SessionInfo] = {}

    global _db_retry_after
    if time.monotonic() >= _db_retry_after:
        try:
            from sqlalchemy import func, select

            from db.engine import async_session
            from db.models import Message, Session as DBSession

            async with async_session() as db:
                db_result = await asyncio.wait_for(
                    db.execute(
                        select(DBSession.id, func.count(Message.id))
                        .outerjoin(Message, Message.session_id == DBSession.id)
                        .group_by(DBSession.id)
                        .order_by(DBSession.last_access.desc())
                    ),
                    timeout=0.5,
                )
                for session_uuid, message_count in db_result.all():
                    result[session_uuid.hex] = SessionInfo(
                        session_id=session_uuid.hex,
                        message_count=message_count,
                    )
                _db_retry_after = 0.0
        except Exception as exc:
            _db_retry_after = time.monotonic() + 60.0
            logger.warning("DB sessions fallback: %s", exc)

    for sid, session in list(_sessions.items()):
        if hasattr(session, "_history"):
            count = len(session._history)
        elif hasattr(session, "history"):
            count = len(session.history)
        elif isinstance(session, dict):
            count = len(session.get("history", []))
        else:
            count = 0
        if sid not in result:
            result[sid] = SessionInfo(session_id=sid, message_count=count)
    return list(result.values())


@router.delete("/sessions/{session_id}")
async def clear_session(
    request: Request,
    session_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> Dict[str, str]:
    global _db_retry_after
    found = False

    if session_id in _sessions:
        session = _sessions[session_id]
        if hasattr(session, "clear"):
            session.clear()
        del _sessions[session_id]
        found = True
    _session_last_access.pop(session_id, None)

    if time.monotonic() >= _db_retry_after:
        try:
            from sqlalchemy import select

            from db.engine import async_session
            from db.models import Session as DBSession

            async with async_session() as db:
                db_result = await asyncio.wait_for(
                    db.execute(select(DBSession).where(DBSession.id == uuid.UUID(session_id))),
                    timeout=0.5,
                )
                db_session = db_result.scalar_one_or_none()
                if db_session is not None:
                    await db.delete(db_session)
                    await asyncio.wait_for(db.commit(), timeout=0.5)
                    found = True
                _db_retry_after = 0.0
        except Exception as exc:
            _db_retry_after = time.monotonic() + 60.0
            logger.warning("DB clear session fallback: %s", exc)

    if not found:
        raise HTTPException(status_code=404, detail="Session not found")

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="delete_session",
        resource=f"session:{session_id}",
        detail={"tenant": _user.get("tenant", "default")},
        ip_address=request.client.host if request.client else None,
    )
    return {"status": "ok", "message": f"Session {session_id} cleared"}


@router.get("/health/live")
async def health_liveness() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"status": "alive", "service": "rag-support-assistant"},
    )


@router.get("/health/ready", response_model=HealthResponse)
async def health_readiness() -> JSONResponse:
    if _shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
                "detail": "process is draining - stop sending traffic",
            },
        )
    return await health_check()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    if _shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
                "detail": "process is draining - stop sending traffic",
            },
        )
    settings = get_settings()

    ollama_status, chroma_status, sqlite_status, postgres_status, redis_status = await asyncio.gather(
        _probe_ollama(settings.ollama_base_url),
        _probe_chromadb(settings.vectordb_chroma_dir),
        _probe_sqlite(settings.tracing_db_path),
        _probe_postgres(),
        _probe_redis(),
    )
    try:
        prometheus_metrics.record_component_health("ollama", ollama_status.status)
        prometheus_metrics.record_component_health("chromadb", chroma_status.status)
        prometheus_metrics.record_component_health("sqlite", sqlite_status.status)
        prometheus_metrics.record_component_health("postgres", postgres_status.status)
        prometheus_metrics.record_component_health("redis", redis_status.status)
    except Exception:
        pass

    critical_down = ollama_status.status == "error" or chroma_status.status == "error"
    non_critical_error = (
        sqlite_status.status == "error"
        or postgres_status.status == "error"
        or redis_status.status == "error"
    )
    overall = "unhealthy" if critical_down else ("degraded" if non_critical_error else "ok")
    breakers_snap: List[Dict[str, Any]] = []
    try:
        from agent.graph import get_default_breaker
    except ImportError:
        get_default_breaker = None  # type: ignore[assignment]

    if get_default_breaker is not None:
        breaker = get_default_breaker()
        if breaker is not None:
            breakers_snap.append(breaker.snapshot())

    response = HealthResponse(
        status=overall,
        components={
            "ollama": ollama_status,
            "chromadb": chroma_status,
            "sqlite": sqlite_status,
            "postgres": postgres_status,
            "redis": redis_status,
        },
        vector_store_loaded=_vector_store is not None,
        sessions_count=len(_sessions),
        pipeline_available=_run_qa_pipeline is not None,
        circuit_breakers=breakers_snap,
        features={
            "streaming_enabled": bool(getattr(settings, "streaming_enabled", False)),
        },
    )

    status_code = 503 if critical_down else 200
    return JSONResponse(content=response.model_dump(), status_code=status_code)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="RAG Support Assistant API", version="0.3.0", lifespan=_lifespan)

# Session + CORS
_app_settings = get_settings()
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
        path_format = getattr(route, "path_format", None)
        if path_format:
            return path_format

        path = getattr(route, "path", None)
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_rejected)
app.include_router(router)
app.add_api_route("/webhook/email", email_inbound_webhook, methods=["POST"])
_static_dir = PROJECT_ROOT / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/agent", response_class=HTMLResponse)
async def agent_dashboard(
    _user: dict = Depends(require_role("agent", "admin")),
) -> HTMLResponse:
    agent_path = PROJECT_ROOT / "static" / "agent.html"
    if not agent_path.exists():
        raise HTTPException(status_code=404, detail="agent dashboard not found")
    return HTMLResponse(agent_path.read_text(encoding="utf-8"))


@app.get("/admin/traces/{trace_id}")
async def admin_trace_detail_redirect(trace_id: str) -> RedirectResponse:
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")
    return RedirectResponse(url=f"/traces-ui/{trace_id}", status_code=307)


@app.get("/metrics")
async def prometheus_metrics_endpoint() -> Response:
    if not getattr(prometheus_metrics, "PROMETHEUS_AVAILABLE", False):
        return JSONResponse(
            status_code=501,
            content={"detail": "prometheus-client is not installed"},
        )

    prometheus_metrics.ACTIVE_SESSIONS.set(len(_sessions))
    return Response(
        content=prometheus_metrics.generate_latest(prometheus_metrics.REGISTRY),
        media_type=prometheus_metrics.CONTENT_TYPE_LATEST,
    )

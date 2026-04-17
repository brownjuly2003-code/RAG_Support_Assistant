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
import json as _json
import logging
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from api.correlation import generate_request_id, get_request_id, sanitize_request_id, set_request_id
from auth.dependencies import get_current_user, require_role
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
    from graph import ConversationSession, run_qa_pipeline
    _ConversationSession = ConversationSession
    _run_qa_pipeline = run_qa_pipeline
except ImportError:
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
    from manager import build_vector_store, get_retriever, get_embeddings
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
            tracing_db_path = PROJECT_ROOT / "data" / "tracing" / "traces.db"
            session_ttl_seconds = 7200
            trace_retention_days = 90
            trace_purge_interval_sec = 86400
            shutdown_ready_delay_sec = 5.0
            api_key = ""
            require_ollama = False
            cors_origins = ["*"]
        return _S()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    tenant_id: str = Field(
        default="default",
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )


class SourceInfo(BaseModel):
    source: str = ""
    page_content: str = ""


class AskResponse(BaseModel):
    answer: str
    quality_score: int = 50
    route: str = "auto"
    sources: List[SourceInfo] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    suggested_questions: List[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., max_length=100)
    session_id: str = Field(..., max_length=100)
    rating: str = Field(..., pattern=r"^(up|down)$")
    reason: Optional[str] = Field(default="", max_length=500)


class EscalateRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    question: str = Field(default="", max_length=2000)
    reason: str = Field(default="user_request", max_length=200)


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


class UploadResponse(BaseModel):
    status: str
    filename: str
    message: str
    tenant_id: str = "default"


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


def _get_pipeline_semaphore() -> asyncio.Semaphore:
    global _pipeline_semaphore

    if _pipeline_semaphore is None:
        settings = get_settings()
        size = int(getattr(settings, "max_concurrent_pipelines", 8))
        _pipeline_semaphore = asyncio.Semaphore(size)

    return _pipeline_semaphore


async def _get_or_create_session(session_id: Optional[str]) -> tuple:
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

    if session_id not in _session_llm_state:
        if _ConversationSession is not None and _retriever is not None:
            session = _ConversationSession(
                retriever=_retriever,
                llm=_llm,
                max_iterations=2,
                max_history=20,
            )
            if db_history and hasattr(session, "_history"):
                max_history = getattr(session, "_max_history", 20)
                session._history = db_history[-(max_history * 2):]
            _session_llm_state[session_id] = session
        else:
            _session_llm_state[session_id] = {"history": list(db_history)}

    import time as _time
    _session_last_access[session_id] = _time.monotonic()
    return session_id, _session_llm_state[session_id]


# ---------------------------------------------------------------------------
# Startup logic
# ---------------------------------------------------------------------------

def initialize_vector_store() -> None:
    global _vector_store, _retriever, _chunks

    settings = get_settings()
    chroma_dir = settings.vectordb_chroma_dir

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
                collection_name="documents",
            )

            if _get_retriever is not None:
                _retriever = _get_retriever(_vector_store, chunks=None)
            else:
                _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

            logger.info("Vector store loaded from %s", chroma_dir)
            return
        except Exception as exc:
            logger.error("Failed to load existing Chroma: %s", exc, exc_info=True)

    logger.info("No existing vector store found. Upload documents via /api/upload to create one.")


def _rebuild_vector_store_from_docs(docs: List[Any]) -> bool:
    global _vector_store, _retriever, _chunks

    if _build_vector_store is None:
        logger.warning("build_vector_store not available")
        return False

    try:
        chunk_config = {"chunk_size": 800, "chunk_overlap": 200}
        _vector_store, _chunks = _build_vector_store(docs, chunk_config)

        if _get_retriever is not None:
            _retriever = _get_retriever(_vector_store, chunks=_chunks)
        elif hasattr(_vector_store, "as_retriever"):
            _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

        for sid, session in _sessions.items():
            if hasattr(session, "_retriever"):
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

        from db.engine import async_session
        from sqlalchemy import text

        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=1.0)
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

    session_result = _get_or_create_session(body.session_id)
    if asyncio.iscoroutine(session_result):
        session_id, session = await session_result
    else:
        session_id, session = session_result

    if hasattr(session, "ask"):
        settings = get_settings()
        timeout = float(getattr(settings, "request_timeout_sec", 30.0))
        acquire_timeout = float(
            getattr(settings, "pipeline_acquire_timeout_sec", 0.5)
        )
        request_id = get_request_id()
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
                    asyncio.to_thread(session.ask, question, request_id),
                    timeout=timeout,
                )

                answer = result.get("answer") or ""
                quality = result.get("quality_score") or 50
                route = result.get("route") or "auto"

                sources_list = []
                docs = result.get("graded_docs") or result.get("context_docs") or []
                for doc in docs[:5]:
                    if isinstance(doc, dict):
                        src = doc.get("metadata", {}).get("source", "")
                        content = doc.get("page_content", "")[:200]
                    else:
                        src = getattr(doc, "metadata", {}).get("source", "")
                        content = getattr(doc, "page_content", "")[:200]
                    sources_list.append(SourceInfo(source=src, page_content=content))

                response = AskResponse(
                    answer=answer,
                    quality_score=quality,
                    route=route,
                    sources=sources_list,
                    session_id=session_id,
                    trace_id=result.get("trace_id") or "",
                    suggested_questions=result.get("suggested_questions") or [],
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
        detail={"question_length": len(body.question)},
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
    return response


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
            detail={"question_length": len(body.question)},
            ip_address=request.client.host if request.client else None,
        )

        try:
            prompt = ""
            docs: List[Any] = []
            chat_history: List[Dict[str, str]] = []

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

                try:
                    from prompts import build_qa_prompt, build_conversational_qa_prompt  # noqa: PLC0415
                except ImportError:
                    from agent.prompts import build_qa_prompt, build_conversational_qa_prompt  # type: ignore[no-redef]  # noqa: PLC0415

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

            yield "data: " + _json.dumps({"type": "token_start"}) + "\n\n"
            try:
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
            for doc in docs[:5]:
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

            quality = 70 if len(full_answer.strip()) > 20 else 40
            route = "auto" if quality >= 70 else "human"
            suggested_questions: List[str] = []
            if route == "auto":
                try:
                    try:
                        from prompts import build_suggested_questions_prompt  # noqa: PLC0415
                    except ImportError:
                        from agent.prompts import build_suggested_questions_prompt  # type: ignore[no-redef]  # noqa: PLC0415

                    question_llm = getattr(session, "_llm", None)
                    if question_llm is None:
                        try:
                            from graph import LocalOllamaLLM  # noqa: PLC0415
                        except ImportError:
                            from agent.graph import LocalOllamaLLM  # type: ignore[no-redef]  # noqa: PLC0415
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
                "trace_id": "",
                "suggested_questions": suggested_questions,
            }) + "\n\n"
        except Exception as exc:
            logger.warning("SSE streaming path failed, fallback to sync pipeline: %s", exc, exc_info=True)
            try:
                if hasattr(session, "ask"):
                    result = await asyncio.get_running_loop().run_in_executor(
                        None, session.ask, question
                    )
                    answer = result.get("answer") or "Не удалось получить ответ."
                    quality = result.get("quality_score") or 50
                    route = result.get("route") or "auto"
                    raw_sources = result.get("graded_docs") or result.get("context_docs") or []
                    sources = []
                    for item in raw_sources:
                        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
                        sources.append({
                            "source": metadata.get("source") or metadata.get("file_name") or "",
                            "page_content": item.get("page_content", "") if isinstance(item, dict) else "",
                        })
                    trace_id = result.get("trace_id") or ""
                    suggested_questions = result.get("suggested_questions") or []
                else:
                    answer = "Сессия не инициализирована."
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": answer})
                    quality, route, sources, trace_id, suggested_questions = 0, "human", [], "", []

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
        detail={"rating": body.rating},
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

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="escalate",
        resource=f"session:{body.session_id}",
        detail={"reason": body.reason},
        ip_address=request.client.host if request.client else None,
    )

    return {
        "status": "ok",
        "message": "Ваш запрос передан оператору. Мы ответим в ближайшее время.",
    }


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
    try:
        from sqlite_trace import get_metrics_snapshot  # noqa: PLC0415

        return get_metrics_snapshot()
    except Exception as exc:
        logger.warning("Failed to get metrics: %s", exc)
        return {"error": str(exc), "generated_at": ""}


@router.post("/admin/circuit-breaker/reset")
async def admin_reset_circuit_breaker(
    request: Request,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from graph import get_default_breaker

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
    limit: int = 50,
    actor: str | None = None,
    action: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    limit = max(1, min(500, limit))

    try:
        from sqlalchemy import select  # noqa: PLC0415

        from db.engine import async_session  # noqa: PLC0415
        from db.models import AuditLog  # noqa: PLC0415

        async with async_session() as db:
            stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
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


@router.get("/admin/traces")
async def admin_list_traces(
    limit: int = 50,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlite_trace import list_recent_traces  # noqa: PLC0415

    traces = await asyncio.to_thread(list_recent_traces, limit)
    return JSONResponse(content={"traces": traces})


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(
    trace_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")

    from sqlite_trace import get_trace_detail  # noqa: PLC0415

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
        detail=result,
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

    deleted = await purge_old_audit(older_than_days)
    try:
        prometheus_metrics.record_audit_purged(deleted)
    except Exception:
        pass

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="audit_purge",
        resource=f"audit_log/older_than={older_than_days}d",
        detail={"deleted": deleted},
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

    safe_name = Path(file.filename.replace("\\", "/")).name
    safe_name = _re.sub(r"[^\w\-.]", "_", safe_name)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_dir = PROJECT_ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / safe_name
    settings = get_settings()
    upload_limit = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)
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
        ip_address=request.client.host if request.client else None,
    )

    try:
        from tasks.ingest_task import ingest_document

        task = ingest_document.delay(str(file_path))
        return UploadResponse(
            status="accepted",
            filename=safe_name,
            message=f"File uploaded. Processing in background. task_id={task.id}",
        )
    except Exception as exc:
        logger.info("Celery async upload unavailable, falling back to sync: %s", exc)

    if _DocumentLoader is not None and _build_vector_store is not None:
        try:
            loader = _DocumentLoader(recursive=False)
            docs = loader.load_documents(str(upload_dir))
            if docs:
                success = _rebuild_vector_store_from_docs(docs)
                if success:
                    return UploadResponse(
                        status="ok",
                        filename=safe_name,
                        message=f"File uploaded and indexed. {len(docs)} document(s) processed.",
                    )
                else:
                    return UploadResponse(
                        status="partial",
                        filename=safe_name,
                        message="File saved but indexing failed. Check server logs.",
                    )
            else:
                return UploadResponse(
                    status="partial",
                    filename=safe_name,
                    message="File saved but no text content could be extracted.",
                )
        except Exception as exc:
            logger.error("Ingestion error for %s: %s", file.filename, exc, exc_info=True)
            return UploadResponse(
                status="partial",
                filename=safe_name,
                message=f"File saved but ingestion failed: {exc}",
            )
    else:
        return UploadResponse(
            status="partial",
            filename=safe_name,
            message="File saved. Document loader or vector store builder not available for indexing.",
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


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT tokens."""
    from auth.jwt_handler import create_access_token, create_refresh_token

    import os

    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
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
            detail={"reason": reason},
            ip_address=client_ip,
        )

    if not admin_hash:
        if body.username == "admin" and body.password == "admin":
            response = TokenResponse(
                access_token=create_access_token("admin", "admin"),
                refresh_token=create_refresh_token("admin", "admin"),
            )
            await log_audit(
                actor=body.username,
                action="login",
                resource="auth",
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
        access_token=create_access_token(body.username, "admin"),
        refresh_token=create_refresh_token(body.username, "admin"),
    )
    await log_audit(
        actor=body.username,
        action="login",
        resource="auth",
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
        access_token=create_access_token(payload["sub"], payload.get("role", "viewer")),
        refresh_token=create_refresh_token(payload["sub"], payload.get("role", "viewer")),
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
        from graph import get_default_breaker
    except ImportError:
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
    )

    status_code = 503 if critical_down else 200
    return JSONResponse(content=response.model_dump(), status_code=status_code)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="RAG Support Assistant API", version="0.3.0", lifespan=_lifespan)

# CORS
_cors_settings = get_settings()
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


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_rejected)
app.include_router(router)
_static_dir = PROJECT_ROOT / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


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

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

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

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
except Exception:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

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
        pass

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
            require_ollama = False
        return _S()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class SourceInfo(BaseModel):
    source: str = ""
    page_content: str = ""


class AskResponse(BaseModel):
    answer: str
    quality_score: int = 50
    route: str = "auto"
    sources: List[SourceInfo] = Field(default_factory=list)
    session_id: str = ""


class HistoryMessage(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[HistoryMessage]


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


class UploadResponse(BaseModel):
    status: str
    filename: str
    message: str


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_sessions: Dict[str, Any] = {}
_vector_store: Any = None
_retriever: Any = None
_chunks: List[Any] = []
_llm: Any = None


def _get_or_create_session(session_id: Optional[str]) -> tuple:
    global _retriever, _llm

    if not session_id:
        session_id = uuid.uuid4().hex

    if session_id not in _sessions:
        if _ConversationSession is not None and _retriever is not None:
            _sessions[session_id] = _ConversationSession(
                retriever=_retriever,
                llm=_llm,
                max_iterations=2,
                max_history=20,
            )
        else:
            _sessions[session_id] = {"history": []}

    return session_id, _sessions[session_id]


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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    settings = get_settings()
    settings.ensure_dirs()

    try:
        settings.validate()
    except RuntimeError as exc:
        logger.error("Startup validation failed: %s", exc)
        raise SystemExit(1) from exc

    initialize_vector_store()
    logger.info("RAG Support Assistant started")

    yield

    # Shutdown
    logger.info("RAG Support Assistant shutting down")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["RAG API"])


@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(request: Request, body: AskRequest) -> AskResponse:
    """Ask a question to the RAG assistant."""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    session_id, session = _get_or_create_session(body.session_id)

    if hasattr(session, "ask"):
        try:
            result = session.ask(question)

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

            return AskResponse(
                answer=answer,
                quality_score=quality,
                route=route,
                sources=sources_list,
                session_id=session_id,
            )
        except Exception as exc:
            logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
            return AskResponse(
                answer="Не удалось обработать запрос автоматически. Ваш вопрос передан оператору.",
                quality_score=0,
                route="human",
                sources=[],
                session_id=session_id,
            )
    else:
        session["history"].append({"role": "user", "content": question})
        fallback_answer = f"[DEMO] Pipeline not available. Question received: {question}"
        session["history"].append({"role": "assistant", "content": fallback_answer})
        return AskResponse(
            answer=fallback_answer,
            quality_score=0,
            route="human",
            sources=[],
            session_id=session_id,
        )


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(request: Request, file: UploadFile = File(...)) -> UploadResponse:
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

    upload_dir = PROJECT_ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    try:
        content = await file.read()
        file_path.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    if _DocumentLoader is not None and _build_vector_store is not None:
        try:
            loader = _DocumentLoader(recursive=False)
            docs = loader.load_documents(str(upload_dir))
            if docs:
                success = _rebuild_vector_store_from_docs(docs)
                if success:
                    return UploadResponse(
                        status="ok",
                        filename=file.filename,
                        message=f"File uploaded and indexed. {len(docs)} document(s) processed.",
                    )
                else:
                    return UploadResponse(
                        status="partial",
                        filename=file.filename,
                        message="File saved but indexing failed. Check server logs.",
                    )
            else:
                return UploadResponse(
                    status="partial",
                    filename=file.filename,
                    message="File saved but no text content could be extracted.",
                )
        except Exception as exc:
            logger.error("Ingestion error for %s: %s", file.filename, exc, exc_info=True)
            return UploadResponse(
                status="partial",
                filename=file.filename,
                message=f"File saved but ingestion failed: {exc}",
            )
    else:
        return UploadResponse(
            status="partial",
            filename=file.filename,
            message="File saved. Document loader or vector store builder not available for indexing.",
        )


@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(session_id: str) -> HistoryResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

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
    return HistoryResponse(session_id=session_id, messages=messages)


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str) -> Dict[str, str]:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    if hasattr(session, "clear"):
        session.clear()
    del _sessions[session_id]
    return {"status": "ok", "message": f"Session {session_id} cleared"}


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check — actively probes all dependencies."""
    settings = get_settings()

    ollama_status, chroma_status, sqlite_status = (
        await _probe_ollama(settings.ollama_base_url),
        await _probe_chromadb(settings.vectordb_chroma_dir),
        await _probe_sqlite(settings.tracing_db_path),
    )

    critical_down = ollama_status.status == "error" or chroma_status.status == "error"
    overall = "unhealthy" if critical_down else (
        "degraded" if sqlite_status.status == "error" else "ok"
    )

    response = HealthResponse(
        status=overall,
        components={
            "ollama": ollama_status,
            "chromadb": chroma_status,
            "sqlite": sqlite_status,
        },
        vector_store_loaded=_vector_store is not None,
        sessions_count=len(_sessions),
        pipeline_available=_run_qa_pipeline is not None,
    )

    status_code = 503 if critical_down else 200
    return JSONResponse(content=response.model_dump(), status_code=status_code)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="RAG Support Assistant API", version="0.3.0", lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(router)

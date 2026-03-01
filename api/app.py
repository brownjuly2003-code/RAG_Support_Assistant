"""
api/app.py

FastAPI REST API for the RAG Support Assistant.

Endpoints:
    POST /api/ask          - Ask a question (with optional session)
    POST /api/upload       - Upload a document (PDF/DOCX/TXT)
    GET  /api/sessions/{session_id}/history - Get conversation history
    DELETE /api/sessions/{session_id}       - Clear a session
    GET  /api/health       - Health check
"""

from __future__ import annotations

import os
import sys
import uuid
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


class HealthResponse(BaseModel):
    status: str
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

# In-memory session store: session_id -> ConversationSession
_sessions: Dict[str, Any] = {}

# Vector store + retriever (loaded on startup)
_vector_store: Any = None
_retriever: Any = None
_chunks: List[Any] = []
_llm: Any = None


def _get_or_create_session(session_id: Optional[str]) -> tuple:
    """Get existing session or create a new one. Returns (session_id, session)."""
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
            # Fallback: store history manually without real pipeline
            _sessions[session_id] = {"history": []}

    return session_id, _sessions[session_id]


# ---------------------------------------------------------------------------
# Startup logic
# ---------------------------------------------------------------------------

def initialize_vector_store() -> None:
    """Try to load existing vector store on startup."""
    global _vector_store, _retriever, _chunks

    settings = get_settings()
    chroma_dir = settings.vectordb_chroma_dir

    # Try to load existing Chroma DB
    if _Chroma is not None and chroma_dir.exists() and any(chroma_dir.iterdir()):
        try:
            if _get_embeddings is not None:
                embeddings = _get_embeddings()
            else:
                print("[api/app] WARNING: get_embeddings not available, skipping vector store load")
                return

            _vector_store = _Chroma(
                persist_directory=str(chroma_dir),
                embedding_function=embeddings,
                collection_name="documents",
            )

            if _get_retriever is not None:
                _retriever = _get_retriever(_vector_store, chunks=None)
            else:
                # Simple fallback retriever
                _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

            print(f"[api/app] Vector store loaded from {chroma_dir}")
            return
        except Exception as exc:
            print(f"[api/app] Failed to load existing Chroma: {exc}")
            traceback.print_exc()

    print("[api/app] No existing vector store found. Upload documents via /api/upload to create one.")


def _rebuild_vector_store_from_docs(docs: List[Any]) -> bool:
    """Rebuild vector store after new documents are uploaded."""
    global _vector_store, _retriever, _chunks

    if _build_vector_store is None:
        print("[api/app] build_vector_store not available")
        return False

    try:
        chunk_config = {"chunk_size": 800, "chunk_overlap": 200}
        _vector_store, _chunks = _build_vector_store(docs, chunk_config)

        if _get_retriever is not None:
            _retriever = _get_retriever(_vector_store, chunks=_chunks)
        elif hasattr(_vector_store, "as_retriever"):
            _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

        # Update all existing sessions with the new retriever
        for sid, session in _sessions.items():
            if hasattr(session, "_retriever"):
                session._retriever = _retriever

        print(f"[api/app] Vector store rebuilt: {len(_chunks)} chunks")
        return True
    except Exception as exc:
        print(f"[api/app] Failed to rebuild vector store: {exc}")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["RAG API"])


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """Ask a question to the RAG assistant."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    session_id, session = _get_or_create_session(request.session_id)

    # If we have a real ConversationSession
    if hasattr(session, "ask"):
        try:
            result = session.ask(question)

            answer = result.get("answer") or ""
            quality = result.get("quality_score") or 50
            route = result.get("route") or "auto"

            # Extract sources from context_docs or graded_docs
            sources_list = []
            docs = result.get("graded_docs") or result.get("context_docs") or []
            for doc in docs[:5]:  # Top 5 sources
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
            print(f"[api/ask] Pipeline error: {exc}")
            traceback.print_exc()
            # Fallback
            return AskResponse(
                answer=f"[ERROR] Pipeline error: {exc}",
                quality_score=0,
                route="human",
                sources=[],
                session_id=session_id,
            )
    else:
        # Fallback: no pipeline available, just echo
        session["history"].append({"role": "user", "content": question})
        fallback_answer = (
            f"[DEMO] Pipeline not available. "
            f"Question received: {question}"
        )
        session["history"].append({"role": "assistant", "content": fallback_answer})
        return AskResponse(
            answer=fallback_answer,
            quality_score=0,
            route="human",
            sources=[],
            session_id=session_id,
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a document (PDF/DOCX/TXT/MD) and ingest it into the vector store."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check extension
    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".html"}
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed))}",
        )

    # Save to temp file, then process
    upload_dir = PROJECT_ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    try:
        content = await file.read()
        file_path.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    # Try to load and ingest the document
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
            print(f"[api/upload] Ingestion error: {exc}")
            traceback.print_exc()
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
    """Get conversation history for a session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]

    if hasattr(session, "history"):
        # ConversationSession object
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
    """Clear a session and its history."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    if hasattr(session, "clear"):
        session.clear()

    del _sessions[session_id]
    return {"status": "ok", "message": f"Session {session_id} cleared"}


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        vector_store_loaded=_vector_store is not None,
        sessions_count=len(_sessions),
        pipeline_available=_run_qa_pipeline is not None,
    )

"""Tenant-aware vector store manager."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from vectordb import _base_manager

from config.settings import get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.documents import Document
else:
    Document = _base_manager.Document
Chroma = getattr(_base_manager, "Chroma", None)

_retriever_cache: dict[str, Any] = {}
_chunks_cache: dict[str, List[Document]] = {}
_store_cache: dict[str, Any] = {}
_cache_lock = Lock()


def get_embeddings(model_name: str | None = None) -> Any:
    return _base_manager.get_embeddings(model_name)


def _sanitize_tenant(tenant_id: str) -> str:
    prefix = getattr(get_settings(), "vectordb_collection_prefix", "rag_docs")
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", tenant_id or "default")
    if not sanitized:
        sanitized = "default"
    max_length = max(1, 63 - len(prefix) - 1)
    return sanitized[:max_length] or "default"


def _collection_name(tenant_id: str) -> str:
    prefix = getattr(get_settings(), "vectordb_collection_prefix", "rag_docs")
    return f"{prefix}_{_sanitize_tenant(tenant_id)}"


def add_contextual_headers(
    chunks: List[Document],
    full_documents: Sequence[Document],
    chunk_size: int,
) -> List[Document]:
    enriched = _base_manager.add_contextual_headers(
        list(chunks),
        llm=None,
        full_documents=list(full_documents),
    )
    prepared: List[Document] = []
    for chunk in enriched:
        page_content = chunk.page_content
        if len(page_content) > chunk_size:
            logger.warning(
                "Contextual header exceeded chunk_size for source %s; truncating chunk",
                (chunk.metadata or {}).get("source", "unknown"),
            )
            page_content = page_content[:chunk_size]
        prepared.append(
            Document(
                page_content=page_content,
                metadata={**(chunk.metadata or {}), "has_context_header": True},
            )
        )
    return prepared


def _ensure_document_metadata(docs: Sequence[Document]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    for index, doc in enumerate(docs):
        metadata = getattr(doc, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
            setattr(doc, "metadata", metadata)
        source = str(
            metadata.get("source")
            or metadata.get("file_name")
            or metadata.get("file_path")
            or f"document-{index}"
        )
        categories = metadata.get("categories")
        if not isinstance(categories, list) or not categories:
            categories = ["uncategorized"]
            metadata["categories"] = categories
        metadata.setdefault("primary_category", str(categories[0]))
        metadata.setdefault("doc_id", Path(source).name)
        metadata.setdefault("title", source)
        metadata.setdefault("last_updated", now_iso)


def build_vector_store(
    docs: Sequence[Document],
    chunk_config: Dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
    tenant_id: str = "default",
) -> tuple[Any, List[Document]]:
    if not docs:
        raise ValueError("Document list is empty.")

    tenant = tenant_id or "default"
    if embeddings is None:
        embeddings = get_embeddings()
    _ensure_document_metadata(docs)

    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    chunk_size = int(chunk_config.get("chunk_size", getattr(settings, "chunk_size", 800)))
    chunk_overlap = int(chunk_config.get("chunk_overlap", getattr(settings, "chunk_overlap", 200)))
    chunks = _base_manager.select_chunks(
        list(docs), embeddings, chunk_size, chunk_overlap,
        settings=settings, use_semantic=use_semantic_chunking,
    )

    if getattr(settings, "contextual_headers", False):
        chunks = add_contextual_headers(
            chunks,
            full_documents=docs,
            chunk_size=chunk_size,
        )

    if backend == "qdrant":
        build_qdrant = getattr(_base_manager, "_build_qdrant", None)
        if build_qdrant is None:
            raise ImportError("Qdrant backend is not available")
        store = build_qdrant(chunks, embeddings)
    else:
        if Chroma is None:
            raise ImportError("Chroma is not available")
        persist_directory = str(getattr(settings, "vectordb_chroma_dir"))
        collection_name = _collection_name(tenant)

        try:
            existing = Chroma(
                persist_directory=persist_directory,
                embedding_function=embeddings,
                collection_name=collection_name,
            )
            delete_collection = getattr(existing, "delete_collection", None)
            if callable(delete_collection):
                delete_collection()
        except Exception:
            pass

        store = Chroma.from_documents(
            documents=list(chunks),
            embedding=embeddings,
            persist_directory=persist_directory,
            collection_name=collection_name,
        )
        if hasattr(store, "persist"):
            store.persist()

    try:
        setattr(store, "_source_docs", list(docs))
        setattr(store, "_source_embeddings", embeddings)
    except Exception:
        pass

    with _cache_lock:
        _chunks_cache[tenant] = list(chunks)
        _store_cache[tenant] = store
        _retriever_cache.pop(tenant, None)

    return store, chunks


def retrieve(
    query: str,
    tenant_id: str = "default",
    categories: Sequence[str] | None = None,
    k: int | None = None,
) -> List[Document]:
    retriever = get_retriever(k=k, tenant_id=tenant_id)
    docs = list(retriever.get_relevant_documents(query))
    if not categories:
        return docs
    allowed = {str(item) for item in categories}
    return [
        doc
        for doc in docs
        if allowed.intersection(set((getattr(doc, "metadata", {}) or {}).get("categories") or []))
    ]


def get_retriever(
    vector_store: Any | None = None,
    chunks: List[Document] | None = None,
    k: int | None = None,
    tenant_id: str = "default",
    persist_directory: str | Path | None = None,
    embeddings: Any | None = None,
) -> Any:
    tenant = tenant_id or "default"

    with _cache_lock:
        cached = _retriever_cache.get(tenant)
        if cached is not None:
            return cached

    if embeddings is None:
        embeddings = get_embeddings()

    if vector_store is None:
        with _cache_lock:
            vector_store = _store_cache.get(tenant)

    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    if vector_store is None and backend != "qdrant":
        if Chroma is None:
            raise ImportError("Chroma is not available")
        vector_store = Chroma(
            persist_directory=str(persist_directory or getattr(settings, "vectordb_chroma_dir")),
            embedding_function=embeddings,
            collection_name=_collection_name(tenant),
        )

    if chunks is None:
        with _cache_lock:
            chunks = _chunks_cache.get(tenant)

    retriever = _base_manager.get_retriever(vector_store, chunks=chunks, k=k)

    with _cache_lock:
        if vector_store is not None:
            _store_cache[tenant] = vector_store
        if chunks is not None:
            _chunks_cache[tenant] = list(chunks)
        _retriever_cache[tenant] = retriever

    return retriever


def reset_retriever_cache(tenant_id: str | None = None) -> None:
    with _cache_lock:
        if tenant_id is None:
            _retriever_cache.clear()
            _chunks_cache.clear()
            _store_cache.clear()
        else:
            tenant = tenant_id or "default"
            _retriever_cache.pop(tenant, None)
            _chunks_cache.pop(tenant, None)
            _store_cache.pop(tenant, None)

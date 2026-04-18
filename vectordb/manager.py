"""Tenant-aware vector store manager."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Sequence

import manager as _base_manager

from config.settings import get_settings

logger = logging.getLogger(__name__)

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

    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    if backend == "qdrant":
        store, chunks = _base_manager.build_vector_store(
            docs,
            chunk_config,
            embeddings=embeddings,
            use_semantic_chunking=use_semantic_chunking,
        )
    else:
        if Chroma is None:
            raise ImportError("Chroma is not available")

        chunk_size = int(chunk_config.get("chunk_size", 800))
        chunk_overlap = int(chunk_config.get("chunk_overlap", 200))
        semantic_chunking_enabled = settings.semantic_chunking or use_semantic_chunking

        if semantic_chunking_enabled:
            chunks = _base_manager.semantic_split(
                list(docs),
                embeddings,
                min_chunk_size=chunk_overlap,
                max_chunk_size=chunk_size,
            )
        else:
            splitter = _base_manager._build_text_splitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks = splitter.split_documents(list(docs))

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

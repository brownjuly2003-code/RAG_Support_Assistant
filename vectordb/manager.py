"""Tenant-aware vector store manager."""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from config.settings import get_settings
from vectordb import _base_manager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.documents import Document
else:
    Document = _base_manager.Document
Chroma = getattr(_base_manager, "Chroma", None)

_retriever_cache: dict[str, Any] = {}
_chunks_cache: dict[str, list[Document]] = {}
_store_cache: dict[str, Any] = {}
_cache_lock = Lock()


def get_embeddings(model_name: str | None = None) -> Any:
    return _base_manager.get_embeddings(model_name)


def _get_chroma() -> Any:
    global Chroma
    if Chroma is not None:
        return Chroma
    load_chroma = getattr(_base_manager, "_load_chroma", None)
    if load_chroma is None:
        raise ImportError("Chroma is not available")
    Chroma = load_chroma()
    if Chroma is None:
        raise ImportError("Chroma is not available")
    return Chroma


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


def _factcard_collection_name(tenant_id: str) -> str:
    """Collection name for the fact-card lane (Track F): ``<prefix>_<tenant>_factcards``.

    Mirrors ``_collection_name`` but reserves room for the ``_factcards`` suffix so
    the whole name stays within Chroma's 63-character collection-name limit.
    """
    prefix = getattr(get_settings(), "vectordb_collection_prefix", "rag_docs")
    suffix = "factcards"
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", tenant_id or "default") or "default"
    # prefix + "_" + tenant + "_" + suffix must be <= 63 chars.
    max_tenant = max(1, 63 - len(prefix) - len(suffix) - 2)
    tenant = sanitized[:max_tenant] or "default"
    return f"{prefix}_{tenant}_{suffix}"


def add_contextual_headers(
    chunks: list[Document],
    full_documents: Sequence[Document],
    chunk_size: int,
) -> list[Document]:
    enriched = _base_manager.add_contextual_headers(
        list(chunks),
        llm=None,
        full_documents=list(full_documents),
    )
    prepared: list[Document] = []
    oversize = 0
    for chunk in enriched:
        # Тело чанка НЕ режем. Прежний `page_content[:chunk_size]` срезал хвост
        # тела на длину заголовка (~28-33% чанков корпуса) — прокси-A/B
        # 2026-06-04 показал, что это вырезает хвостовые строки field-таблиц и
        # превращает выигрыш contextual-header в регрессию (3/13 целевых кейсов;
        # docs/operations/2026-06-04-phase1-proxy-ab-contextual-header.md).
        # Превышение chunk_size ограничено длиной заголовка: оба пути
        # (_base_manager LLM и no-LLM fallback) клампят его до 200 символов.
        if len(chunk.page_content) > chunk_size:
            oversize += 1
        prepared.append(
            Document(
                page_content=chunk.page_content,
                metadata={**(chunk.metadata or {}), "has_context_header": True},
            )
        )
    if oversize:
        logger.info(
            "Contextual headers push %d/%d chunks past chunk_size=%d "
            "(body preserved; overflow bounded by the 200-char header clamp)",
            oversize,
            len(prepared),
            chunk_size,
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
    chunk_config: dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
    tenant_id: str = "default",
) -> tuple[Any, list[Document]]:
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

    # Ingestion-order stamp. Persisted with the collection so the BM25 corpus
    # and parent-expansion neighbour order can be rebuilt after a process
    # restart (see _restore_chunks_from_store) instead of silently degrading
    # to vector-only retrieval.
    for index, chunk in enumerate(chunks):
        metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
        metadata["chunk_index"] = index
        chunk.metadata = metadata

    if backend == "qdrant":
        build_qdrant = getattr(_base_manager, "_build_qdrant", None)
        if build_qdrant is None:
            raise ImportError("Qdrant backend is not available")
        store = build_qdrant(chunks, embeddings)
    else:
        chroma_cls = _get_chroma()
        persist_directory = str(settings.vectordb_chroma_dir)
        collection_name = _collection_name(tenant)

        try:
            existing = chroma_cls(
                persist_directory=persist_directory,
                embedding_function=embeddings,
                collection_name=collection_name,
            )
            delete_collection = getattr(existing, "delete_collection", None)
            if callable(delete_collection):
                delete_collection()
        except Exception:
            pass

        store = chroma_cls.from_documents(
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


def build_factcard_store(
    card_docs: Sequence[Document],
    embeddings: Any | None = None,
    tenant_id: str = "default",
) -> Any:
    """Build the fact-card vector collection (adaptive-retrieval Track F / F2).

    Each Document is one *whole* fact-card — no chunking, no contextual headers,
    no BM25/chunk_index stamp: the whole point of the lane is to return a complete
    enumeration that the main D2 reranker truncates (residual MISS
    ``customs-clearance-fields``). Cards live in a sibling
    ``<prefix>_<tenant>_factcards`` Chroma collection that F3
    (``get_factcard_documents``) reads, kept separate from the chunk collection so
    neither indexing path disturbs the other. Chroma backend only; the lane is
    eval-gated (Phase 5) and not wired into live retrieval yet.

    Mirrors ``build_vector_store``'s Chroma path (delete-then-rebuild,
    persist-if-supported) and returns the store. Keep metadata flat (scalar) —
    Chroma rejects list/dict metadata values.
    """
    if not card_docs:
        raise ValueError("Fact-card document list is empty.")
    tenant = tenant_id or "default"
    if embeddings is None:
        embeddings = get_embeddings()

    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    if backend == "qdrant":
        raise NotImplementedError(
            "Fact-card lane supports the Chroma backend only (Track F is eval-gated)."
        )

    chroma_cls = _get_chroma()
    persist_directory = str(settings.vectordb_chroma_dir)
    collection_name = _factcard_collection_name(tenant)

    try:
        existing = chroma_cls(
            persist_directory=persist_directory,
            embedding_function=embeddings,
            collection_name=collection_name,
        )
        delete_collection = getattr(existing, "delete_collection", None)
        if callable(delete_collection):
            delete_collection()
    except Exception:
        pass

    store = chroma_cls.from_documents(
        documents=list(card_docs),
        embedding=embeddings,
        persist_directory=persist_directory,
        collection_name=collection_name,
    )
    if hasattr(store, "persist"):
        store.persist()
    return store


def get_factcard_store(tenant_id: str = "default", embeddings: Any | None = None) -> Any | None:
    """Open the persisted fact-card collection for reading (Track F / F3).

    Returns the Chroma store for ``<prefix>_<tenant>_factcards`` (the collection
    built by ``build_factcard_store``), or ``None`` if the backend is unavailable.
    Opens the collection per call (no cache): the lane is eval-gated and off the
    hot path, so correctness/simplicity beats a cache-invalidation surface.
    """
    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    if backend == "qdrant":
        return None
    try:
        chroma_cls = _get_chroma()
    except ImportError:
        return None
    if embeddings is None:
        embeddings = get_embeddings()
    return chroma_cls(
        persist_directory=str(settings.vectordb_chroma_dir),
        embedding_function=embeddings,
        collection_name=_factcard_collection_name(tenant_id or "default"),
    )


def get_factcard_documents(
    query: str,
    tenant_id: str = "default",
    k: int = 3,
    embeddings: Any | None = None,
) -> list[Document]:
    """Return fact-cards relevant to ``query`` as whole Documents (Track F / F3).

    Reads the ``<prefix>_<tenant>_factcards`` collection built by
    ``build_factcard_store`` (F2). Returns ``[]`` if the query is blank, the
    collection is missing/empty, or the backend errors — so the F4 dispatcher can
    fall back to the hybrid lane instead of failing the request.
    """
    if not query or not query.strip():
        return []
    store = get_factcard_store(tenant_id, embeddings=embeddings)
    if store is None:
        return []
    search = getattr(store, "similarity_search", None)
    if not callable(search):
        return []
    try:
        results = search(query, k=k)
    except Exception:
        logger.warning("Fact-card search failed for tenant %s", tenant_id, exc_info=True)
        return []
    return list(results)


def _restore_chunks_from_store(vector_store: Any, tenant: str) -> list[Document] | None:
    """Rebuild the in-memory chunk list from a persisted Chroma collection.

    The BM25 corpus and the parent-expansion neighbour order only live in
    ``_chunks_cache`` (filled on upload). Without this restore, the first
    ``get_retriever`` call after a process restart builds a HybridRetriever
    with ``chunks=None`` — BM25 and parent-expansion silently turn off and the
    measured production stack is no longer what actually runs.
    """
    collection = getattr(vector_store, "_collection", None)
    if collection is None or not hasattr(collection, "get"):
        return None
    try:
        payload = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("Chunk restore failed for tenant %s: %s", tenant, exc)
        return None

    texts = (payload or {}).get("documents") or []
    metadatas = (payload or {}).get("metadatas") or []
    if not texts:
        return None

    chunks = [
        Document(page_content=str(text), metadata=dict(metadata or {}))
        for text, metadata in zip(texts, metadatas, strict=False)
    ]
    if all(isinstance((chunk.metadata or {}).get("chunk_index"), int) for chunk in chunks):
        chunks.sort(key=lambda chunk: int(chunk.metadata["chunk_index"]))
    else:
        # Legacy collection built before the chunk_index stamp. A stable sort
        # by source keeps each document's chunks contiguous in their returned
        # relative order — enough for parent-expansion's same-source window,
        # though the exact ingest order is not guaranteed.
        chunks.sort(key=lambda chunk: str((chunk.metadata or {}).get("source") or ""))
        logger.warning(
            "Tenant %s: restored %d chunks without chunk_index metadata "
            "(legacy collection) — neighbour order is approximate. "
            "Re-ingest to restore exact parent-expansion order.",
            tenant,
            len(chunks),
        )
    logger.info(
        "Restored %d chunks for tenant %s from the persisted collection "
        "(BM25 + parent-expansion re-enabled)",
        len(chunks),
        tenant,
    )
    return chunks


def _report_bm25_state(retriever: Any, tenant: str) -> None:
    """Expose whether the tenant retriever actually has a BM25 index."""
    bm25_active = getattr(retriever, "_bm25", None) is not None
    try:
        from monitoring.prometheus import set_retriever_bm25_enabled  # noqa: PLC0415

        set_retriever_bm25_enabled(tenant, bm25_active)
    except Exception:
        pass
    if bm25_active:
        return
    settings = get_settings()
    hybrid_expected = bool(getattr(settings, "hybrid_search", True)) and (
        _base_manager._normalize_retrieval_strategy(settings) != "vector"
    )
    if hybrid_expected:
        logger.warning(
            "Tenant %s: retriever built WITHOUT BM25 index while hybrid search "
            "is enabled — retrieval degraded to vector-only. "
            "Usually means the chunk cache is empty and could not be restored.",
            tenant,
        )


def retrieve(
    query: str,
    tenant_id: str = "default",
    categories: Sequence[str] | None = None,
    k: int | None = None,
) -> list[Document]:
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
    chunks: list[Document] | None = None,
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
        chroma_cls = _get_chroma()
        vector_store = chroma_cls(
            persist_directory=str(persist_directory or settings.vectordb_chroma_dir),
            embedding_function=embeddings,
            collection_name=_collection_name(tenant),
        )

    if chunks is None:
        with _cache_lock:
            chunks = _chunks_cache.get(tenant)

    if chunks is None and vector_store is not None:
        chunks = _restore_chunks_from_store(vector_store, tenant)

    retriever = _base_manager.get_retriever(vector_store, chunks=chunks, k=k)
    _report_bm25_state(retriever, tenant)

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

"""Tenant-aware vector store manager."""
from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from config.settings import get_settings
from utils.tenant_naming import physical_tenant_component
from vectordb import _base_manager
from vectordb.chroma_retention import (
    execute_chroma_retention,
    execute_guarded_chroma_retention,
)
from vectordb.index_manifest import (
    IndexVersionManifest,
    publish_active_collection,
    read_index_manifest,
)
from vectordb.index_operator import (
    IndexRetentionExecutionResult,
    rollback_index_version,
)
from vectordb.index_retention import record_retention_collection
from vectordb.index_staging import (
    IndexStagingValidationError,
    build_staged_collection,
    discard_staged_collection,
    validate_existing_collection,
    validate_staged_known_query,
)
from vectordb.tenant_lock import TenantIndexLockToken, tenant_index_lock

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.documents import Document
else:
    Document = _base_manager.Document
Chroma = getattr(_base_manager, "Chroma", None)

_retriever_cache: dict[str, Any] = {}
_chunks_cache: dict[str, list[Document]] = {}
_store_cache: dict[str, Any] = {}
_index_cache_keys: dict[str, tuple[str, str, int]] = {}
_cache_lock = Lock()


@dataclass(frozen=True)
class IndexPublicationReceipt:
    """Exact Chroma publish receipt captured during one successful build."""

    tenant_id: str
    active_collection: str
    previous_collection: str | None
    manifest_generation: int


@dataclass(frozen=True)
class BuildVectorStoreResult:
    """Opt-in build result with an optional race-free publication receipt."""

    store: Any
    chunks: list[Document]
    publication: IndexPublicationReceipt | None


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
    max_length = 63 - len(prefix) - 1
    return physical_tenant_component(tenant_id, max_length=max_length)


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
    # prefix + "_" + tenant + "_" + suffix must be <= 63 chars.
    max_tenant = 63 - len(prefix) - len(suffix) - 2
    tenant = physical_tenant_component(tenant_id, max_length=max_tenant)
    return f"{prefix}_{tenant}_{suffix}"


def _index_cache_key(
    chroma_directory: str | Path,
    manifest: IndexVersionManifest,
) -> tuple[str, str, int]:
    return (
        str(Path(chroma_directory).resolve()),
        manifest.active_collection,
        manifest.generation,
    )


def _resolve_active_index(
    tenant_id: str,
    chroma_directory: str | Path,
) -> tuple[str, tuple[str, str, int], bool]:
    directory = Path(chroma_directory).resolve()
    manifest = read_index_manifest(
        tenant_id,
        chroma_directory=directory,
    )
    if manifest is None:
        active_collection = _collection_name(tenant_id)
        return active_collection, (str(directory), active_collection, 0), False
    return (
        manifest.active_collection,
        _index_cache_key(directory, manifest),
        True,
    )


def resolve_response_cache_index_identity(
    tenant_id: str = "default",
    *,
    settings: Any | None = None,
) -> str | None:
    """Durable Chroma index identity for the LLM response cache.

    Returns a path-free token ``chroma:<collection>:gN`` (or
    ``chroma:<collection>:legacy:g0`` when no manifest exists). Non-Chroma
    backends and unreadable manifests return ``None`` so callers fail closed.
    """
    cfg = settings if settings is not None else get_settings()
    backend = str(getattr(cfg, "vector_backend", "chroma") or "chroma").strip().lower()
    if backend != "chroma":
        return None

    chroma_directory = getattr(cfg, "vectordb_chroma_dir", None)
    if chroma_directory is None:
        return None

    tenant = tenant_id or "default"
    try:
        active_collection, index_key, _manifest_present = _resolve_active_index(
            tenant,
            chroma_directory,
        )
    except Exception:
        return None

    generation = int(index_key[2])
    if generation <= 0:
        # Explicit legacy generation: upload invalidation still covers mutations.
        return f"chroma:{active_collection}:legacy:g0"
    return f"chroma:{active_collection}:g{generation}"


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


def _build_vector_store_result(
    docs: Sequence[Document],
    chunk_config: dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
    tenant_id: str = "default",
) -> BuildVectorStoreResult:
    """Shared build/publish path used by ordinary and opt-in entrypoints."""
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

    index_cache_key: tuple[str, str, int] | None = None
    published_manifest: IndexVersionManifest | None = None
    with tenant_index_lock(tenant) as lock_token:
        # Embedding is the dominant cost here and runs synchronously inside the
        # backend's from_documents() with no per-item callback. On CPU with a large
        # local model (~1.3s/chunk for BGE-M3) a few-thousand-chunk corpus takes tens
        # of minutes; without a start marker that is indistinguishable from a hang
        # (dogfood finding #1). Bracket the heavy call with start/elapsed logs.
        embed_started = time.time()
        embed_device = getattr(get_settings(), "rag_device", None)
        logger.info(
            "[index] embedding %d chunks into '%s' (backend=%s, device=%s) — "
            "this is the slow step on CPU",
            len(chunks),
            tenant,
            backend,
            embed_device or "auto",
        )

        if backend == "qdrant":
            build_qdrant = getattr(_base_manager, "_build_qdrant", None)
            if build_qdrant is None:
                raise ImportError("Qdrant backend is not available")
            store = build_qdrant(chunks, embeddings)
        else:
            chroma_cls = _get_chroma()
            persist_directory = str(settings.vectordb_chroma_dir)
            candidate = build_staged_collection(
                chunks,
                embeddings,
                tenant_id=tenant,
                lock_token=lock_token,
                chroma_cls=chroma_cls,
                chroma_directory=persist_directory,
            )
            try:
                validate_staged_known_query(
                    candidate,
                    chunks,
                    tenant_id=tenant,
                    lock_token=lock_token,
                )
                record_retention_collection(
                    tenant,
                    candidate.collection_name,
                    lock_token=lock_token,
                    chroma_directory=persist_directory,
                )
                published_manifest = publish_active_collection(
                    tenant,
                    candidate.collection_name,
                    lock_token=lock_token,
                    chroma_directory=persist_directory,
                )
            except BaseException:
                discard_staged_collection(
                    candidate,
                    tenant_id=tenant,
                    lock_token=lock_token,
                )
                raise
            # Retention runs only after successful publish and outside the
            # unpublished-candidate discard path. Failures propagate as-is.
            execute_chroma_retention(
                tenant,
                max_versions=settings.vectordb_retention_max_versions,
                lock_token=lock_token,
                chroma_directory=persist_directory,
            )
            store = candidate.store
            index_cache_key = _index_cache_key(persist_directory, published_manifest)

        logger.info(
            "[index] collection '%s' built: %d chunks in %.0fs",
            tenant,
            len(chunks),
            time.time() - embed_started,
        )

        try:
            setattr(store, "_source_docs", list(docs))
            setattr(store, "_source_embeddings", embeddings)
        except Exception:
            pass

        with _cache_lock:
            _chunks_cache[tenant] = list(chunks)
            _store_cache[tenant] = store
            _retriever_cache.pop(tenant, None)
            if index_cache_key is None:
                _index_cache_keys.pop(tenant, None)
            else:
                _index_cache_keys[tenant] = index_cache_key

    publication: IndexPublicationReceipt | None = None
    if published_manifest is not None:
        # Receipt is derived from the exact manifest returned by this build's
        # publish, and is only returned after retention/cache completion above.
        publication = IndexPublicationReceipt(
            tenant_id=tenant,
            active_collection=published_manifest.active_collection,
            previous_collection=published_manifest.previous_collection,
            manifest_generation=published_manifest.generation,
        )
    return BuildVectorStoreResult(
        store=store,
        chunks=chunks,
        publication=publication,
    )


def build_vector_store(
    docs: Sequence[Document],
    chunk_config: dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
    tenant_id: str = "default",
) -> tuple[Any, list[Document]]:
    """Build the tenant vector store and return the ordinary ``(store, chunks)`` tuple."""
    result = _build_vector_store_result(
        docs,
        chunk_config,
        embeddings=embeddings,
        use_semantic_chunking=use_semantic_chunking,
        tenant_id=tenant_id,
    )
    return result.store, result.chunks


def build_vector_store_with_publication(
    docs: Sequence[Document],
    chunk_config: dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
    tenant_id: str = "default",
) -> BuildVectorStoreResult:
    """Build once and return store/chunks plus the exact Chroma publish receipt.

    Performs the same single build/publish path as ``build_vector_store``. For
    Chroma, ``publication`` is the race-free receipt of the publish performed in
    this invocation. For Qdrant, ``publication`` is ``None``.
    """
    return _build_vector_store_result(
        docs,
        chunk_config,
        embeddings=embeddings,
        use_semantic_chunking=use_semantic_chunking,
        tenant_id=tenant_id,
    )


def rollback_vector_store(
    tenant_id: str = "default",
    embeddings: Any | None = None,
    *,
    expected_generation: int,
    target_collection: str,
) -> tuple[Any, list[Document]]:
    """Validate and activate an explicit previous Chroma collection.

    Requires the idempotent command key ``(expected_generation, target_collection)``
    and routes durable classification/mutation through
    ``rollback_index_version``. Target open/restore/validation runs under the
    operator-held tenant lock via ``target_validator`` so preconditions fail
    closed before embeddings/Chroma work and before any manifest mutation.
    """
    tenant = tenant_id or "default"
    settings = get_settings()
    if getattr(settings, "vector_backend", "chroma") == "qdrant":
        raise IndexStagingValidationError(
            "Rollback target collection is unavailable for the Qdrant backend"
        )
    chroma_directory = settings.vectordb_chroma_dir
    validated: dict[str, Any] = {}

    def _validate_target(
        collection_name: str,
        lock_token: TenantIndexLockToken,
    ) -> None:
        nonlocal embeddings
        if embeddings is None:
            embeddings = get_embeddings()
        chroma_cls = _get_chroma()
        try:
            store = chroma_cls(
                persist_directory=str(chroma_directory),
                embedding_function=embeddings,
                collection_name=collection_name,
                create_collection_if_not_exists=False,
            )
        except Exception as exc:
            raise IndexStagingValidationError(
                "Rollback target collection is unavailable"
            ) from exc

        chunks = _restore_chunks_from_store(store, tenant)
        if not chunks:
            raise IndexStagingValidationError(
                "Rollback target collection has no restorable chunks"
            )
        validate_existing_collection(
            collection_name,
            store,
            chunks,
            embeddings,
            tenant_id=tenant,
            lock_token=lock_token,
        )
        validated["store"] = store
        validated["chunks"] = list(chunks)

    result = rollback_index_version(
        tenant,
        expected_generation=expected_generation,
        target_collection=target_collection,
        chroma_directory=chroma_directory,
        target_validator=_validate_target,
    )

    store = validated["store"]
    chunks = validated["chunks"]
    with _cache_lock:
        _chunks_cache[tenant] = list(chunks)
        _store_cache[tenant] = store
        _retriever_cache.pop(tenant, None)
        _index_cache_keys[tenant] = (
            str(Path(chroma_directory).resolve()),
            result.active_collection,
            result.manifest_generation,
        )

    return store, chunks


def execute_vector_store_retention(
    tenant_id: str = "default",
    *,
    expected_generation: int,
    expected_candidates: tuple[str, ...],
) -> IndexRetentionExecutionResult:
    """Execute guarded retention for the configured Chroma vector store.

    Requires the idempotent command key
    ``(expected_generation, expected_candidates)`` and routes durable
    classification/mutation through ``execute_guarded_chroma_retention``.
    Callers cannot override the configured retention budget or chroma
    directory; Qdrant fails closed before any adapter work.
    """
    tenant = tenant_id or "default"
    settings = get_settings()
    if getattr(settings, "vector_backend", "chroma") == "qdrant":
        raise IndexStagingValidationError(
            "Vector store retention is unavailable for the Qdrant backend"
        )
    return execute_guarded_chroma_retention(
        tenant,
        max_versions=settings.vectordb_retention_max_versions,
        expected_generation=expected_generation,
        expected_candidates=expected_candidates,
        chroma_directory=settings.vectordb_chroma_dir,
    )


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

    with tenant_index_lock(tenant):
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
    settings = get_settings()
    backend = getattr(settings, "vector_backend", "chroma")
    active_collection: str | None = None
    manifest_present = False
    current_index_key: tuple[str, str, int] | None = None
    cached_store: Any | None = None
    cached_chunks: list[Document] | None = None

    if backend != "qdrant":
        chroma_directory = persist_directory or settings.vectordb_chroma_dir
        active_collection, current_index_key, manifest_present = _resolve_active_index(
            tenant,
            chroma_directory,
        )

    with _cache_lock:
        if current_index_key is not None:
            if _index_cache_keys.get(tenant) != current_index_key:
                _retriever_cache.pop(tenant, None)
                _chunks_cache.pop(tenant, None)
                _store_cache.pop(tenant, None)
                _index_cache_keys[tenant] = current_index_key
        elif tenant in _index_cache_keys:
            _retriever_cache.pop(tenant, None)
            _chunks_cache.pop(tenant, None)
            _store_cache.pop(tenant, None)
            _index_cache_keys.pop(tenant, None)

        cached = _retriever_cache.get(tenant)
        if cached is not None:
            return cached
        cached_store = _store_cache.get(tenant)
        cached_chunks = _chunks_cache.get(tenant)

    if embeddings is None:
        embeddings = get_embeddings()

    if manifest_present:
        vector_store = cached_store
        chunks = list(cached_chunks) if cached_chunks is not None else None
    else:
        if vector_store is None:
            vector_store = cached_store
        if chunks is None and cached_chunks is not None:
            chunks = list(cached_chunks)

    if vector_store is None and backend != "qdrant":
        assert active_collection is not None
        chroma_cls = _get_chroma()
        vector_store = chroma_cls(
            persist_directory=str(persist_directory or settings.vectordb_chroma_dir),
            embedding_function=embeddings,
            collection_name=active_collection,
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
            _index_cache_keys.clear()
        else:
            tenant = tenant_id or "default"
            _retriever_cache.pop(tenant, None)
            _chunks_cache.pop(tenant, None)
            _store_cache.pop(tenant, None)
            _index_cache_keys.pop(tenant, None)

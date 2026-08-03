"""Unpublished, versioned Chroma collection staging."""
from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import get_settings
from utils.tenant_naming import physical_tenant_component
from vectordb.tenant_lock import TenantIndexLockToken, require_tenant_index_lock

_COLLECTION_NAME_MAX_LENGTH = 63
_CANDIDATE_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_COLLECTION_NAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
_DIMENSION_PROBE_TEXT = "staged collection dimension validation"
_KNOWN_QUERY_MAX_CHARS = 512


class IndexStagingError(RuntimeError):
    """Base class for staged collection failures."""


class IndexStagingValidationError(IndexStagingError):
    """Raised when a staged collection cannot satisfy its local contract."""


class IndexStagingBuildError(IndexStagingError):
    """Raised when Chroma cannot build or persist the candidate collection."""


class IndexStagingCleanupError(IndexStagingError):
    """Raised when an unpublished candidate cannot be removed after failure."""


@dataclass(frozen=True)
class StagedIndexCandidate:
    collection_name: str
    chunk_count: int
    embedding_dimension: int
    store: Any


def staged_collection_name(
    tenant_id: str,
    *,
    candidate_id: str | None = None,
) -> str:
    """Return a tenant-safe candidate name outside the legacy ``prefix_`` lane."""
    if candidate_id is None:
        candidate_id = secrets.token_hex(8)
    if _CANDIDATE_ID_RE.fullmatch(candidate_id) is None:
        raise IndexStagingValidationError(
            "Index staging candidate ID must be 16 lowercase hexadecimal characters"
        )

    prefix = str(getattr(get_settings(), "vectordb_collection_prefix", "rag_docs"))
    name_prefix = f"{prefix}-v-"
    name_suffix = f"-{candidate_id}"
    max_tenant_length = (
        _COLLECTION_NAME_MAX_LENGTH - len(name_prefix) - len(name_suffix)
    )
    try:
        tenant = physical_tenant_component(
            tenant_id,
            max_length=max_tenant_length,
        )
    except ValueError as exc:
        raise IndexStagingValidationError(
            "Vector collection prefix leaves no safe room for a versioned tenant name"
        ) from exc
    collection_name = f"{name_prefix}{tenant}{name_suffix}"
    if (
        len(collection_name) > _COLLECTION_NAME_MAX_LENGTH
        or _COLLECTION_NAME_RE.fullmatch(collection_name) is None
    ):
        raise IndexStagingValidationError(
            "Versioned collection name violates the Chroma naming contract"
        )
    return collection_name


def _validate_candidate(
    store: Any,
    embeddings: Any,
    *,
    expected_count: int,
) -> tuple[int, int]:
    collection = getattr(store, "_collection", None)
    count = getattr(collection, "count", None)
    query = getattr(collection, "query", None)
    if not callable(count) or not callable(query):
        raise IndexStagingValidationError(
            "Staged collection does not expose count and dimension probes"
        )

    try:
        actual_count = int(count())
    except Exception as exc:
        raise IndexStagingValidationError(
            "Staged collection count validation failed"
        ) from exc
    if actual_count != expected_count:
        raise IndexStagingValidationError(
            f"Staged collection count mismatch: expected {expected_count}, got {actual_count}"
        )

    embed_query = getattr(embeddings, "embed_query", None)
    if not callable(embed_query):
        raise IndexStagingValidationError(
            "Embeddings do not expose a dimension probe"
        )
    try:
        probe_vector = list(embed_query(_DIMENSION_PROBE_TEXT))
    except Exception as exc:
        raise IndexStagingValidationError(
            "Staged collection embedding dimension probe failed"
        ) from exc
    if not probe_vector:
        raise IndexStagingValidationError(
            "Staged collection embedding dimension probe is empty"
        )
    try:
        query(query_embeddings=[probe_vector], n_results=1)
    except Exception as exc:
        raise IndexStagingValidationError(
            "Staged collection embedding dimension validation failed"
        ) from exc
    return actual_count, len(probe_vector)


def _cleanup_candidate(
    *,
    store: Any | None,
    chroma_cls: Any,
    embeddings: Any,
    persist_directory: str,
    collection_name: str,
) -> None:
    try:
        target = store
        if target is None:
            target = chroma_cls(
                persist_directory=persist_directory,
                embedding_function=embeddings,
                collection_name=collection_name,
            )
        delete_collection = getattr(target, "delete_collection", None)
        if not callable(delete_collection):
            raise RuntimeError("delete_collection is unavailable")
        delete_collection()
    except Exception as exc:
        raise IndexStagingCleanupError(
            "Unpublished staged collection cleanup failed"
        ) from exc


def validate_staged_known_query(
    candidate: StagedIndexCandidate,
    chunks: Sequence[Any],
    *,
    tenant_id: str,
    lock_token: TenantIndexLockToken | None,
) -> None:
    """Require one deterministic query to return content from the candidate."""
    require_tenant_index_lock(lock_token, tenant_id)
    documents = list(chunks)
    ordered_contents = [
        str(getattr(document, "page_content", ""))
        for document in documents
        if str(getattr(document, "page_content", "")).strip()
    ]
    expected_contents = set(ordered_contents)
    if not expected_contents:
        raise IndexStagingValidationError(
            "Staged collection known-query smoke has no non-empty content"
        )

    known_content = ordered_contents[0]
    similarity_search = getattr(candidate.store, "similarity_search", None)
    if not callable(similarity_search):
        raise IndexStagingValidationError(
            "Staged collection does not expose known-query search"
        )
    try:
        results = list(
            similarity_search(
                known_content[:_KNOWN_QUERY_MAX_CHARS],
                k=1,
            )
        )
    except Exception as exc:
        raise IndexStagingValidationError(
            "Staged collection known-query smoke failed"
        ) from exc
    if not results:
        raise IndexStagingValidationError(
            "Staged collection known-query smoke returned no results"
        )
    if not any(
        str(getattr(result, "page_content", "")) in expected_contents
        for result in results
    ):
        raise IndexStagingValidationError(
            "Staged collection known-query smoke returned unknown content"
        )


def validate_existing_collection(
    collection_name: str,
    store: Any,
    chunks: Sequence[Any],
    embeddings: Any,
    *,
    tenant_id: str,
    lock_token: TenantIndexLockToken | None,
) -> StagedIndexCandidate:
    """Validate a persisted collection before making it active."""
    require_tenant_index_lock(lock_token, tenant_id)
    documents = list(chunks)
    if not documents:
        raise IndexStagingValidationError(
            "Existing collection has no restorable chunks"
        )
    chunk_count, embedding_dimension = _validate_candidate(
        store,
        embeddings,
        expected_count=len(documents),
    )
    candidate = StagedIndexCandidate(
        collection_name=collection_name,
        chunk_count=chunk_count,
        embedding_dimension=embedding_dimension,
        store=store,
    )
    validate_staged_known_query(
        candidate,
        documents,
        tenant_id=tenant_id,
        lock_token=lock_token,
    )
    return candidate


def discard_staged_collection(
    candidate: StagedIndexCandidate,
    *,
    tenant_id: str,
    lock_token: TenantIndexLockToken | None,
) -> None:
    """Delete a candidate that has not been published as active."""
    require_tenant_index_lock(lock_token, tenant_id)
    _cleanup_candidate(
        store=candidate.store,
        chroma_cls=None,
        embeddings=None,
        persist_directory="",
        collection_name=candidate.collection_name,
    )


def build_staged_collection(
    chunks: Sequence[Any],
    embeddings: Any,
    *,
    tenant_id: str,
    lock_token: TenantIndexLockToken | None,
    chroma_cls: Any,
    chroma_directory: str | Path | None = None,
    candidate_id: str | None = None,
) -> StagedIndexCandidate:
    """Build and validate one unpublished collection under the tenant lock."""
    require_tenant_index_lock(lock_token, tenant_id)
    documents = list(chunks)
    if not documents:
        raise IndexStagingValidationError("Staged collection input is empty")

    collection_name = staged_collection_name(
        tenant_id,
        candidate_id=candidate_id,
    )
    persist_directory = str(
        chroma_directory
        if chroma_directory is not None
        else get_settings().vectordb_chroma_dir
    )
    store: Any | None = None
    try:
        store = chroma_cls.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=persist_directory,
            collection_name=collection_name,
        )
        persist = getattr(store, "persist", None)
        if callable(persist):
            persist()
        chunk_count, embedding_dimension = _validate_candidate(
            store,
            embeddings,
            expected_count=len(documents),
        )
    except BaseException as exc:
        try:
            _cleanup_candidate(
                store=store,
                chroma_cls=chroma_cls,
                embeddings=embeddings,
                persist_directory=persist_directory,
                collection_name=collection_name,
            )
        except IndexStagingCleanupError:
            raise
        if isinstance(exc, IndexStagingError):
            raise
        if isinstance(exc, Exception):
            raise IndexStagingBuildError(
                "Staged collection build failed"
            ) from exc
        raise

    return StagedIndexCandidate(
        collection_name=collection_name,
        chunk_count=chunk_count,
        embedding_dimension=embedding_dimension,
        store=store,
    )

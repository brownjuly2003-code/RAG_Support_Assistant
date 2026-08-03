"""Lock-consistent index retention previews and unwired rollback commands."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vectordb.index_manifest import (
    IndexManifestRollbackUnavailable,
    read_index_manifest,
    rollback_active_collection,
)
from vectordb.index_retention import (
    bounded_retention_candidates,
    read_retention_inventory,
)
from vectordb.tenant_lock import tenant_index_lock


class IndexRollbackCommandError(RuntimeError):
    """Base class for rollback command contract failures."""


class IndexRollbackValidationError(IndexRollbackCommandError):
    """Raised when rollback command inputs are invalid."""


class IndexRollbackConflict(IndexRollbackCommandError):
    """Raised when expected generation/target no longer match durable state."""


@dataclass(frozen=True)
class IndexRetentionPreview:
    tenant_id: str
    max_versions: int
    manifest_generation: int | None
    active_collection: str | None
    previous_collection: str | None
    inventory_collections: tuple[str, ...]
    deletion_candidates: tuple[str, ...]


@dataclass(frozen=True)
class IndexRollbackResult:
    tenant_id: str
    expected_generation: int
    target_collection: str
    applied: bool
    manifest_generation: int
    active_collection: str
    previous_collection: str | None


def preview_index_retention(
    tenant_id: str,
    *,
    max_versions: int,
    chroma_directory: str | Path | None = None,
) -> IndexRetentionPreview:
    """Preview bounded retention candidates under the tenant index lock."""
    normalized_tenant = str(tenant_id or "default")
    with tenant_index_lock(normalized_tenant):
        deletion_candidates = bounded_retention_candidates(
            normalized_tenant,
            max_versions=max_versions,
            chroma_directory=chroma_directory,
        )
        manifest = read_index_manifest(
            normalized_tenant,
            chroma_directory=chroma_directory,
        )
        inventory = read_retention_inventory(
            normalized_tenant,
            chroma_directory=chroma_directory,
        )

    inventory_collections = (
        tuple(entry.collection_name for entry in inventory.collections)
        if inventory is not None
        else ()
    )
    if manifest is None:
        return IndexRetentionPreview(
            tenant_id=normalized_tenant,
            max_versions=max_versions,
            manifest_generation=None,
            active_collection=None,
            previous_collection=None,
            inventory_collections=inventory_collections,
            deletion_candidates=deletion_candidates,
        )
    return IndexRetentionPreview(
        tenant_id=normalized_tenant,
        max_versions=max_versions,
        manifest_generation=manifest.generation,
        active_collection=manifest.active_collection,
        previous_collection=manifest.previous_collection,
        inventory_collections=inventory_collections,
        deletion_candidates=deletion_candidates,
    )


def rollback_index_version(
    tenant_id: str,
    *,
    expected_generation: int,
    target_collection: str,
    chroma_directory: str | Path | None = None,
) -> IndexRollbackResult:
    """Conditionally roll back the active index version under the tenant lock.

    This is an unwired idempotent command contract: it serializes on the tenant
    lock and requires an explicit expected generation plus target collection so
    retries cannot flip active/previous back and forth.
    """
    if (
        not isinstance(expected_generation, int)
        or isinstance(expected_generation, bool)
        or expected_generation < 1
    ):
        raise IndexRollbackValidationError(
            "expected_generation must be a positive int"
        )
    if not isinstance(target_collection, str) or not target_collection:
        raise IndexRollbackValidationError(
            "target_collection must be a non-empty str"
        )

    normalized_tenant = str(tenant_id or "default")
    with tenant_index_lock(normalized_tenant) as lock_token:
        current = read_index_manifest(
            normalized_tenant,
            chroma_directory=chroma_directory,
        )
        if current is None:
            raise IndexManifestRollbackUnavailable(
                "Index version manifest has no previous collection to restore"
            )

        # Exact retry: already applied for this command key.
        if (
            current.generation == expected_generation + 1
            and current.active_collection == target_collection
        ):
            return IndexRollbackResult(
                tenant_id=normalized_tenant,
                expected_generation=expected_generation,
                target_collection=target_collection,
                applied=False,
                manifest_generation=current.generation,
                active_collection=current.active_collection,
                previous_collection=current.previous_collection,
            )

        # First application only when generation and previous target match.
        if current.generation == expected_generation:
            if current.previous_collection is None:
                raise IndexManifestRollbackUnavailable(
                    "Index version manifest has no previous collection to restore"
                )
            if current.previous_collection != target_collection:
                raise IndexRollbackConflict(
                    "target_collection does not match manifest previous_collection"
                )
            rolled = rollback_active_collection(
                normalized_tenant,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )
            return IndexRollbackResult(
                tenant_id=normalized_tenant,
                expected_generation=expected_generation,
                target_collection=target_collection,
                applied=True,
                manifest_generation=rolled.generation,
                active_collection=rolled.active_collection,
                previous_collection=rolled.previous_collection,
            )

        raise IndexRollbackConflict(
            "expected_generation does not match durable manifest generation"
        )

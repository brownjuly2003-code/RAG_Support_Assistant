"""Read-only, lock-consistent index retention previews."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vectordb.index_manifest import read_index_manifest
from vectordb.index_retention import (
    bounded_retention_candidates,
    read_retention_inventory,
)
from vectordb.tenant_lock import tenant_index_lock


@dataclass(frozen=True)
class IndexRetentionPreview:
    tenant_id: str
    max_versions: int
    manifest_generation: int | None
    active_collection: str | None
    previous_collection: str | None
    inventory_collections: tuple[str, ...]
    deletion_candidates: tuple[str, ...]


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

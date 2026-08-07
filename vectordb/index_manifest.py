"""Durable active-version pointer for tenant Chroma collections."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import get_settings
from utils.tenant_naming import physical_tenant_component
from vectordb.index_lifecycle_faults import MANIFEST_PUBLISH, maybe_inject
from vectordb.tenant_lock import TenantIndexLockToken, require_tenant_index_lock

_SCHEMA_VERSION = 1
_COLLECTION_NAME_MAX_LENGTH = 63
_MANIFEST_DIRECTORY_NAME = "index-manifests"
_MANIFEST_KEYS = {
    "schema_version",
    "active_collection",
    "previous_collection",
    "generation",
    "updated_at",
}
_COLLECTION_NAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)


class IndexManifestError(RuntimeError):
    """Base class for active-version manifest failures."""


class IndexManifestCorrupt(IndexManifestError):
    """Raised when an existing manifest cannot be trusted."""


class IndexManifestValidationError(IndexManifestError):
    """Raised when a proposed manifest value violates the v1 contract."""


class IndexManifestRollbackUnavailable(IndexManifestError):
    """Raised when a manifest has no previous collection to restore."""


@dataclass(frozen=True)
class IndexVersionManifest:
    schema_version: int
    active_collection: str
    previous_collection: str | None
    generation: int
    updated_at: str


def _chroma_directory(chroma_directory: str | Path | None) -> Path:
    if chroma_directory is not None:
        return Path(chroma_directory)
    return Path(get_settings().vectordb_chroma_dir)


def index_manifest_path(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> Path:
    """Return the collision-resistant manifest path beside the Chroma directory."""
    manifest_root = _chroma_directory(chroma_directory).parent / _MANIFEST_DIRECTORY_NAME
    component = physical_tenant_component(tenant_id, max_length=63)
    path = manifest_root / f"{component}.json"
    try:
        path.resolve().relative_to(manifest_root.resolve())
    except ValueError as exc:  # pragma: no cover - physical component is path-safe
        raise IndexManifestValidationError(
            "Index version manifest path escapes its registry directory"
        ) from exc
    return path


def _legacy_collection_name(tenant_id: str) -> str:
    prefix = str(getattr(get_settings(), "vectordb_collection_prefix", "rag_docs"))
    max_tenant_length = _COLLECTION_NAME_MAX_LENGTH - len(prefix) - 1
    tenant = physical_tenant_component(tenant_id, max_length=max_tenant_length)
    return f"{prefix}_{tenant}"


def _validate_collection_name(value: Any) -> str:
    if not isinstance(value, str):
        raise IndexManifestValidationError("Collection name must be a string")
    if not 1 <= len(value) <= _COLLECTION_NAME_MAX_LENGTH:
        raise IndexManifestValidationError(
            "Collection name must be between 1 and 63 characters"
        )
    if _COLLECTION_NAME_RE.fullmatch(value) is None:
        raise IndexManifestValidationError("Collection name contains unsafe characters")
    return value


def _parse_updated_at(value: Any) -> str:
    if not isinstance(value, str):
        raise IndexManifestValidationError("updated_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise IndexManifestValidationError(
            "updated_at must be an ISO-8601 string"
        ) from exc
    if parsed.tzinfo is None:
        raise IndexManifestValidationError("updated_at must include a timezone")
    return value


def _parse_manifest(payload: Any) -> IndexVersionManifest:
    try:
        if not isinstance(payload, dict) or set(payload) != _MANIFEST_KEYS:
            raise IndexManifestValidationError(
                "Index version manifest has an unexpected schema"
            )
        schema_version = payload["schema_version"]
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != _SCHEMA_VERSION
        ):
            raise IndexManifestValidationError(
                "Index version manifest schema_version is unsupported"
            )
        generation = payload["generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise IndexManifestValidationError(
                "Index version manifest generation must be a positive integer"
            )
        previous = payload["previous_collection"]
        if previous is not None:
            previous = _validate_collection_name(previous)
        return IndexVersionManifest(
            schema_version=schema_version,
            active_collection=_validate_collection_name(payload["active_collection"]),
            previous_collection=previous,
            generation=generation,
            updated_at=_parse_updated_at(payload["updated_at"]),
        )
    except (KeyError, IndexManifestValidationError) as exc:
        raise IndexManifestCorrupt("Index version manifest is invalid") from exc


def read_index_manifest(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> IndexVersionManifest | None:
    """Read a trusted manifest, returning ``None`` only when it is absent."""
    path = index_manifest_path(tenant_id, chroma_directory=chroma_directory)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeError as exc:
        raise IndexManifestCorrupt("Index version manifest is invalid") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IndexManifestCorrupt("Index version manifest is invalid") from exc
    return _parse_manifest(payload)


def resolve_active_collection(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> str:
    """Resolve the active collection, preserving legacy indexes when absent."""
    manifest = read_index_manifest(tenant_id, chroma_directory=chroma_directory)
    if manifest is None:
        return _legacy_collection_name(tenant_id)
    return manifest.active_collection


def _manifest_payload(manifest: IndexVersionManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "active_collection": manifest.active_collection,
        "previous_collection": manifest.previous_collection,
        "generation": manifest.generation,
        "updated_at": manifest.updated_at,
    }


def publish_active_collection(
    tenant_id: str,
    active_collection: str,
    *,
    lock_token: TenantIndexLockToken | None,
    chroma_directory: str | Path | None = None,
) -> IndexVersionManifest:
    """Atomically publish ``active_collection`` while a tenant lock is held."""
    require_tenant_index_lock(lock_token, tenant_id)
    active_collection = _validate_collection_name(active_collection)
    current = read_index_manifest(tenant_id, chroma_directory=chroma_directory)
    manifest = IndexVersionManifest(
        schema_version=_SCHEMA_VERSION,
        active_collection=active_collection,
        previous_collection=current.active_collection if current is not None else None,
        generation=current.generation + 1 if current is not None else 1,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    path = index_manifest_path(tenant_id, chroma_directory=chroma_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        _manifest_payload(manifest),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        # Inject only at the durable commit boundary so a failed publish cannot
        # switch the active collection or leave a half-applied manifest.
        maybe_inject(MANIFEST_PUBLISH)
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return manifest


def rollback_active_collection(
    tenant_id: str,
    *,
    lock_token: TenantIndexLockToken | None,
    chroma_directory: str | Path | None = None,
) -> IndexVersionManifest:
    """Atomically swap active and previous collections under the tenant lock."""
    require_tenant_index_lock(lock_token, tenant_id)
    current = read_index_manifest(tenant_id, chroma_directory=chroma_directory)
    if current is None or current.previous_collection is None:
        raise IndexManifestRollbackUnavailable(
            "Index version manifest has no previous collection to restore"
        )
    return publish_active_collection(
        tenant_id,
        current.previous_collection,
        lock_token=lock_token,
        chroma_directory=chroma_directory,
    )

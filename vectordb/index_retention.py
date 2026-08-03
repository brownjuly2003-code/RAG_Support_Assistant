"""Durable ordering metadata for tenant index retention."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import get_settings
from utils.tenant_naming import physical_tenant_component
from vectordb.index_manifest import read_index_manifest
from vectordb.index_staging import IndexStagingValidationError, staged_collection_name
from vectordb.tenant_lock import TenantIndexLockToken, require_tenant_index_lock

_SCHEMA_VERSION = 1
_RETENTION_DIRECTORY_NAME = "index-retention"
_TENANT_KEY_DOMAIN = b"rag-support:index-retention:v1\0"
_INVENTORY_KEYS = {
    "schema_version",
    "tenant_key",
    "collections",
    "updated_at",
}
_COLLECTION_KEYS = {
    "collection_name",
    "sequence",
    "recorded_at",
}


class IndexRetentionError(RuntimeError):
    """Base class for durable index-retention metadata failures."""


class IndexRetentionCorrupt(IndexRetentionError):
    """Raised when existing retention metadata cannot be trusted."""


class IndexRetentionValidationError(IndexRetentionError):
    """Raised when proposed retention metadata violates its contract."""


@dataclass(frozen=True)
class RetentionCollectionMetadata:
    collection_name: str
    sequence: int
    recorded_at: str


@dataclass(frozen=True)
class IndexRetentionInventory:
    schema_version: int
    tenant_key: str
    collections: tuple[RetentionCollectionMetadata, ...]
    updated_at: str


def _chroma_directory(chroma_directory: str | Path | None) -> Path:
    if chroma_directory is not None:
        return Path(chroma_directory)
    return Path(get_settings().vectordb_chroma_dir)


def index_retention_path(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> Path:
    """Return the tenant-safe inventory path beside the Chroma directory."""
    inventory_root = (
        _chroma_directory(chroma_directory).parent / _RETENTION_DIRECTORY_NAME
    )
    component = physical_tenant_component(tenant_id, max_length=63)
    path = inventory_root / f"{component}.json"
    try:
        path.resolve().relative_to(inventory_root.resolve())
    except ValueError as exc:  # pragma: no cover - physical component is path-safe
        raise IndexRetentionValidationError(
            "Index retention inventory path escapes its registry directory"
        ) from exc
    return path


def _tenant_key(tenant_id: str) -> str:
    canonical = str(tenant_id or "default").encode("utf-8")
    return hashlib.sha256(_TENANT_KEY_DOMAIN + canonical).hexdigest()


def _parse_timestamp(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise IndexRetentionValidationError(
            f"Index retention {field_name} must be an ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise IndexRetentionValidationError(
            f"Index retention {field_name} must be an ISO-8601 string"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IndexRetentionValidationError(
            f"Index retention {field_name} must include a timezone"
        )
    return value


def _validate_versioned_collection_name(tenant_id: str, value: Any) -> str:
    if not isinstance(value, str):
        raise IndexRetentionValidationError(
            "Retention collection must be a versioned collection for this tenant"
        )
    candidate_id = value[-16:]
    try:
        expected = staged_collection_name(tenant_id, candidate_id=candidate_id)
    except (IndexStagingValidationError, ValueError) as exc:
        raise IndexRetentionValidationError(
            "Retention collection must be a versioned collection for this tenant"
        ) from exc
    if value != expected:
        raise IndexRetentionValidationError(
            "Retention collection must be a versioned collection for this tenant"
        )
    return value


def _parse_inventory(payload: Any, *, tenant_id: str) -> IndexRetentionInventory:
    try:
        if not isinstance(payload, dict) or set(payload) != _INVENTORY_KEYS:
            raise IndexRetentionValidationError(
                "Index retention inventory has an unexpected schema"
            )
        schema_version = payload["schema_version"]
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != _SCHEMA_VERSION
        ):
            raise IndexRetentionValidationError(
                "Index retention inventory schema_version is unsupported"
            )
        tenant_key = payload["tenant_key"]
        if not isinstance(tenant_key, str) or tenant_key != _tenant_key(tenant_id):
            raise IndexRetentionValidationError(
                "Index retention inventory tenant binding is invalid"
            )
        collection_payloads = payload["collections"]
        if not isinstance(collection_payloads, list):
            raise IndexRetentionValidationError(
                "Index retention inventory collections must be a list"
            )

        collections: list[RetentionCollectionMetadata] = []
        seen_names: set[str] = set()
        for expected_sequence, collection_payload in enumerate(
            collection_payloads,
            start=1,
        ):
            if (
                not isinstance(collection_payload, dict)
                or set(collection_payload) != _COLLECTION_KEYS
            ):
                raise IndexRetentionValidationError(
                    "Index retention collection has an unexpected schema"
                )
            sequence = collection_payload["sequence"]
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != expected_sequence
            ):
                raise IndexRetentionValidationError(
                    "Index retention collection sequence is invalid"
                )
            collection_name = _validate_versioned_collection_name(
                tenant_id,
                collection_payload["collection_name"],
            )
            if collection_name in seen_names:
                raise IndexRetentionValidationError(
                    "Index retention collection names must be unique"
                )
            seen_names.add(collection_name)
            collections.append(
                RetentionCollectionMetadata(
                    collection_name=collection_name,
                    sequence=sequence,
                    recorded_at=_parse_timestamp(
                        collection_payload["recorded_at"],
                        field_name="recorded_at",
                    ),
                )
            )

        updated_at = _parse_timestamp(payload["updated_at"], field_name="updated_at")
        if collections and updated_at != collections[-1].recorded_at:
            raise IndexRetentionValidationError(
                "Index retention inventory updated_at does not match its latest entry"
            )
        return IndexRetentionInventory(
            schema_version=schema_version,
            tenant_key=tenant_key,
            collections=tuple(collections),
            updated_at=updated_at,
        )
    except (KeyError, IndexRetentionValidationError) as exc:
        raise IndexRetentionCorrupt(str(exc)) from exc


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise IndexRetentionValidationError(
                "Index retention inventory contains duplicate keys"
            )
        payload[key] = value
    return payload


def read_retention_inventory(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> IndexRetentionInventory | None:
    """Read trusted retention metadata, returning ``None`` only when absent."""
    path = index_retention_path(tenant_id, chroma_directory=chroma_directory)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeError as exc:
        raise IndexRetentionCorrupt(
            "Index retention inventory encoding is invalid"
        ) from exc
    try:
        payload = json.loads(raw, object_pairs_hook=_strict_json_object)
    except json.JSONDecodeError as exc:
        raise IndexRetentionCorrupt(
            "Index retention inventory JSON is invalid"
        ) from exc
    except IndexRetentionValidationError as exc:
        raise IndexRetentionCorrupt(str(exc)) from exc
    return _parse_inventory(payload, tenant_id=tenant_id)


def _inventory_payload(inventory: IndexRetentionInventory) -> dict[str, Any]:
    return {
        "schema_version": inventory.schema_version,
        "tenant_key": inventory.tenant_key,
        "collections": [
            {
                "collection_name": entry.collection_name,
                "sequence": entry.sequence,
                "recorded_at": entry.recorded_at,
            }
            for entry in inventory.collections
        ],
        "updated_at": inventory.updated_at,
    }


def _write_inventory(
    tenant_id: str,
    inventory: IndexRetentionInventory,
    *,
    chroma_directory: str | Path | None,
) -> None:
    path = index_retention_path(tenant_id, chroma_directory=chroma_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        _inventory_payload(inventory),
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
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def record_retention_collection(
    tenant_id: str,
    collection_name: str,
    *,
    lock_token: TenantIndexLockToken | None,
    chroma_directory: str | Path | None = None,
) -> IndexRetentionInventory:
    """Append trusted ordering metadata while the tenant lock is held."""
    require_tenant_index_lock(lock_token, tenant_id)
    collection_name = _validate_versioned_collection_name(tenant_id, collection_name)
    current = read_retention_inventory(
        tenant_id,
        chroma_directory=chroma_directory,
    )
    if current is not None and any(
        entry.collection_name == collection_name for entry in current.collections
    ):
        return current

    recorded_at = datetime.now(timezone.utc).isoformat()
    current_collections = current.collections if current is not None else ()
    inventory = IndexRetentionInventory(
        schema_version=_SCHEMA_VERSION,
        tenant_key=_tenant_key(tenant_id),
        collections=(
            *current_collections,
            RetentionCollectionMetadata(
                collection_name=collection_name,
                sequence=len(current_collections) + 1,
                recorded_at=recorded_at,
            ),
        ),
        updated_at=recorded_at,
    )
    _write_inventory(
        tenant_id,
        inventory,
        chroma_directory=chroma_directory,
    )
    return inventory


def trusted_retention_candidates(
    tenant_id: str,
    *,
    chroma_directory: str | Path | None = None,
) -> tuple[str, ...]:
    """Return oldest-first trusted candidates without touching Chroma."""
    inventory = read_retention_inventory(
        tenant_id,
        chroma_directory=chroma_directory,
    )
    if inventory is None:
        return ()
    manifest = read_index_manifest(
        tenant_id,
        chroma_directory=chroma_directory,
    )
    if manifest is None:
        return ()
    protected = {manifest.active_collection, manifest.previous_collection}
    return tuple(
        entry.collection_name
        for entry in inventory.collections
        if entry.collection_name not in protected
    )


def bounded_retention_candidates(
    tenant_id: str,
    *,
    max_versions: int,
    chroma_directory: str | Path | None = None,
) -> tuple[str, ...]:
    """Return oldest-first trusted candidates outside a safe version budget."""
    if (
        isinstance(max_versions, bool)
        or not isinstance(max_versions, int)
        or max_versions < 2
    ):
        raise IndexRetentionValidationError(
            "Index retention max_versions must be an integer >= 2"
        )

    inventory = read_retention_inventory(
        tenant_id,
        chroma_directory=chroma_directory,
    )
    if inventory is None:
        return ()
    manifest = read_index_manifest(
        tenant_id,
        chroma_directory=chroma_directory,
    )
    if manifest is None:
        return ()

    protected = {manifest.active_collection}
    if manifest.previous_collection is not None:
        protected.add(manifest.previous_collection)
    unprotected = tuple(
        entry.collection_name
        for entry in inventory.collections
        if entry.collection_name not in protected
    )
    keep_slots = max(max_versions - len(protected), 0)
    candidate_count = max(len(unprotected) - keep_slots, 0)
    return unprotected[:candidate_count]

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _operator_module() -> ModuleType:
    return importlib.import_module("vectordb.index_operator")


def _versioned_name(tenant_id: str, ordinal: int) -> str:
    from vectordb.index_staging import staged_collection_name

    return staged_collection_name(
        tenant_id,
        candidate_id=f"{ordinal:016x}",
    )


@contextmanager
def _held_tenant_lock(
    monkeypatch: pytest.MonkeyPatch,
    tenant_id: str,
) -> Iterator[Any]:
    from vectordb import tenant_lock

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    with tenant_lock.tenant_index_lock(tenant_id) as lock_token:
        yield lock_token


def _seed_four_versions(
    *,
    tenant_id: str,
    chroma_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, ...]:
    from vectordb.index_manifest import publish_active_collection
    from vectordb.index_retention import record_retention_collection

    versions = tuple(_versioned_name(tenant_id, ordinal) for ordinal in range(1, 5))
    with _held_tenant_lock(monkeypatch, tenant_id) as lock_token:
        for collection_name in versions:
            record_retention_collection(
                tenant_id,
                collection_name,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )
            publish_active_collection(
                tenant_id,
                collection_name,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )
    return versions


def test_preview_returns_lock_consistent_snapshot_for_seeded_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = _seed_four_versions(
        tenant_id="acme",
        chroma_directory=chroma_directory,
        monkeypatch=monkeypatch,
    )

    # Keep the real lock path stubbed so preview does not need Postgres.
    with _held_tenant_lock(monkeypatch, "acme"):
        pass

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    preview = operator.preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )

    assert preview.tenant_id == "acme"
    assert preview.max_versions == 2
    assert preview.manifest_generation == 4
    assert preview.active_collection == versions[-1]
    assert preview.previous_collection == versions[-2]
    assert preview.inventory_collections == versions
    # active + previous protected; budget 2 leaves no unprotected keep slots
    assert preview.deletion_candidates == versions[:2]


def test_preview_does_not_mutate_manifest_or_inventory_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock
    from vectordb.index_manifest import index_manifest_path
    from vectordb.index_retention import index_retention_path

    chroma_directory = tmp_path / "vectordb" / "chroma"
    _seed_four_versions(
        tenant_id="acme",
        chroma_directory=chroma_directory,
        monkeypatch=monkeypatch,
    )

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    inventory_path = index_retention_path("acme", chroma_directory=chroma_directory)
    before_manifest = manifest_path.read_bytes()
    before_inventory = inventory_path.read_bytes()

    operator.preview_index_retention(
        "acme",
        max_versions=3,
        chroma_directory=chroma_directory,
    )

    assert manifest_path.read_bytes() == before_manifest
    assert inventory_path.read_bytes() == before_inventory


def test_preview_reads_all_state_while_tenant_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()

    lock_held = False
    held_during: dict[str, bool] = {}

    @contextmanager
    def _fake_lock(tenant_id: str) -> Iterator[object]:
        nonlocal lock_held
        assert tenant_id == "acme"
        lock_held = True
        try:
            yield object()
        finally:
            lock_held = False

    def _candidates(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        held_during["candidates"] = lock_held
        return ("old_collection",)

    def _manifest(*_args: Any, **_kwargs: Any) -> None:
        held_during["manifest"] = lock_held
        return None

    def _inventory(*_args: Any, **_kwargs: Any) -> None:
        held_during["inventory"] = lock_held
        return None

    monkeypatch.setattr(operator, "tenant_index_lock", _fake_lock)
    monkeypatch.setattr(operator, "bounded_retention_candidates", _candidates)
    monkeypatch.setattr(operator, "read_index_manifest", _manifest)
    monkeypatch.setattr(operator, "read_retention_inventory", _inventory)

    preview = operator.preview_index_retention("acme", max_versions=2)

    assert held_during == {
        "candidates": True,
        "manifest": True,
        "inventory": True,
    }
    assert preview.deletion_candidates == ("old_collection",)
    assert preview.manifest_generation is None
    assert preview.inventory_collections == ()


def test_preview_missing_manifest_and_inventory_returns_empty_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    preview = operator.preview_index_retention(
        "",
        max_versions=2,
        chroma_directory=tmp_path / "vectordb" / "chroma",
    )

    assert preview.tenant_id == "default"
    assert preview.max_versions == 2
    assert preview.manifest_generation is None
    assert preview.active_collection is None
    assert preview.previous_collection is None
    assert preview.inventory_collections == ()
    assert preview.deletion_candidates == ()


@pytest.mark.parametrize("max_versions", [True, 1, 2.0])
def test_preview_propagates_invalid_budget_without_mutating_files(
    max_versions: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock
    from vectordb.index_manifest import index_manifest_path
    from vectordb.index_retention import (
        IndexRetentionValidationError,
        index_retention_path,
    )

    chroma_directory = tmp_path / "vectordb" / "chroma"
    _seed_four_versions(
        tenant_id="acme",
        chroma_directory=chroma_directory,
        monkeypatch=monkeypatch,
    )

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    inventory_path = index_retention_path("acme", chroma_directory=chroma_directory)
    before_manifest = manifest_path.read_bytes()
    before_inventory = inventory_path.read_bytes()

    with pytest.raises(IndexRetentionValidationError, match="max_versions"):
        operator.preview_index_retention(
            "acme",
            max_versions=max_versions,
            chroma_directory=chroma_directory,
        )

    assert manifest_path.read_bytes() == before_manifest
    assert inventory_path.read_bytes() == before_inventory


def test_preview_propagates_corrupt_inventory_without_mutating_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock
    from vectordb.index_retention import IndexRetentionCorrupt, index_retention_path

    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = index_retention_path("acme", chroma_directory=chroma_directory)
    path.parent.mkdir(parents=True)
    raw = b'{"schema_version": 1, "collections": '
    path.write_bytes(raw)

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    with pytest.raises(IndexRetentionCorrupt, match="inventory"):
        operator.preview_index_retention(
            "acme",
            max_versions=2,
            chroma_directory=chroma_directory,
        )

    assert path.read_bytes() == raw


def test_preview_propagates_corrupt_manifest_without_mutating_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator_module()
    from vectordb import tenant_lock
    from vectordb.index_manifest import IndexManifestCorrupt, index_manifest_path
    from vectordb.index_retention import index_retention_path

    chroma_directory = tmp_path / "vectordb" / "chroma"
    # Seed a valid inventory so the failure comes from the corrupt manifest path.
    from vectordb.index_retention import record_retention_collection

    version = _versioned_name("acme", 1)
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        record_retention_collection(
            "acme",
            version,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    inventory_path = index_retention_path("acme", chroma_directory=chroma_directory)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    raw_manifest = b'{"schema_version": 1, "active_collection": '
    manifest_path.write_bytes(raw_manifest)
    before_inventory = inventory_path.read_bytes()

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    with pytest.raises(IndexManifestCorrupt, match="manifest"):
        operator.preview_index_retention(
            "acme",
            max_versions=2,
            chroma_directory=chroma_directory,
        )

    assert manifest_path.read_bytes() == raw_manifest
    assert inventory_path.read_bytes() == before_inventory


def test_operator_module_has_no_chroma_or_runtime_wiring() -> None:
    operator = _operator_module()
    source = Path(inspect.getfile(operator)).read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden_substrings = (
        "chromadb",
        "chroma.client",
        "persistentclient",
        "delete_collection",
        "list_collections",
        "get_collection",
        "get_or_create_collection",
        "apirouter",
        "fastapi",
        "publish_active_collection",
        "rollback_active_collection",
        "apply_bounded_retention",
        "execute_retention",
        "audit_log",
        "record_audit",
    )
    for fragment in forbidden_substrings:
        assert fragment not in lowered, f"unexpected wiring fragment: {fragment}"

    assert "tenant_index_lock" in source
    assert "bounded_retention_candidates" in source
    assert "read_index_manifest" in source
    assert "read_retention_inventory" in source
    assert "IndexRetentionPreview" in source
    assert "preview_index_retention" in source

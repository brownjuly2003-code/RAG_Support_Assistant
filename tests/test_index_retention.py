from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _retention_module() -> ModuleType:
    return importlib.import_module("vectordb.index_retention")


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


def test_trusted_candidates_are_ordered_and_protect_manifest_pointers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    from vectordb.index_manifest import publish_active_collection

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 4))

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        for collection_name in versions:
            retention.record_retention_collection(
                "acme",
                collection_name,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )
            publish_active_collection(
                "acme",
                collection_name,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    inventory = retention.read_retention_inventory(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == list(versions)
    assert [entry.sequence for entry in inventory.collections] == [1, 2, 3]
    assert all(
        datetime.fromisoformat(entry.recorded_at).tzinfo is not None
        for entry in inventory.collections
    )
    assert retention.trusted_retention_candidates(
        "acme",
        chroma_directory=chroma_directory,
    ) == (versions[0],)


def test_legacy_foreign_malformed_and_unrecorded_collections_are_never_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    from vectordb.index_manifest import publish_active_collection

    chroma_directory = tmp_path / "vectordb" / "chroma"
    recorded = _versioned_name("acme", 1)
    unrecorded = _versioned_name("acme", 2)
    active = _versioned_name("acme", 3)

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        retention.record_retention_collection(
            "acme",
            recorded,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        for invalid_name in (
            "rag_docs_acme",
            "malformed collection name",
            _versioned_name("beta", 4),
        ):
            with pytest.raises(
                retention.IndexRetentionValidationError,
                match="versioned",
            ):
                retention.record_retention_collection(
                    "acme",
                    invalid_name,
                    lock_token=lock_token,
                    chroma_directory=chroma_directory,
                )
        publish_active_collection(
            "acme",
            unrecorded,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        publish_active_collection(
            "acme",
            active,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    candidates = retention.trusted_retention_candidates(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert candidates == (recorded,)
    assert unrecorded not in candidates
    assert active not in candidates


def test_inventory_without_a_version_manifest_has_no_retention_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        retention.record_retention_collection(
            "acme",
            _versioned_name("acme", 1),
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    assert retention.trusted_retention_candidates(
        "acme",
        chroma_directory=chroma_directory,
    ) == ()


def test_inventory_writer_requires_a_current_matching_tenant_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    from vectordb import tenant_lock

    chroma_directory = tmp_path / "vectordb" / "chroma"
    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        retention.record_retention_collection(
            "acme",
            _versioned_name("acme", 1),
            lock_token=None,
            chroma_directory=chroma_directory,
        )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="tenant"):
            retention.record_retention_collection(
                "beta",
                _versioned_name("beta", 1),
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        retention.record_retention_collection(
            "acme",
            _versioned_name("acme", 1),
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version": 1, "collections": ',
        json.dumps({"schema_version": 1, "collections": []}).encode("utf-8"),
    ],
)
def test_corrupt_or_partial_inventory_fails_closed_without_replacement(
    raw: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = retention.index_retention_path(
        "acme",
        chroma_directory=chroma_directory,
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)

    with pytest.raises(retention.IndexRetentionCorrupt, match="inventory"):
        retention.read_retention_inventory(
            "acme",
            chroma_directory=chroma_directory,
        )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(retention.IndexRetentionCorrupt, match="inventory"):
            retention.record_retention_collection(
                "acme",
                _versioned_name("acme", 1),
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert path.read_bytes() == raw


def test_wrong_tenant_inventory_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"

    with _held_tenant_lock(monkeypatch, "beta") as lock_token:
        retention.record_retention_collection(
            "beta",
            _versioned_name("beta", 1),
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    beta_path = retention.index_retention_path(
        "beta",
        chroma_directory=chroma_directory,
    )
    acme_path = retention.index_retention_path(
        "acme",
        chroma_directory=chroma_directory,
    )
    acme_path.write_bytes(beta_path.read_bytes())

    with pytest.raises(retention.IndexRetentionCorrupt, match="tenant"):
        retention.read_retention_inventory(
            "acme",
            chroma_directory=chroma_directory,
        )
    with pytest.raises(retention.IndexRetentionCorrupt, match="tenant"):
        retention.trusted_retention_candidates(
            "acme",
            chroma_directory=chroma_directory,
        )


def test_replace_failure_preserves_inventory_byte_for_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retention = _retention_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = retention.index_retention_path(
        "acme",
        chroma_directory=chroma_directory,
    )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        retention.record_retention_collection(
            "acme",
            _versioned_name("acme", 1),
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    before = path.read_bytes()

    def _fail_replace(source: str | Path, destination: str | Path) -> None:
        _ = source, destination
        raise OSError("retention replace failed")

    monkeypatch.setattr(retention.os, "replace", _fail_replace)
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(OSError, match="retention replace failed"):
            retention.record_retention_collection(
                "acme",
                _versioned_name("acme", 2),
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]

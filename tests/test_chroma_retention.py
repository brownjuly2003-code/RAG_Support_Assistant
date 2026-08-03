from __future__ import annotations

import importlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _adapter_module() -> ModuleType:
    return importlib.import_module("vectordb.chroma_retention")


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


def _seed_versions(
    versions: Sequence[str],
    *,
    lock_token: Any,
    chroma_directory: Path,
) -> None:
    from vectordb.index_manifest import publish_active_collection
    from vectordb.index_retention import record_retention_collection

    for collection_name in versions:
        record_retention_collection(
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


def test_chroma_adapter_deletes_candidates_directly_without_listing_or_opening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 5))
    client_paths: list[str] = []
    delete_calls: list[str] = []

    class _Client:
        def list_collections(self) -> None:
            raise AssertionError("retention adapter must not list collections")

        def get_collection(self, *, name: str) -> None:
            raise AssertionError(f"retention adapter must not open {name}")

        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)

    def _client_factory(*, path: str) -> _Client:
        client_paths.append(path)
        return _Client()

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        deleted = adapter.execute_chroma_retention(
            "acme",
            max_versions=2,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        )

    assert deleted == versions[:2]
    assert delete_calls == list(versions[:2])
    assert client_paths == [str(chroma_directory)]
    inventory = read_retention_inventory(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == list(
        versions[2:]
    )


def test_chroma_adapter_treats_not_found_as_idempotent_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from chromadb.errors import NotFoundError

    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 4))
    delete_calls: list[str] = []

    class _Client:
        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)
            raise NotFoundError("collection is already absent")

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        deleted = adapter.execute_chroma_retention(
            "acme",
            max_versions=2,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
            client_factory=lambda **kwargs: _Client(),
        )

    assert deleted == (versions[0],)
    assert delete_calls == [versions[0]]
    inventory = read_retention_inventory(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == list(
        versions[1:]
    )


def test_chroma_adapter_propagates_other_delete_failures_without_pruning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_retention import (
        IndexRetentionDeletionError,
        index_retention_path,
    )

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 4))
    path = index_retention_path("acme", chroma_directory=chroma_directory)

    class _Client:
        def delete_collection(self, *, name: str) -> None:
            raise RuntimeError(f"backend unavailable for {name}")

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        before = path.read_bytes()
        with pytest.raises(
            IndexRetentionDeletionError,
            match="deletion failed",
        ) as error:
            adapter.execute_chroma_retention(
                "acme",
                max_versions=2,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
                client_factory=lambda **kwargs: _Client(),
            )

    assert error.value.failed_collection == versions[0]
    assert error.value.deleted_collections == ()
    assert isinstance(error.value.__cause__, RuntimeError)
    assert path.read_bytes() == before


def test_chroma_adapter_requires_lock_before_client_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb import tenant_lock

    chroma_directory = tmp_path / "vectordb" / "chroma"
    client_paths: list[str] = []

    def _client_factory(*, path: str) -> Any:
        client_paths.append(path)
        raise AssertionError("client must not be created")

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        adapter.execute_chroma_retention(
            "acme",
            max_versions=2,
            lock_token=None,
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="tenant"):
            adapter.execute_chroma_retention(
                "beta",
                max_versions=2,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
                client_factory=_client_factory,
            )

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        adapter.execute_chroma_retention(
            "acme",
            max_versions=2,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        )
    assert client_paths == []


def test_chroma_adapter_does_not_create_client_without_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 3))

    def _client_factory(*, path: str) -> Any:
        raise AssertionError(f"unexpected Chroma client for {path}")

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        assert adapter.execute_chroma_retention(
            "acme",
            max_versions=2,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        ) == ()

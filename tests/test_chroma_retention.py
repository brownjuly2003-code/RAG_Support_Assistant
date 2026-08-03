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


def _stub_tenant_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    from vectordb import tenant_lock

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)


def _seed_four_versions(
    *,
    tenant_id: str,
    chroma_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, ...]:
    versions = tuple(_versioned_name(tenant_id, ordinal) for ordinal in range(1, 5))
    with _held_tenant_lock(monkeypatch, tenant_id) as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    return versions


def test_guarded_chroma_adapter_deletes_oldest_first_and_returns_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_operator import (
        IndexRetentionExecutionResult,
        preview_index_retention,
    )
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = _seed_four_versions(
        tenant_id="acme",
        chroma_directory=chroma_directory,
        monkeypatch=monkeypatch,
    )
    _stub_tenant_lock(monkeypatch)

    preview = preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )
    assert preview.manifest_generation == 4
    assert preview.deletion_candidates == versions[:2]

    client_paths: list[str] = []
    delete_calls: list[str] = []

    class _Client:
        def list_collections(self) -> None:
            raise AssertionError("guarded adapter must not list collections")

        def get_collection(self, *, name: str) -> None:
            raise AssertionError(f"guarded adapter must not open {name}")

        def create_collection(self, *, name: str) -> None:
            raise AssertionError(f"guarded adapter must not create {name}")

        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)

    def _client_factory(*, path: str) -> _Client:
        client_paths.append(path)
        return _Client()

    result = adapter.execute_guarded_chroma_retention(
        "acme",
        max_versions=2,
        expected_generation=4,
        expected_candidates=preview.deletion_candidates,
        chroma_directory=chroma_directory,
        client_factory=_client_factory,
    )

    assert result == IndexRetentionExecutionResult(
        tenant_id="acme",
        max_versions=2,
        expected_generation=4,
        expected_candidates=versions[:2],
        deleted_collections=versions[:2],
    )
    assert delete_calls == list(versions[:2])
    assert client_paths == [str(chroma_directory)]
    inventory = read_retention_inventory(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert inventory is not None
    assert tuple(entry.collection_name for entry in inventory.collections) == (
        versions[2],
        versions[3],
    )


def test_guarded_chroma_adapter_generation_and_candidate_mismatch_preserve_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_operator import (
        IndexRetentionExecutionConflict,
        preview_index_retention,
    )
    from vectordb.index_retention import index_retention_path

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = _seed_four_versions(
        tenant_id="acme",
        chroma_directory=chroma_directory,
        monkeypatch=monkeypatch,
    )
    _stub_tenant_lock(monkeypatch)

    preview = preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )
    assert preview.manifest_generation == 4
    assert preview.deletion_candidates == versions[:2]

    inventory_path = index_retention_path("acme", chroma_directory=chroma_directory)
    before_inventory = inventory_path.read_bytes()
    client_paths: list[str] = []
    delete_calls: list[str] = []

    class _Client:
        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)

    def _client_factory(*, path: str) -> _Client:
        client_paths.append(path)
        return _Client()

    with pytest.raises(IndexRetentionExecutionConflict):
        adapter.execute_guarded_chroma_retention(
            "acme",
            max_versions=2,
            expected_generation=3,
            expected_candidates=preview.deletion_candidates,
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        )

    with pytest.raises(IndexRetentionExecutionConflict):
        adapter.execute_guarded_chroma_retention(
            "acme",
            max_versions=2,
            expected_generation=4,
            expected_candidates=(versions[1], versions[0]),
            chroma_directory=chroma_directory,
            client_factory=_client_factory,
        )

    assert delete_calls == []
    assert client_paths == []
    assert inventory_path.read_bytes() == before_inventory


def test_guarded_chroma_adapter_invalid_inputs_fail_without_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_operator import IndexRetentionExecutionValidationError

    client_paths: list[str] = []

    def _client_factory(*, path: str) -> Any:
        client_paths.append(path)
        raise AssertionError("client must not be created")

    with pytest.raises(IndexRetentionExecutionValidationError):
        adapter.execute_guarded_chroma_retention(
            "acme",
            max_versions=2,
            expected_generation=0,
            expected_candidates=(),
            chroma_directory=Path("unused"),
            client_factory=_client_factory,
        )

    with pytest.raises(IndexRetentionExecutionValidationError):
        adapter.execute_guarded_chroma_retention(
            "acme",
            max_versions=2,
            expected_generation=1,
            expected_candidates=["a"],  # type: ignore[arg-type]
            chroma_directory=Path("unused"),
            client_factory=_client_factory,
        )

    assert client_paths == []


def test_guarded_chroma_adapter_empty_candidates_skip_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_operator import (
        IndexRetentionExecutionResult,
        preview_index_retention,
    )

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 3))
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    _stub_tenant_lock(monkeypatch)

    preview = preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )
    assert preview.manifest_generation == 2
    assert preview.deletion_candidates == ()

    def _client_factory(*, path: str) -> Any:
        raise AssertionError(f"unexpected Chroma client for {path}")

    result = adapter.execute_guarded_chroma_retention(
        "acme",
        max_versions=2,
        expected_generation=2,
        expected_candidates=(),
        chroma_directory=chroma_directory,
        client_factory=_client_factory,
    )

    assert result == IndexRetentionExecutionResult(
        tenant_id="acme",
        max_versions=2,
        expected_generation=2,
        expected_candidates=(),
        deleted_collections=(),
    )


def test_guarded_chroma_adapter_treats_not_found_as_idempotent_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from chromadb.errors import NotFoundError

    from vectordb.index_operator import (
        IndexRetentionExecutionResult,
        preview_index_retention,
    )
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 4))
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    _stub_tenant_lock(monkeypatch)

    preview = preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )
    assert preview.deletion_candidates == (versions[0],)

    delete_calls: list[str] = []

    class _Client:
        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)
            raise NotFoundError("collection is already absent")

    result = adapter.execute_guarded_chroma_retention(
        "acme",
        max_versions=2,
        expected_generation=3,
        expected_candidates=preview.deletion_candidates,
        chroma_directory=chroma_directory,
        client_factory=lambda **kwargs: _Client(),
    )

    assert result == IndexRetentionExecutionResult(
        tenant_id="acme",
        max_versions=2,
        expected_generation=3,
        expected_candidates=(versions[0],),
        deleted_collections=(versions[0],),
    )
    assert delete_calls == [versions[0]]
    inventory = read_retention_inventory(
        "acme",
        chroma_directory=chroma_directory,
    )
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == list(
        versions[1:]
    )


def test_guarded_chroma_adapter_propagates_other_delete_failures_without_pruning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_module()
    from vectordb.index_operator import preview_index_retention
    from vectordb.index_retention import (
        IndexRetentionDeletionError,
        index_retention_path,
    )

    chroma_directory = tmp_path / "vectordb" / "chroma"
    versions = tuple(_versioned_name("acme", ordinal) for ordinal in range(1, 4))
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        _seed_versions(
            versions,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    _stub_tenant_lock(monkeypatch)

    preview = preview_index_retention(
        "acme",
        max_versions=2,
        chroma_directory=chroma_directory,
    )
    path = index_retention_path("acme", chroma_directory=chroma_directory)
    before = path.read_bytes()

    class _Client:
        def delete_collection(self, *, name: str) -> None:
            raise RuntimeError(f"backend unavailable for {name}")

    with pytest.raises(
        IndexRetentionDeletionError,
        match="deletion failed",
    ) as error:
        adapter.execute_guarded_chroma_retention(
            "acme",
            max_versions=2,
            expected_generation=3,
            expected_candidates=preview.deletion_candidates,
            chroma_directory=chroma_directory,
            client_factory=lambda **kwargs: _Client(),
        )

    assert error.value.failed_collection == versions[0]
    assert error.value.deleted_collections == ()
    assert isinstance(error.value.__cause__, RuntimeError)
    assert path.read_bytes() == before


def test_guarded_chroma_adapter_forwards_to_operator_without_caller_lock_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inspect

    adapter = _adapter_module()
    from vectordb.index_operator import IndexRetentionExecutionResult

    seen_kwargs: dict[str, Any] = {}
    client_paths: list[str] = []
    delete_calls: list[str] = []
    directory = Path("tmp-chroma")

    class _Client:
        def list_collections(self) -> None:
            raise AssertionError("must not list")

        def get_collection(self, *, name: str) -> None:
            raise AssertionError("must not open")

        def create_collection(self, *, name: str) -> None:
            raise AssertionError("must not create")

        def delete_collection(self, *, name: str) -> None:
            delete_calls.append(name)

    def _client_factory(*, path: str) -> _Client:
        client_paths.append(path)
        return _Client()

    def _fake_execute(
        tenant_id: str,
        *,
        max_versions: int,
        expected_generation: int,
        expected_candidates: tuple[str, ...],
        delete_collection_if_exists: Any,
        chroma_directory: Any = None,
    ) -> IndexRetentionExecutionResult:
        seen_kwargs["tenant_id"] = tenant_id
        seen_kwargs["max_versions"] = max_versions
        seen_kwargs["expected_generation"] = expected_generation
        seen_kwargs["expected_candidates"] = expected_candidates
        seen_kwargs["chroma_directory"] = chroma_directory
        seen_kwargs["callback"] = delete_collection_if_exists
        # Client must stay lazy until the first real delete.
        assert client_paths == []
        delete_collection_if_exists("old_a")
        delete_collection_if_exists("old_b")
        assert client_paths == [str(directory)]
        return IndexRetentionExecutionResult(
            tenant_id=tenant_id,
            max_versions=max_versions,
            expected_generation=expected_generation,
            expected_candidates=expected_candidates,
            deleted_collections=("old_a", "old_b"),
        )

    monkeypatch.setattr(adapter, "execute_index_retention", _fake_execute)

    signature = inspect.signature(adapter.execute_guarded_chroma_retention)
    assert "lock_token" not in signature.parameters

    source = inspect.getsource(adapter)
    assert "execute_index_retention" in source
    assert "from vectordb.index_operator import" in source
    # No manager/FastAPI/settings/audit/list/open/create wiring.
    for forbidden in (
        "vectordb.manager",
        "fastapi",
        "APIRouter",
        "settings",
        "audit",
        "list_collections",
        "get_collection",
        "create_collection",
    ):
        assert forbidden not in source

    result = adapter.execute_guarded_chroma_retention(
        "acme",
        max_versions=2,
        expected_generation=4,
        expected_candidates=("old_a", "old_b"),
        chroma_directory=directory,
        client_factory=_client_factory,
    )

    assert seen_kwargs["tenant_id"] == "acme"
    assert seen_kwargs["max_versions"] == 2
    assert seen_kwargs["expected_generation"] == 4
    assert seen_kwargs["expected_candidates"] == ("old_a", "old_b")
    assert seen_kwargs["chroma_directory"] == directory
    assert callable(seen_kwargs["callback"])
    assert delete_calls == ["old_a", "old_b"]
    assert client_paths == [str(directory)]
    assert result == IndexRetentionExecutionResult(
        tenant_id="acme",
        max_versions=2,
        expected_generation=4,
        expected_candidates=("old_a", "old_b"),
        deleted_collections=("old_a", "old_b"),
    )

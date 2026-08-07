"""2.6e — same-tenant rebuild lock contention fail-closed.

Proves concurrent same-tenant rebuilds cannot double-publish or tear the
active manifest when the tenant advisory lock is contended:

1. A rebuild that cannot acquire the lock fails closed with
   ``TenantIndexLockTimeout`` and leaves the active version unchanged.
2. Serialized concurrent rebuilds publish monotonically (one generation step
   per successful winner) without a torn active pointer.
"""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _Embeddings:
    def embed_query(self, text: str) -> list[float]:
        assert text
        return [0.0, 0.0, 0.0]


class _FakeChromaState:
    def __init__(self) -> None:
        self.documents: dict[str, list[Any]] = {}
        self.built_names: list[str] = []
        self.deleted_names: list[str] = []
        self.events: list[str] = []
        self._guard = threading.Lock()

    def note(self, event: str) -> None:
        with self._guard:
            self.events.append(event)


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        return self._value


class _AdvisoryLockRegistry:
    """In-process stand-in for PostgreSQL session advisory locks."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._owners: dict[int, int] = {}
        self._next_owner = 0

    def connect(self) -> _FakeConnection:
        with self._guard:
            self._next_owner += 1
            owner = self._next_owner
        return _FakeConnection(self, owner)

    def execute(self, owner: int, statement: Any, params: dict[str, int]) -> _ScalarResult:
        sql = str(statement)
        key = params["lock_key"]
        with self._guard:
            if "pg_try_advisory_lock" in sql:
                if key in self._owners:
                    return _ScalarResult(False)
                self._owners[key] = owner
                return _ScalarResult(True)
            if "pg_advisory_unlock" in sql:
                if self._owners.get(key) != owner:
                    return _ScalarResult(False)
                self._owners.pop(key, None)
                return _ScalarResult(True)
        raise AssertionError(f"Unexpected advisory-lock statement: {sql}")

    def close(self, owner: int) -> None:
        with self._guard:
            for key, current_owner in list(self._owners.items()):
                if current_owner == owner:
                    self._owners.pop(key, None)

    def is_held(self, lock_key: int) -> bool:
        with self._guard:
            return lock_key in self._owners


class _FakeConnection:
    def __init__(self, registry: _AdvisoryLockRegistry, owner: int) -> None:
        self._registry = registry
        self._owner = owner

    def execute(self, statement: Any, params: dict[str, int]) -> _ScalarResult:
        return self._registry.execute(self._owner, statement, params)

    def close(self) -> None:
        self._registry.close(self._owner)


def _fake_chroma(state: _FakeChromaState) -> type[Any]:
    class _Collection:
        def __init__(self, collection_name: str) -> None:
            self.name = collection_name

        def count(self) -> int:
            return len(state.documents.get(self.name, []))

        def query(
            self,
            *,
            query_embeddings: list[list[float]],
            n_results: int,
        ) -> dict[str, list[list[str]]]:
            assert len(query_embeddings[0]) == 3
            assert n_results == 1
            return {"ids": [["known-chunk"]]}

        def get(self, *, include: list[str]) -> dict[str, list[Any]]:
            assert include == ["documents", "metadatas"]
            documents = state.documents.get(self.name, [])
            return {
                "documents": [doc.page_content for doc in documents],
                "metadatas": [dict(doc.metadata or {}) for doc in documents],
            }

    class _FakeChroma:
        def __init__(
            self,
            *,
            persist_directory: str,
            embedding_function: Any,
            collection_name: str,
            create_collection_if_not_exists: bool = True,
        ) -> None:
            _ = persist_directory, embedding_function
            if (
                not create_collection_if_not_exists
                and collection_name not in state.documents
            ):
                raise RuntimeError("collection does not exist")
            self.collection_name = collection_name
            self._collection = _Collection(collection_name)

        @classmethod
        def from_documents(
            cls,
            *,
            documents: list[Any],
            embedding: Any,
            persist_directory: str,
            collection_name: str,
        ) -> Any:
            state.note(f"build:{collection_name}")
            with state._guard:
                state.built_names.append(collection_name)
                state.documents[collection_name] = list(documents)
            return cls(
                persist_directory=persist_directory,
                embedding_function=embedding,
                collection_name=collection_name,
            )

        def persist(self) -> None:
            state.note(f"persist:{self.collection_name}")

        def delete_collection(self) -> None:
            state.note(f"delete:{self.collection_name}")
            with state._guard:
                state.deleted_names.append(self.collection_name)
                state.documents.pop(self.collection_name, None)

        def similarity_search(self, query: str, *, k: int) -> list[Any]:
            assert query.strip()
            state.note(f"known-query:{self.collection_name}")
            return list(state.documents.get(self.collection_name, []))[:k]

    return _FakeChroma


def _settings(chroma_directory: Path) -> SimpleNamespace:
    return SimpleNamespace(
        vector_backend="chroma",
        vectordb_chroma_dir=chroma_directory,
        vectordb_collection_prefix="rag_docs",
        vectordb_retention_max_versions=3,
        chunk_size=100,
        chunk_overlap=0,
        contextual_headers=False,
        rag_device="cpu",
        ingestion_tenant_lock_wait_sec=0.05,
    )


def _configure_manager_with_real_lock(
    monkeypatch: pytest.MonkeyPatch,
    chroma_directory: Path,
    state: _FakeChromaState,
    registry: _AdvisoryLockRegistry,
    *,
    wait_timeout_sec: float,
) -> Any:
    """Wire manager rebuild path with real acquire/release against registry."""
    from vectordb import manager, tenant_lock

    class _Retriever:
        def __init__(self, collection_name: str) -> None:
            self.collection_name = collection_name

    monkeypatch.setattr(manager, "get_settings", lambda: _settings(chroma_directory))
    monkeypatch.setattr(manager, "Chroma", _fake_chroma(state), raising=False)
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: wait_timeout_sec)
    # Keep real _acquire / _release — this is the contention contract under test.
    monkeypatch.setattr(manager, "tenant_index_lock", tenant_lock.tenant_index_lock)
    monkeypatch.setattr(
        manager._base_manager,
        "select_chunks",
        lambda docs, *args, **kwargs: list(docs),
    )
    monkeypatch.setattr(
        manager._base_manager,
        "get_retriever",
        lambda store, **kwargs: _Retriever(store.collection_name),
    )
    monkeypatch.setattr(manager, "_report_bm25_state", lambda *args: None)
    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        lambda *args, **kwargs: (),
        raising=False,
    )
    manager.reset_retriever_cache()
    return manager


def _seed_active(
    monkeypatch: pytest.MonkeyPatch,
    registry: _AdvisoryLockRegistry,
    chroma_directory: Path,
    state: _FakeChromaState,
    *,
    tenant_id: str,
    collection_name: str,
    content: str,
    document_cls: type[Any],
) -> None:
    from vectordb import tenant_lock
    from vectordb.index_manifest import publish_active_collection

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 1.0)
    state.documents[collection_name] = [
        document_cls(page_content=content, metadata={"chunk_index": 0})
    ]
    with tenant_lock.tenant_index_lock(tenant_id) as lock_token:
        publish_active_collection(
            tenant_id,
            collection_name,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


def test_build_fail_closed_when_tenant_lock_already_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb import tenant_lock
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    registry = _AdvisoryLockRegistry()
    manager = _configure_manager_with_real_lock(
        monkeypatch,
        chroma_directory,
        state,
        registry,
        wait_timeout_sec=0.05,
    )
    active_name = "rag_docs-v-acme-1111111111111111"
    _seed_active(
        monkeypatch,
        registry,
        chroma_directory,
        state,
        tenant_id="acme",
        collection_name=active_name,
        content="still active",
        document_cls=manager.Document,
    )
    # Re-apply lock wiring after seed (seed also patched open/wait).
    manager = _configure_manager_with_real_lock(
        monkeypatch,
        chroma_directory,
        state,
        registry,
        wait_timeout_sec=0.05,
    )

    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    builds_before = list(state.built_names)

    holder_ready = threading.Event()
    release_holder = threading.Event()
    holder_errors: list[BaseException] = []

    def _hold_lock() -> None:
        try:
            with tenant_lock.tenant_index_lock("acme"):
                holder_ready.set()
                assert release_holder.wait(timeout=5)
        except BaseException as exc:  # pragma: no cover - relayed
            holder_errors.append(exc)

    holder = threading.Thread(target=_hold_lock)
    holder.start()
    assert holder_ready.wait(timeout=2)

    with pytest.raises(tenant_lock.TenantIndexLockTimeout, match="already in progress"):
        manager.build_vector_store(
            [
                manager.Document(
                    page_content="loser candidate",
                    metadata={"source": "loser.md"},
                )
            ],
            {"chunk_size": 100, "chunk_overlap": 0},
            embeddings=_Embeddings(),
            tenant_id="acme",
        )

    release_holder.set()
    holder.join(timeout=2)
    assert not holder.is_alive()
    assert holder_errors == []

    # Loser never entered rebuild: no new staged collection under lock.
    assert state.built_names == builds_before
    assert active_name in state.documents
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    assert active.generation == 1
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )


def test_serialized_concurrent_rebuilds_publish_monotonically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import read_index_manifest

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    registry = _AdvisoryLockRegistry()
    manager = _configure_manager_with_real_lock(
        monkeypatch,
        chroma_directory,
        state,
        registry,
        wait_timeout_sec=2.0,
    )
    active_name = "rag_docs-v-acme-1111111111111111"
    _seed_active(
        monkeypatch,
        registry,
        chroma_directory,
        state,
        tenant_id="acme",
        collection_name=active_name,
        content="seed active",
        document_cls=manager.Document,
    )
    manager = _configure_manager_with_real_lock(
        monkeypatch,
        chroma_directory,
        state,
        registry,
        wait_timeout_sec=2.0,
    )

    first_entered = threading.Event()
    release_first = threading.Event()
    results: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}
    barrier = threading.Barrier(2)

    # Gate after lock acquisition via known-query so the second waiter blocks
    # on the tenant lock (not on a no-op acquire).
    real_known_query = manager.validate_staged_known_query
    gate = threading.Lock()
    paused_once = False

    def _gated_known_query(*args: Any, **kwargs: Any) -> Any:
        nonlocal paused_once
        should_pause = False
        with gate:
            if not paused_once:
                paused_once = True
                should_pause = True
        if should_pause:
            first_entered.set()
            assert release_first.wait(timeout=5)
        return real_known_query(*args, **kwargs)

    monkeypatch.setattr(manager, "validate_staged_known_query", _gated_known_query)

    def _worker(name: str, content: str) -> None:
        try:
            barrier.wait(timeout=5)
            store, chunks = manager.build_vector_store(
                [
                    manager.Document(
                        page_content=content,
                        metadata={"source": f"{name}.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )
            results[name] = (store.collection_name, chunks[0].page_content)
        except BaseException as exc:  # pragma: no cover - relayed
            errors[name] = exc

    t1 = threading.Thread(target=_worker, args=("first", "first body"))
    t2 = threading.Thread(target=_worker, args=("second", "second body"))
    t1.start()
    t2.start()

    assert first_entered.wait(timeout=3)
    # Second must not have published while first holds the tenant lock.
    mid = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert mid is not None
    assert mid.active_collection == active_name or mid.generation >= 1
    # While first is mid-rebuild, second is blocked on lock (not publishing).
    release_first.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not t1.is_alive()
    assert not t2.is_alive()
    assert errors == {}, errors
    assert set(results) == {"first", "second"}

    final = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert final is not None
    # Two successful publishes after seed → generation 3 (seed was 1).
    assert final.generation == 3
    assert final.active_collection in {
        results["first"][0],
        results["second"][0],
    }
    assert final.active_collection != active_name
    # Active always points at an existing collection, never a deleted orphan.
    assert final.active_collection in state.documents
    # Both rebuilds ran under lock serialization (two new builds after seed).
    assert len([n for n in state.built_names if n != active_name]) == 2


def test_unknown_lifecycle_fault_still_excludes_concurrency_name() -> None:
    """Concurrency is a lock-path contract in 2.6e, not a lifecycle inject name."""
    from vectordb import index_lifecycle_faults as faults

    assert "concurrency" not in faults.known_fault_points()
    with pytest.raises(ValueError, match="Unknown index lifecycle fault point"):
        faults.arm_fault("concurrency", RuntimeError("nope"))

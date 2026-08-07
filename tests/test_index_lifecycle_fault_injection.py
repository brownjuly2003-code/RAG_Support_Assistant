"""2.6a–2.6d — index lifecycle fail-closed fault injection.

Proves named lifecycle fault points:
1. Inventory-write failure does not change the active manifest and discards the
   unpublished candidate (publish never commits).
2. Manifest-publish failure does not leave a dangerous live candidate; active
   collection and durable manifest stay on the previous version.
3. Known-query validation failure (2.6b) does not record inventory or publish,
   and discards the unpublished candidate with the active manifest unchanged.
4. Embeddings dimension validation failure (2.6c) cleans the partial candidate
   during build, never reaches inventory/publish, and keeps the active manifest.
5. Cleanup discard-path failure (2.6d) surfaces without publishing; active
   manifest stays unchanged even when the unpublished candidate cannot be deleted.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
            state.events.append(f"build:{collection_name}")
            state.built_names.append(collection_name)
            state.documents[collection_name] = list(documents)
            return cls(
                persist_directory=persist_directory,
                embedding_function=embedding,
                collection_name=collection_name,
            )

        def persist(self) -> None:
            state.events.append(f"persist:{self.collection_name}")

        def delete_collection(self) -> None:
            state.events.append(f"delete:{self.collection_name}")
            state.deleted_names.append(self.collection_name)
            state.documents.pop(self.collection_name, None)

        def similarity_search(self, query: str, *, k: int) -> list[Any]:
            assert query.strip()
            state.events.append(f"known-query:{self.collection_name}")
            return list(state.documents.get(self.collection_name, []))[:k]

    return _FakeChroma


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
    )


def _configure_manager(
    monkeypatch: pytest.MonkeyPatch,
    chroma_directory: Path,
    state: _FakeChromaState,
) -> Any:
    from vectordb import manager, tenant_lock

    class _Retriever:
        def __init__(self, collection_name: str) -> None:
            self.collection_name = collection_name

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(manager, "get_settings", lambda: _settings(chroma_directory))
    monkeypatch.setattr(manager, "Chroma", _fake_chroma(state), raising=False)
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)
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
    manager.reset_retriever_cache()
    return manager


def _publish(
    monkeypatch: pytest.MonkeyPatch,
    chroma_directory: Path,
    collection_name: str,
    *,
    tenant_id: str = "acme",
) -> Any:
    from vectordb.index_manifest import publish_active_collection

    with _held_tenant_lock(monkeypatch, tenant_id) as lock_token:
        return publish_active_collection(
            tenant_id,
            collection_name,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


@pytest.fixture(autouse=True)
def _clear_lifecycle_faults() -> Iterator[None]:
    from vectordb.index_lifecycle_faults import clear_faults

    clear_faults()
    try:
        yield
    finally:
        clear_faults()


def test_known_fault_points_include_inventory_through_cleanup() -> None:
    from vectordb import index_lifecycle_faults as faults

    assert faults.known_fault_points() == frozenset(
        {
            faults.INVENTORY_WRITE,
            faults.MANIFEST_PUBLISH,
            faults.KNOWN_QUERY,
            faults.EMBEDDINGS,
            faults.CLEANUP,
        }
    )
    with pytest.raises(ValueError, match="Unknown index lifecycle fault point"):
        faults.arm_fault("concurrency", RuntimeError("nope"))


def test_inventory_write_fault_keeps_active_manifest_and_discards_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_lifecycle_faults import (
        INVENTORY_WRITE,
        IndexLifecycleFaultError,
        fault_armed,
        is_armed,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    retention_calls: list[str] = []
    publish_calls: list[str] = []

    real_publish = manager.publish_active_collection

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        publish_calls.append(str(args[1]))
        return real_publish(*args, **kwargs)

    def _spy_retention(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        retention_calls.append("called")
        return ()

    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)
    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        _spy_retention,
        raising=False,
    )

    with fault_armed(
        INVENTORY_WRITE,
        IndexLifecycleFaultError("inventory commit injected failure"),
    ):
        assert is_armed(INVENTORY_WRITE)
        with pytest.raises(
            IndexLifecycleFaultError,
            match="inventory commit injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )

    assert not is_armed(INVENTORY_WRITE)
    candidate_name = state.built_names[-1]
    assert candidate_name != active_name
    assert publish_calls == []
    assert retention_calls == []
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert candidate_name not in state.documents
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )
    # No durable inventory temp files left behind after fail-closed write.
    retention_root = chroma_directory / "index-retention"
    if retention_root.exists():
        leftover = list(retention_root.glob("*.tmp"))
        assert leftover == []


def test_manifest_publish_fault_discards_candidate_without_live_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_lifecycle_faults import (
        MANIFEST_PUBLISH,
        IndexLifecycleFaultError,
        fault_armed,
        is_armed,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    retention_calls: list[str] = []

    def _spy_retention(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        retention_calls.append("called")
        return ()

    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        _spy_retention,
        raising=False,
    )

    with fault_armed(
        MANIFEST_PUBLISH,
        IndexLifecycleFaultError("manifest publish injected failure"),
    ):
        assert is_armed(MANIFEST_PUBLISH)
        with pytest.raises(
            IndexLifecycleFaultError,
            match="manifest publish injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )

    assert not is_armed(MANIFEST_PUBLISH)
    candidate_name = state.built_names[-1]
    assert candidate_name != active_name
    # Unpublished candidate must not remain as a live/dangerous collection.
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert candidate_name not in state.documents
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    assert active.generation == 1
    assert retention_calls == []
    # Inventory may record the candidate before publish; that entry is not live.
    inventory = read_retention_inventory("acme", chroma_directory=chroma_directory)
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == [
        candidate_name
    ]
    manifests_root = chroma_directory / "index-manifests"
    leftover = list(manifests_root.glob("*.tmp")) if manifests_root.exists() else []
    assert leftover == []


def test_known_query_fault_keeps_active_manifest_and_discards_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2.6b: known-query fault before inventory must not publish or leave live candidate."""
    from vectordb.index_lifecycle_faults import (
        KNOWN_QUERY,
        IndexLifecycleFaultError,
        fault_armed,
        is_armed,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    retention_calls: list[str] = []
    inventory_calls: list[str] = []
    publish_calls: list[str] = []

    real_record = manager.record_retention_collection
    real_publish = manager.publish_active_collection

    def _spy_record(*args: Any, **kwargs: Any) -> Any:
        inventory_calls.append(str(args[1]))
        return real_record(*args, **kwargs)

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        publish_calls.append(str(args[1]))
        return real_publish(*args, **kwargs)

    def _spy_retention(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        retention_calls.append("called")
        return ()

    monkeypatch.setattr(manager, "record_retention_collection", _spy_record)
    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)
    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        _spy_retention,
        raising=False,
    )

    with fault_armed(
        KNOWN_QUERY,
        IndexLifecycleFaultError("known-query validation injected failure"),
    ):
        assert is_armed(KNOWN_QUERY)
        with pytest.raises(
            IndexLifecycleFaultError,
            match="known-query validation injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )

    assert not is_armed(KNOWN_QUERY)
    candidate_name = state.built_names[-1]
    assert candidate_name != active_name
    # Candidate was built (staging succeeded) but never advanced past validation.
    assert any(event.startswith("build:") for event in state.events)
    assert inventory_calls == []
    assert publish_calls == []
    assert retention_calls == []
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert candidate_name not in state.documents
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )


def test_embeddings_fault_cleans_candidate_before_inventory_or_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2.6c: embeddings fault during staging cleans candidate; active stays put."""
    from vectordb.index_lifecycle_faults import (
        EMBEDDINGS,
        IndexLifecycleFaultError,
        fault_armed,
        is_armed,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    retention_calls: list[str] = []
    inventory_calls: list[str] = []
    publish_calls: list[str] = []
    known_query_calls: list[str] = []

    real_record = manager.record_retention_collection
    real_publish = manager.publish_active_collection
    real_known_query = manager.validate_staged_known_query

    def _spy_record(*args: Any, **kwargs: Any) -> Any:
        inventory_calls.append(str(args[1]))
        return real_record(*args, **kwargs)

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        publish_calls.append(str(args[1]))
        return real_publish(*args, **kwargs)

    def _spy_known_query(*args: Any, **kwargs: Any) -> Any:
        known_query_calls.append("called")
        return real_known_query(*args, **kwargs)

    def _spy_retention(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        retention_calls.append("called")
        return ()

    monkeypatch.setattr(manager, "record_retention_collection", _spy_record)
    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)
    monkeypatch.setattr(manager, "validate_staged_known_query", _spy_known_query)
    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        _spy_retention,
        raising=False,
    )

    with fault_armed(
        EMBEDDINGS,
        IndexLifecycleFaultError("embeddings validation injected failure"),
    ):
        assert is_armed(EMBEDDINGS)
        with pytest.raises(
            IndexLifecycleFaultError,
            match="embeddings validation injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )

    assert not is_armed(EMBEDDINGS)
    candidate_name = state.built_names[-1]
    assert candidate_name != active_name
    # Build started and cleaned inside staging; later gates never run.
    assert any(event.startswith("build:") for event in state.events)
    assert state.deleted_names == [candidate_name]
    assert candidate_name not in state.documents
    assert active_name in state.documents
    assert known_query_calls == []
    assert inventory_calls == []
    assert publish_calls == []
    assert retention_calls == []
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )


def test_cleanup_fault_after_known_query_failure_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2.6d: cleanup fault on discard surfaces; active stays put; no publish."""
    from vectordb.index_lifecycle_faults import (
        CLEANUP,
        KNOWN_QUERY,
        IndexLifecycleFaultError,
        arm_fault,
        clear_faults,
        is_armed,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    retention_calls: list[str] = []
    inventory_calls: list[str] = []
    publish_calls: list[str] = []

    real_record = manager.record_retention_collection
    real_publish = manager.publish_active_collection

    def _spy_record(*args: Any, **kwargs: Any) -> Any:
        inventory_calls.append(str(args[1]))
        return real_record(*args, **kwargs)

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        publish_calls.append(str(args[1]))
        return real_publish(*args, **kwargs)

    def _spy_retention(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        retention_calls.append("called")
        return ()

    monkeypatch.setattr(manager, "record_retention_collection", _spy_record)
    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)
    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        _spy_retention,
        raising=False,
    )

    arm_fault(
        KNOWN_QUERY,
        IndexLifecycleFaultError("known-query validation injected failure"),
    )
    arm_fault(
        CLEANUP,
        IndexLifecycleFaultError("cleanup discard injected failure"),
    )
    try:
        assert is_armed(KNOWN_QUERY)
        assert is_armed(CLEANUP)
        with pytest.raises(
            IndexLifecycleFaultError,
            match="cleanup discard injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )
    finally:
        clear_faults()

    assert not is_armed(KNOWN_QUERY)
    assert not is_armed(CLEANUP)
    candidate_name = state.built_names[-1]
    assert candidate_name != active_name
    # Cleanup inject fires before delete_collection, so discard did not complete.
    assert candidate_name not in state.deleted_names
    assert candidate_name in state.documents
    assert active_name in state.documents
    assert inventory_calls == []
    assert publish_calls == []
    assert retention_calls == []
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name
    # Failed discard must not promote the orphan candidate to active.
    assert active.active_collection != candidate_name
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )


def test_cleanup_fault_during_embeddings_failure_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2.6d: cleanup fault during staging self-cleanup also stays fail-closed."""
    from vectordb.index_lifecycle_faults import (
        CLEANUP,
        EMBEDDINGS,
        IndexLifecycleFaultError,
        arm_fault,
        clear_faults,
    )
    from vectordb.index_manifest import index_manifest_path, read_index_manifest

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="still active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()

    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        lambda *args, **kwargs: (),
        raising=False,
    )

    arm_fault(
        EMBEDDINGS,
        IndexLifecycleFaultError("embeddings validation injected failure"),
    )
    arm_fault(
        CLEANUP,
        IndexLifecycleFaultError("cleanup discard injected failure"),
    )
    try:
        with pytest.raises(
            IndexLifecycleFaultError,
            match="cleanup discard injected failure",
        ):
            manager.build_vector_store(
                [
                    manager.Document(
                        page_content="candidate body",
                        metadata={"source": "new.md"},
                    )
                ],
                {"chunk_size": 100, "chunk_overlap": 0},
                embeddings=_Embeddings(),
                tenant_id="acme",
            )
    finally:
        clear_faults()

    candidate_name = state.built_names[-1]
    assert candidate_name not in state.deleted_names
    assert candidate_name in state.documents
    assert active_name in state.documents
    assert manifest_path.read_bytes() == manifest_before
    active = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert active is not None
    assert active.active_collection == active_name


def test_unarmed_build_still_publishes_and_records_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: importing fault hooks must not change the happy path."""
    from vectordb.index_lifecycle_faults import is_armed
    from vectordb.index_manifest import read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="old active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)

    monkeypatch.setattr(
        manager,
        "execute_chroma_retention",
        lambda *args, **kwargs: (),
        raising=False,
    )

    assert not is_armed("inventory_write")
    assert not is_armed("manifest_publish")
    assert not is_armed("known_query")
    assert not is_armed("embeddings")
    assert not is_armed("cleanup")

    store, chunks = manager.build_vector_store(
        [
            manager.Document(
                page_content="new known content",
                metadata={"source": "new.md"},
            )
        ],
        {"chunk_size": 100, "chunk_overlap": 0},
        embeddings=_Embeddings(),
        tenant_id="acme",
    )

    assert chunks[0].page_content == "new known content"
    assert store.collection_name in state.documents
    assert store.collection_name not in state.deleted_names
    manifest = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert manifest is not None
    assert manifest.active_collection == store.collection_name
    assert manifest.previous_collection == active_name
    inventory = read_retention_inventory("acme", chroma_directory=chroma_directory)
    assert inventory is not None
    assert store.collection_name in [
        entry.collection_name for entry in inventory.collections
    ]

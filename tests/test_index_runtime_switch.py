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
        self.opened_names: list[str] = []
        self.deleted_names: list[str] = []
        self.events: list[str] = []
        self.fail_dimension = False
        self.fail_known_query = False


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
            state.events.append(f"dimension:{self.name}")
            if state.fail_dimension:
                raise RuntimeError("dimension validation failed")
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
            if not create_collection_if_not_exists and collection_name not in state.documents:
                raise RuntimeError("collection does not exist")
            self.collection_name = collection_name
            self._collection = _Collection(collection_name)
            state.opened_names.append(collection_name)

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
            if state.fail_known_query:
                raise RuntimeError("known query failed")
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
) -> Any:
    from vectordb.index_manifest import publish_active_collection

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        return publish_active_collection(
            "acme",
            collection_name,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


def test_rebuild_validates_known_query_then_atomically_publishes_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import read_index_manifest
    from vectordb.index_retention import read_retention_inventory

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    legacy_name = manager._collection_name("acme")
    old_doc = manager.Document(page_content="old active content", metadata={})
    state.documents[legacy_name] = [old_doc]
    docs = [manager.Document(page_content="new known content", metadata={"source": "new.md"})]
    real_record_retention = manager.record_retention_collection
    real_publish = manager.publish_active_collection

    def _spy_record_retention(*args: Any, **kwargs: Any) -> Any:
        collection_name = args[1]
        state.events.append(f"record-inventory:{collection_name}")
        return real_record_retention(*args, **kwargs)

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        collection_name = args[1]
        state.events.append(f"publish:{collection_name}")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(
        manager,
        "record_retention_collection",
        _spy_record_retention,
        raising=False,
    )
    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)

    store, chunks = manager.build_vector_store(
        docs,
        {"chunk_size": 100, "chunk_overlap": 0},
        embeddings=_Embeddings(),
        tenant_id="acme",
    )

    manifest = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert manifest is not None
    assert manifest.active_collection == store.collection_name
    assert manifest.generation == 1
    assert state.documents[legacy_name] == [old_doc]
    assert legacy_name not in state.deleted_names
    assert state.events.index(f"known-query:{store.collection_name}") < state.events.index(
        f"record-inventory:{store.collection_name}"
    )
    assert state.events.index(
        f"record-inventory:{store.collection_name}"
    ) < state.events.index(f"publish:{store.collection_name}")
    assert store.collection_name not in state.deleted_names
    assert state.deleted_names == []
    inventory = read_retention_inventory("acme", chroma_directory=chroma_directory)
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == [
        store.collection_name
    ]
    assert chunks[0].page_content == "new known content"

    retriever = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )
    assert retriever.collection_name == manifest.active_collection


def test_known_query_failure_removes_candidate_without_changing_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import index_manifest_path
    from vectordb.index_staging import IndexStagingValidationError

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
    state.fail_known_query = True

    with pytest.raises(IndexStagingValidationError, match="known-query"):
        manager.build_vector_store(
            [manager.Document(page_content="candidate", metadata={"source": "new.md"})],
            {"chunk_size": 100, "chunk_overlap": 0},
            embeddings=_Embeddings(),
            tenant_id="acme",
        )

    candidate_name = state.built_names[-1]
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert manifest_path.read_bytes() == manifest_before


def test_inventory_record_failure_does_not_publish_and_discards_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import index_manifest_path
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
    publish_calls: list[str] = []
    real_publish = manager.publish_active_collection

    def _fail_record(*args: Any, **kwargs: Any) -> None:
        state.events.append(f"record-inventory-fail:{args[1]}")
        raise RuntimeError("inventory record failed")

    def _spy_publish(*args: Any, **kwargs: Any) -> Any:
        publish_calls.append(args[1])
        state.events.append(f"publish:{args[1]}")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(
        manager,
        "record_retention_collection",
        _fail_record,
        raising=False,
    )
    monkeypatch.setattr(manager, "publish_active_collection", _spy_publish)

    with pytest.raises(RuntimeError, match="inventory record failed"):
        manager.build_vector_store(
            [manager.Document(page_content="candidate", metadata={"source": "new.md"})],
            {"chunk_size": 100, "chunk_overlap": 0},
            embeddings=_Embeddings(),
            tenant_id="acme",
        )

    candidate_name = state.built_names[-1]
    assert publish_calls == []
    assert f"publish:{candidate_name}" not in state.events
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert candidate_name not in state.documents
    assert manifest_path.read_bytes() == manifest_before
    assert (
        read_retention_inventory("acme", chroma_directory=chroma_directory) is None
    )


def test_publish_failure_removes_unpublished_candidate_and_preserves_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import index_manifest_path
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

    def _fail_publish(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("manifest publish failed")

    monkeypatch.setattr(manager, "publish_active_collection", _fail_publish, raising=False)

    with pytest.raises(RuntimeError, match="manifest publish failed"):
        manager.build_vector_store(
            [manager.Document(page_content="candidate", metadata={"source": "new.md"})],
            {"chunk_size": 100, "chunk_overlap": 0},
            embeddings=_Embeddings(),
            tenant_id="acme",
        )

    candidate_name = state.built_names[-1]
    assert state.deleted_names == [candidate_name]
    assert active_name in state.documents
    assert candidate_name not in state.documents
    assert manifest_path.read_bytes() == manifest_before
    # Stale trusted inventory entry may remain after publish fails; retention
    # adapter treats NotFoundError as idempotent and prunes durable inventory.
    inventory = read_retention_inventory("acme", chroma_directory=chroma_directory)
    assert inventory is not None
    assert [entry.collection_name for entry in inventory.collections] == [
        candidate_name
    ]


def test_retriever_cache_invalidates_when_manifest_generation_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    first_name = "rag_docs-v-acme-1111111111111111"
    second_name = "rag_docs-v-acme-2222222222222222"
    state.documents[first_name] = [
        manager.Document(page_content="first", metadata={"chunk_index": 0})
    ]
    state.documents[second_name] = [
        manager.Document(page_content="second", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, first_name)

    first = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )
    _publish(monkeypatch, chroma_directory, second_name)
    second = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )

    assert first.collection_name == first_name
    assert second.collection_name == second_name
    assert first is not second
    assert state.opened_names == [first_name, second_name]


def test_runtime_rollback_validates_previous_then_switches_cache_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import read_index_manifest

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    first_name = "rag_docs-v-acme-1111111111111111"
    second_name = "rag_docs-v-acme-2222222222222222"
    state.documents[first_name] = [
        manager.Document(page_content="first", metadata={"chunk_index": 0})
    ]
    state.documents[second_name] = [
        manager.Document(page_content="second", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, first_name)
    _publish(monkeypatch, chroma_directory, second_name)
    active_retriever = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )

    store, chunks = manager.rollback_vector_store(
        tenant_id="acme",
        embeddings=_Embeddings(),
    )

    rolled_back = read_index_manifest("acme", chroma_directory=chroma_directory)
    assert rolled_back is not None
    assert rolled_back.active_collection == first_name
    assert rolled_back.previous_collection == second_name
    assert rolled_back.generation == 3
    assert store.collection_name == first_name
    assert [chunk.page_content for chunk in chunks] == ["first"]
    assert f"dimension:{first_name}" in state.events
    assert f"known-query:{first_name}" in state.events

    rolled_back_retriever = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )
    assert rolled_back_retriever.collection_name == first_name
    assert rolled_back_retriever is not active_retriever
    assert state.opened_names == [second_name, first_name]
    assert state.deleted_names == []


@pytest.mark.parametrize(
    ("failure_mode", "message"),
    [
        ("missing", "unavailable"),
        ("empty", "no restorable chunks"),
        ("dimension", "dimension"),
        ("known-query", "known-query"),
    ],
)
def test_runtime_rollback_target_failure_preserves_manifest_and_active_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
    message: str,
) -> None:
    from vectordb.index_manifest import index_manifest_path
    from vectordb.index_staging import IndexStagingValidationError

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    first_name = "rag_docs-v-acme-1111111111111111"
    second_name = "rag_docs-v-acme-2222222222222222"
    if failure_mode != "missing":
        state.documents[first_name] = []
    if failure_mode in {"dimension", "known-query"}:
        state.documents[first_name] = [
            manager.Document(page_content="first", metadata={"chunk_index": 0})
        ]
    state.documents[second_name] = [
        manager.Document(page_content="second", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, first_name)
    _publish(monkeypatch, chroma_directory, second_name)
    active_retriever = manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )
    manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
    manifest_before = manifest_path.read_bytes()
    state.fail_dimension = failure_mode == "dimension"
    state.fail_known_query = failure_mode == "known-query"

    with pytest.raises(IndexStagingValidationError, match=message):
        manager.rollback_vector_store(
            tenant_id="acme",
            embeddings=_Embeddings(),
        )

    assert manifest_path.read_bytes() == manifest_before
    assert (
        manager.get_retriever(
            tenant_id="acme",
            persist_directory=chroma_directory,
            embeddings=_Embeddings(),
        )
        is active_retriever
    )
    assert state.deleted_names == []


def test_corrupt_manifest_fails_closed_even_with_cached_retriever(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb.index_manifest import IndexManifestCorrupt, index_manifest_path

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    manager = _configure_manager(monkeypatch, chroma_directory, state)
    active_name = "rag_docs-v-acme-1111111111111111"
    state.documents[active_name] = [
        manager.Document(page_content="active", metadata={"chunk_index": 0})
    ]
    _publish(monkeypatch, chroma_directory, active_name)
    manager.get_retriever(
        tenant_id="acme",
        persist_directory=chroma_directory,
        embeddings=_Embeddings(),
    )
    index_manifest_path("acme", chroma_directory=chroma_directory).write_text(
        "{",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(IndexManifestCorrupt):
        manager.get_retriever(
            tenant_id="acme",
            persist_directory=chroma_directory,
            embeddings=_Embeddings(),
        )


def test_api_startup_opens_the_manifest_active_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app

    chroma_directory = tmp_path / "vectordb" / "chroma"
    chroma_directory.mkdir(parents=True)
    (chroma_directory / "chroma.sqlite3").touch()
    state = _FakeChromaState()
    active_name = "rag_docs-v-default-1111111111111111"

    with _held_tenant_lock(monkeypatch, "default") as lock_token:
        from vectordb.index_manifest import publish_active_collection

        publish_active_collection(
            "default",
            active_name,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    monkeypatch.setattr(api_app, "get_settings", lambda: _settings(chroma_directory))
    monkeypatch.setattr(api_app, "_Chroma", _fake_chroma(state))
    monkeypatch.setattr(api_app, "_get_embeddings", _Embeddings)
    monkeypatch.setattr(api_app, "_get_retriever", lambda *args, **kwargs: object())
    monkeypatch.setattr(api_app, "_vector_store", None)
    monkeypatch.setattr(api_app, "_retriever", None)
    monkeypatch.setattr(api_app, "_chunks", None)

    api_app.initialize_vector_store()

    assert state.opened_names == [active_name]


@pytest.mark.asyncio
async def test_api_session_resolution_does_not_fall_back_to_stale_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    import api.app as api_app

    def _fail_retriever(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("active index unavailable")

    monkeypatch.setattr(api_app, "_db_retry_after", float("inf"))
    monkeypatch.setattr(api_app, "_retriever", object())
    monkeypatch.setattr(api_app, "_vector_store", object())
    monkeypatch.setattr(api_app, "_get_retriever", _fail_retriever)
    monkeypatch.setattr(api_app, "_ConversationSession", None)
    monkeypatch.setattr(api_app, "_session_llm_state", {})

    with pytest.raises(HTTPException) as exc_info:
        await api_app._get_or_create_session(None, tenant_id="acme")

    assert exc_info.value.status_code == 503

from __future__ import annotations

import io
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
}


def _token(tenant: str = "default", role: str = "admin") -> dict[str, str]:
    token = create_access_token("tenant-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def test_collection_name_sanitizes_special_chars() -> None:
    from vectordb.manager import _collection_name

    assert _collection_name("acme-corp") == "rag_docs_acme-corp"
    unsafe = _collection_name("evil; DROP TABLE")
    assert re.fullmatch(r"rag_docs_evil__DROP_TABLE--[0-9a-f]{16}", unsafe)
    assert _collection_name("") == "rag_docs_default"


def test_collection_name_truncates_long_tenant() -> None:
    from vectordb.manager import _collection_name

    result = _collection_name("x" * 100)

    assert len(result) <= 63


def test_collection_names_resist_lossy_and_truncation_collisions() -> None:
    from vectordb.manager import _collection_name, _factcard_collection_name

    for name_factory in (_collection_name, _factcard_collection_name):
        slash = name_factory("a/b")
        question = name_factory("a?b")
        assert slash != question
        assert len(slash) <= 63
        assert len(question) <= 63

        long_a = name_factory(f"{'x' * 100}a")
        long_b = name_factory(f"{'x' * 100}b")
        assert long_a != long_b
        assert len(long_a) <= 63
        assert len(long_b) <= 63


def test_upload_directories_use_the_same_collision_resistant_component(
    tmp_path: Path,
) -> None:
    from api.routers.upload import _tenant_upload_directory
    from utils.tenant_naming import physical_tenant_component

    upload_root = tmp_path / "uploads"
    assert _tenant_upload_directory(upload_root, "default") == upload_root
    assert _tenant_upload_directory(upload_root, "acme-corp") == upload_root / "acme-corp"

    slash = _tenant_upload_directory(upload_root, "a/b")
    question = _tenant_upload_directory(upload_root, "a?b")
    assert slash != question
    assert slash.parent == upload_root
    assert question.parent == upload_root
    assert slash.name == physical_tenant_component("a/b", max_length=63)
    assert question.name == physical_tenant_component("a?b", max_length=63)
    assert re.fullmatch(r"a_b--[0-9a-f]{16}", slash.name)


def test_physical_names_resist_casefold_and_windows_device_collisions() -> None:
    from utils.tenant_naming import physical_tenant_component

    lower = physical_tenant_component("acme", max_length=63)
    mixed = physical_tenant_component("Acme", max_length=63)
    assert lower == "acme"
    assert lower.casefold() != mixed.casefold()
    assert re.fullmatch(r"Acme--[0-9a-f]{16}", mixed)

    reserved = physical_tenant_component("con", max_length=63)
    assert reserved.casefold() != "con"
    assert re.fullmatch(r"con--[0-9a-f]{16}", reserved)


def test_reindex_resolves_explicit_tenant_and_rejects_ambiguous_hashed_all(
    tmp_path: Path,
) -> None:
    from scripts import reindex
    from utils.tenant_naming import physical_tenant_component

    upload_root = tmp_path / "uploads"
    component = physical_tenant_component("a/b", max_length=63)
    assert reindex._upload_dir_for_tenant(upload_root, "a/b") == upload_root / component

    (upload_root / component).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="--tenant"):
        reindex._iter_tenants(upload_root)


def test_factcard_default_cache_uses_physical_tenant_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import build_factcards
    from utils.tenant_naming import physical_tenant_component

    monkeypatch.setattr(build_factcards, "PROJECT_ROOT", tmp_path)
    args = types.SimpleNamespace(cards_json=None, tenant="a/b")
    component = physical_tenant_component("a/b", max_length=63)

    assert build_factcards._cards_cache_path(args) == (
        tmp_path / ".tmp" / f"factcards_{component}_cards.json"
    )


def test_two_tenants_get_different_retrievers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from vectordb import manager

    calls: list[str] = []

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            calls.append(kwargs["collection_name"])

        def as_retriever(self, **kwargs):
            return f"retriever_for_{self.kwargs['collection_name']}"

    monkeypatch.setattr(manager, "Chroma", FakeChroma, raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: None)
    manager.reset_retriever_cache()

    chroma_directory = tmp_path / "vectordb" / "chroma"
    acme = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=None,
        tenant_id="acme",
    )
    mega = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=None,
        tenant_id="megacorp",
    )

    assert acme != mega
    assert calls == ["rag_docs_acme", "rag_docs_megacorp"]


def test_retriever_is_cached_per_tenant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from vectordb import manager

    call_count = {"count": 0}

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            call_count["count"] += 1

        def as_retriever(self, **kwargs):
            return object()

    monkeypatch.setattr(manager, "Chroma", FakeChroma, raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: None)
    manager.reset_retriever_cache()

    chroma_directory = tmp_path / "vectordb" / "chroma"
    first = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=None,
        tenant_id="acme",
    )
    second = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=None,
        tenant_id="acme",
    )

    assert first is second
    assert call_count["count"] == 1


def test_build_store_invalidates_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from vectordb import manager

    docs = [manager.Document(page_content="Tenant specific content", metadata={})]
    splitter = Mock()
    splitter.split_documents.return_value = docs

    class _Embeddings:
        def embed_query(self, text: str) -> list[float]:
            assert text
            return [0.0, 0.0, 0.0]

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.documents = list(kwargs.pop("documents", []))
            self._collection = self

        @classmethod
        def from_documents(cls, **kwargs):
            return cls(**kwargs)

        def persist(self) -> None:
            return None

        def count(self) -> int:
            return len(self.documents)

        def query(self, **kwargs):
            _ = kwargs
            return {"ids": [["chunk"]]}

        def similarity_search(self, query: str, *, k: int):
            _ = query
            return self.documents[:k]

        def delete_collection(self) -> None:
            return None

        def as_retriever(self, **kwargs):
            return object()

    chroma_directory = tmp_path / "vectordb" / "chroma"
    monkeypatch.setattr(manager, "Chroma", FakeChroma, raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: _Embeddings())
    monkeypatch.setattr(manager, "get_settings", lambda: SimpleNamespace(
        vector_backend="chroma",
        vectordb_chroma_dir=chroma_directory,
        vectordb_collection_prefix="rag_docs",
        chunk_size=800,
        chunk_overlap=200,
        contextual_headers=False,
        rag_device="cpu",
        vectordb_retention_max_versions=2,
    ))
    monkeypatch.setattr(manager._base_manager, "select_chunks", lambda *args, **kwargs: docs)
    manager.reset_retriever_cache()

    first = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=_Embeddings(),
        tenant_id="acme",
    )
    manager.build_vector_store(
        docs,
        {"chunk_size": 800, "chunk_overlap": 200},
        embeddings=None,
        tenant_id="acme",
    )
    second = manager.get_retriever(
        persist_directory=str(chroma_directory),
        embeddings=None,
        tenant_id="acme",
    )

    assert first is not second


def test_ask_endpoint_passes_tenant_to_session_resolution(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    captured: dict[str, str] = {}

    class FakeSession:
        def __init__(self):
            self._retriever = object()

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default", **kwargs):
            return {
                "answer": question,
                "quality_score": 90,
                "route": "auto",
                "sources": [],
                "trace_id": trace_id or "",
                "suggested_questions": [],
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        captured["tenant_id"] = tenant_id
        return "00000000000000000000000000000001", FakeSession()

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client_with_key.post(
        "/api/ask",
        json={"question": "How are tenant docs isolated?"},
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    assert captured["tenant_id"] == "acme"


def test_upload_uses_tenant_specific_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    captured: dict[str, object] = {}

    class FakeLoader:
        def __init__(self, recursive: bool = False):
            self.recursive = recursive

        def load_documents(self, path: str):
            captured["load_path"] = path
            return [{"page_content": "doc", "metadata": {"source": "file.txt"}}]

    def _fake_rebuild(docs, tenant_id: str = "default") -> bool:
        captured["tenant_id"] = tenant_id
        captured["docs"] = docs
        return True

    async def _fake_log_audit(**kwargs) -> None:
        return None

    def _raise_celery(*args, **kwargs):
        raise RuntimeError("celery disabled for test")

    fake_ingest_task = types.ModuleType("tasks.ingest_task")
    fake_ingest_task.ingest_document = types.SimpleNamespace(delay=_raise_celery)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_ingest_task)

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _fake_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client_with_key.post(
        "/api/upload",
        files={"file": ("guide.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=_token("acme-corp", "admin"),
    )

    assert response.status_code == 200
    assert captured["tenant_id"] == "acme-corp"
    assert response.json()["tenant_id"] == "acme-corp"
    assert "job_id" in response.json()


def test_get_retriever_rejects_active_chroma_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Fail-fast when active Chroma vectors disagree with embedder dimension.

    Tenant runtime must reject a 3D legacy collection against a 1024D embedder
    before chunk restore, retriever construction, or any cache population, and
    without calling the embedder or mutating the collection.
    """
    from vectordb import manager

    class TrackingEmbeddings:
        embedding_dimension = 1024
        embed_query_calls = 0
        embed_documents_calls = 0

        def embed_query(self, text: str) -> list[float]:
            self.embed_query_calls += 1
            raise AssertionError("embed_query must not be called on dimension guard")

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.embed_documents_calls += 1
            raise AssertionError("embed_documents must not be called on dimension guard")

    class TrackingCollection:
        def __init__(self) -> None:
            self.get_calls: list[dict[str, object]] = []
            self.mutation_calls = 0

        def count(self) -> int:
            return 1

        def get(self, *args: object, **kwargs: object) -> dict[str, object]:
            self.get_calls.append(dict(kwargs))
            return {"embeddings": [[0.1, 0.2, 0.3]]}

        def delete(self, *args: object, **kwargs: object) -> None:
            self.mutation_calls += 1

        def delete_collection(self) -> None:
            self.mutation_calls += 1

        def update(self, *args: object, **kwargs: object) -> None:
            self.mutation_calls += 1

        def add(self, *args: object, **kwargs: object) -> None:
            self.mutation_calls += 1

        def upsert(self, *args: object, **kwargs: object) -> None:
            self.mutation_calls += 1

    class TrackingStore:
        def __init__(self) -> None:
            self._collection = TrackingCollection()
            self.as_retriever_calls = 0

        def as_retriever(self, **kwargs: object) -> object:
            self.as_retriever_calls += 1
            raise AssertionError("as_retriever must not be called on dimension mismatch")

    embeddings = TrackingEmbeddings()
    store = TrackingStore()
    base_retriever_calls = {"count": 0}
    restore_calls = {"count": 0}

    def _boom_base_retriever(*args: object, **kwargs: object) -> object:
        base_retriever_calls["count"] += 1
        raise AssertionError("base get_retriever must not run on dimension mismatch")

    def _boom_restore(*args: object, **kwargs: object) -> list:
        restore_calls["count"] += 1
        raise AssertionError("chunk restore must not run on dimension mismatch")

    chroma_directory = tmp_path / "vectordb" / "chroma"
    chroma_directory.mkdir(parents=True)
    monkeypatch.setattr(
        manager,
        "get_settings",
        lambda: SimpleNamespace(
            vector_backend="chroma",
            vectordb_chroma_dir=chroma_directory,
            vectordb_collection_prefix="rag_docs",
        ),
    )
    monkeypatch.setattr(manager._base_manager, "get_retriever", _boom_base_retriever)
    monkeypatch.setattr(manager, "_restore_chunks_from_store", _boom_restore)
    manager.reset_retriever_cache()
    # A prior partial cache state with the same resolved index key must also be
    # cleared if the compatibility guard rejects the active collection.
    manager._chunks_cache["default"] = []
    manager._store_cache["default"] = object()
    manager._index_cache_keys["default"] = (
        str(chroma_directory.resolve()),
        "rag_docs_default",
        0,
    )

    with pytest.raises(manager.ActiveCollectionEmbeddingDimensionMismatch) as exc_info:
        manager.get_retriever(
            vector_store=store,
            embeddings=embeddings,
            tenant_id="default",
            persist_directory=str(chroma_directory),
        )

    message = str(exc_info.value)
    assert "default" in message
    assert "rag_docs_default" in message
    assert "3" in message
    assert "1024" in message
    assert "rebuild" in message.lower()

    assert embeddings.embed_query_calls == 0
    assert embeddings.embed_documents_calls == 0
    assert base_retriever_calls["count"] == 0
    assert restore_calls["count"] == 0
    assert store.as_retriever_calls == 0
    assert store._collection.mutation_calls == 0
    assert "default" not in manager._retriever_cache
    assert "default" not in manager._chunks_cache
    assert "default" not in manager._store_cache
    assert "default" not in manager._index_cache_keys
    # Read-only probe: one stored embedding only.
    assert store._collection.get_calls
    assert store._collection.get_calls[0].get("limit") == 1
    assert store._collection.get_calls[0].get("include") == ["embeddings"]

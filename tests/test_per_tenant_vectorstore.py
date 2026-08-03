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

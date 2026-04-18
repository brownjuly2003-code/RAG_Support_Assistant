from __future__ import annotations

import io
import sys
import types

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock

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
    assert _collection_name("evil; DROP TABLE") == "rag_docs_evil__DROP_TABLE"
    assert _collection_name("") == "rag_docs_default"


def test_collection_name_truncates_long_tenant() -> None:
    from vectordb.manager import _collection_name

    result = _collection_name("x" * 100)

    assert len(result) <= 63


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

    acme = manager.get_retriever(
        persist_directory=str(tmp_path),
        embeddings=None,
        tenant_id="acme",
    )
    mega = manager.get_retriever(
        persist_directory=str(tmp_path),
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

    first = manager.get_retriever(
        persist_directory=str(tmp_path),
        embeddings=None,
        tenant_id="acme",
    )
    second = manager.get_retriever(
        persist_directory=str(tmp_path),
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

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_documents(cls, **kwargs):
            instance = cls(**kwargs)
            instance.persist = lambda: None
            return instance

        def as_retriever(self, **kwargs):
            return object()

    monkeypatch.setattr(manager, "Chroma", FakeChroma, raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: None)
    monkeypatch.setattr(manager._base_manager, "_build_text_splitter", lambda *args, **kwargs: splitter)
    manager.reset_retriever_cache()

    first = manager.get_retriever(
        persist_directory=str(tmp_path),
        embeddings=None,
        tenant_id="acme",
    )
    manager.build_vector_store(
        docs,
        {"chunk_size": 800, "chunk_overlap": 200},
        embeddings=None,
        tenant_id="acme",
    )
    second = manager.get_retriever(
        persist_directory=str(tmp_path),
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

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default"):
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

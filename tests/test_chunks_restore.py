"""Chunk restore after process restart (fable_com.md F-2).

The BM25 corpus and parent-expansion neighbour order live in
``vectordb.manager._chunks_cache``. Before the F-2 fix, a process restart left
the cache empty and the first ``get_retriever`` call built a retriever without
BM25 — silent degradation to vector-only. These tests pin the restore path:
chunks come back from the persisted Chroma collection, ordered by the
``chunk_index`` metadata stamped at build time.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from config.settings import get_settings
from vectordb import manager


@pytest.fixture(autouse=True)
def _no_heavy_models(monkeypatch: pytest.MonkeyPatch):
    # reranker_model is an import-time settings default; patch the singleton
    # so get_reranker() never tries to download a real CrossEncoder. Embeddings
    # are likewise stubbed — get_retriever(embeddings=None) would otherwise
    # load the real SentenceTransformer.
    monkeypatch.setattr(get_settings(), "reranker_model", "", raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: object())
    manager.reset_retriever_cache()
    yield
    manager.reset_retriever_cache()


class FakeCollection:
    def __init__(self, texts: list[str], metadatas: list[dict]):
        self._texts = texts
        self._metadatas = metadatas

    def get(self, include=None):
        return {"documents": list(self._texts), "metadatas": list(self._metadatas)}


class FakeChroma:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._collection = kwargs.pop("collection", None)

    def as_retriever(self, **kwargs):
        return object()

    def similarity_search(self, query: str, k: int = 5):
        return []


def test_get_retriever_restores_chunks_and_bm25(monkeypatch: pytest.MonkeyPatch) -> None:
    texts = ["section B", "section A", "section C"]
    metadatas = [
        {"source": "doc.md", "chunk_index": 1},
        {"source": "doc.md", "chunk_index": 0},
        {"source": "doc.md", "chunk_index": 2},
    ]
    store = FakeChroma(collection_name="rag_docs_acme")
    store._collection = FakeCollection(texts, metadatas)

    retriever = manager.get_retriever(vector_store=store, tenant_id="acme")

    cached = manager._chunks_cache.get("acme")
    assert cached is not None, "restored chunks must repopulate the cache"
    assert [c.page_content for c in cached] == ["section A", "section B", "section C"]
    # BM25 index is built from the restored chunks (hybrid is back).
    assert getattr(retriever, "_bm25", None) is not None


def test_restore_legacy_collection_keeps_sources_contiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Legacy collection: no chunk_index. Interleaved sources must come back
    # grouped per source with their relative order preserved (stable sort).
    texts = ["b1", "a1", "b2", "a2"]
    metadatas = [
        {"source": "b.md"},
        {"source": "a.md"},
        {"source": "b.md"},
        {"source": "a.md"},
    ]
    store = FakeChroma(collection_name="rag_docs_legacy")
    store._collection = FakeCollection(texts, metadatas)

    manager.get_retriever(vector_store=store, tenant_id="legacy")

    cached = manager._chunks_cache["legacy"]
    assert [c.page_content for c in cached] == ["a1", "a2", "b1", "b2"]


def test_restore_skipped_for_empty_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeChroma(collection_name="rag_docs_empty")
    store._collection = FakeCollection([], [])

    retriever = manager.get_retriever(vector_store=store, tenant_id="empty")

    assert "empty" not in manager._chunks_cache
    assert getattr(retriever, "_bm25", None) is None


def test_restore_survives_collection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeChroma(collection_name="rag_docs_broken")

    class BrokenCollection:
        def get(self, include=None):
            raise RuntimeError("collection unavailable")

    store._collection = BrokenCollection()

    retriever = manager.get_retriever(vector_store=store, tenant_id="broken")

    assert retriever is not None
    assert "broken" not in manager._chunks_cache


def test_build_vector_store_stamps_chunk_index(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = [
        manager.Document(page_content="first", metadata={"source": "doc.md"}),
        manager.Document(page_content="second", metadata={"source": "doc.md"}),
    ]
    splitter = Mock()
    splitter.split_documents.return_value = list(docs)

    captured: dict[str, list] = {}

    class BuildChroma:
        @classmethod
        def from_documents(cls, documents=None, **kwargs):
            captured["documents"] = list(documents or [])
            instance = cls()
            instance.persist = lambda: None
            return instance

        def as_retriever(self, **kwargs):
            return object()

    monkeypatch.setattr(manager, "Chroma", BuildChroma, raising=False)
    monkeypatch.setattr(manager, "get_embeddings", lambda model_name=None: None)
    monkeypatch.setattr(
        manager._base_manager, "_build_text_splitter", lambda *args, **kwargs: splitter
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "structural_chunking", False, raising=False)
    monkeypatch.setattr(settings, "semantic_chunking", False, raising=False)
    monkeypatch.setattr(settings, "contextual_headers", False, raising=False)

    _store, chunks = manager.build_vector_store(
        docs,
        {"chunk_size": 800, "chunk_overlap": 200},
        embeddings=None,
        tenant_id="stamped",
    )

    assert [c.metadata.get("chunk_index") for c in chunks] == [0, 1]
    assert [c.metadata.get("chunk_index") for c in captured["documents"]] == [0, 1]


def test_bm25_gauge_reports_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    from monitoring import prometheus as prom

    recorded: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        prom,
        "set_retriever_bm25_enabled",
        lambda tenant, enabled: recorded.append((tenant, enabled)),
    )

    store = FakeChroma(collection_name="rag_docs_gauge")
    store._collection = FakeCollection([], [])
    manager.get_retriever(vector_store=store, tenant_id="gauge")

    assert recorded == [("gauge", False)]

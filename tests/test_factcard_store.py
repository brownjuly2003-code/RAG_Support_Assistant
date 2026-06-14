"""F2: fact-card vector collection builder (adaptive-retrieval Track F).

Windows-safe: a fake Chroma class and a sentinel embeddings object stand in for
the real backend, so nothing is embedded or downloaded here. The real embed run
happens on Mac via scripts/build_factcards.py.
"""
from __future__ import annotations

from typing import ClassVar

import pytest

from vectordb import _base_manager, manager

Document = _base_manager.Document


class _FakeStore:
    def __init__(self, documents: list, collection_name: str) -> None:
        self.documents = list(documents)
        self.collection_name = collection_name
        self.persisted = False

    def persist(self) -> None:
        self.persisted = True

    def similarity_search(self, query: str, k: int = 3) -> list:
        return self.documents[:k]


class _FakeChroma:
    deleted: ClassVar[list[str]] = []
    last: ClassVar[_FakeStore | None] = None
    seeded: ClassVar[list] = []  # docs returned by instance.similarity_search (F3 read path)

    def __init__(self, persist_directory=None, embedding_function=None, collection_name=None):
        self.collection_name = collection_name

    def delete_collection(self) -> None:
        _FakeChroma.deleted.append(self.collection_name)

    def similarity_search(self, query: str, k: int = 3) -> list:
        return _FakeChroma.seeded[:k]

    @classmethod
    def from_documents(cls, documents, embedding, persist_directory, collection_name):
        store = _FakeStore(documents, collection_name)
        cls.last = store
        return store


@pytest.fixture
def fake_chroma(monkeypatch):
    _FakeChroma.deleted = []
    _FakeChroma.last = None
    _FakeChroma.seeded = []
    monkeypatch.setattr(manager, "_get_chroma", lambda: _FakeChroma)
    return _FakeChroma


def _card_doc(topic: str, fields: list[str]) -> object:
    return Document(
        page_content=f"topic: {topic}\nfields: " + ", ".join(fields),
        metadata={"type": "factcard", "topic": topic, "source": f"{topic}.md"},
    )


def test_build_factcard_store_stores_cards_whole(fake_chroma):
    docs = [_card_doc("customs_clearance", ["declaration_number", "customs_code"])]
    store = manager.build_factcard_store(docs, embeddings=object(), tenant_id="default")
    # one card in -> one document stored, content intact (no chunking).
    assert len(store.documents) == 1
    assert "declaration_number" in store.documents[0].page_content
    assert store.persisted is True
    # rebuilt collection name follows the <prefix>_<tenant>_factcards shape.
    assert store.collection_name.endswith("_default_factcards")
    # delete-then-rebuild: the existing collection was cleared first.
    assert store.collection_name in fake_chroma.deleted


def test_build_factcard_store_rejects_empty():
    with pytest.raises(ValueError):
        manager.build_factcard_store([], embeddings=object())


def test_factcard_collection_name_respects_chroma_limit():
    name = manager._factcard_collection_name("t" * 200)
    assert len(name) <= 63
    assert name.endswith("_factcards")


# --- F3: read path ---------------------------------------------------------


def test_get_factcard_documents_returns_cards(fake_chroma):
    fake_chroma.seeded = [_card_doc("customs_clearance", ["declaration_number", "customs_code"])]
    docs = manager.get_factcard_documents("какие поля нужны", embeddings=object(), k=3)
    assert len(docs) == 1
    assert "declaration_number" in docs[0].page_content


def test_get_factcard_documents_blank_query_returns_empty(fake_chroma):
    fake_chroma.seeded = [_card_doc("x", ["y"])]
    assert manager.get_factcard_documents("   ", embeddings=object()) == []


def test_get_factcard_documents_swallows_backend_error(fake_chroma, monkeypatch):
    def _boom(self, query, k=3):  # noqa: ANN001
        raise RuntimeError("backend down")

    monkeypatch.setattr(_FakeChroma, "similarity_search", _boom)
    fake_chroma.seeded = [_card_doc("x", ["y"])]
    # Errors degrade to [] so F4 can fall back to the hybrid lane.
    assert manager.get_factcard_documents("q", embeddings=object()) == []

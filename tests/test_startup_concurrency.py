from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest


def test_initialize_vector_store_is_single_flight_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.app as api_app

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    (chroma_dir / "index.bin").write_text("x", encoding="utf-8")

    settings = SimpleNamespace(
        vectordb_chroma_dir=chroma_dir,
        vectordb_collection_prefix="rag_docs",
    )
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    counts = {
        "embeddings": 0,
        "chroma": 0,
        "retriever": 0,
    }
    lock = threading.Lock()

    def _fake_embeddings():
        time.sleep(0.05)
        with lock:
            counts["embeddings"] += 1
        return "embeddings"

    class _FakeChroma:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            with lock:
                counts["chroma"] += 1

        def as_retriever(self, search_kwargs=None):
            _ = search_kwargs
            return "retriever"

    def _fake_get_retriever(store, chunks=None, tenant_id=None):
        _ = store, chunks, tenant_id
        with lock:
            counts["retriever"] += 1
        return "retriever"

    monkeypatch.setattr(api_app, "_vector_store", None, raising=False)
    monkeypatch.setattr(api_app, "_retriever", None, raising=False)
    monkeypatch.setattr(api_app, "_chunks", [], raising=False)
    monkeypatch.setattr(api_app, "_get_embeddings", _fake_embeddings, raising=False)
    monkeypatch.setattr(api_app, "_Chroma", _FakeChroma, raising=False)
    monkeypatch.setattr(api_app, "_get_retriever", _fake_get_retriever, raising=False)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: api_app.initialize_vector_store(), range(4)))

    assert counts == {
        "embeddings": 1,
        "chroma": 1,
        "retriever": 1,
    }


def test_initialize_vector_store_skips_incompatible_chroma_embeddings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import api.app as api_app

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    (chroma_dir / "index.bin").write_text("x", encoding="utf-8")

    settings = SimpleNamespace(
        embedding_model="BAAI/bge-m3",
        vectordb_chroma_dir=chroma_dir,
        vectordb_collection_prefix="rag_docs",
    )
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    counts = {"retriever": 0}

    class _Embeddings:
        def embed_query(self, text: str) -> list[float]:
            _ = text
            return [0.0] * 1024

    class _Collection:
        def count(self) -> int:
            return 1

        def query(self, **kwargs) -> None:
            _ = kwargs
            raise ValueError("Collection expecting embedding with dimension of 3, got 1024")

    class _FakeChroma:
        _collection = _Collection()

        def __init__(self, **kwargs) -> None:
            _ = kwargs

    def _fake_get_retriever(store, chunks=None, tenant_id=None):
        _ = store, chunks, tenant_id
        counts["retriever"] += 1
        return "retriever"

    monkeypatch.setattr(api_app, "_vector_store", None, raising=False)
    monkeypatch.setattr(api_app, "_retriever", None, raising=False)
    monkeypatch.setattr(api_app, "_chunks", [], raising=False)
    monkeypatch.setattr(api_app, "_get_embeddings", lambda: _Embeddings(), raising=False)
    monkeypatch.setattr(api_app, "_Chroma", _FakeChroma, raising=False)
    monkeypatch.setattr(api_app, "_get_retriever", _fake_get_retriever, raising=False)

    caplog.set_level("ERROR", logger="api.app")

    api_app.initialize_vector_store()

    assert api_app._vector_store is None
    assert api_app._retriever is None
    assert counts["retriever"] == 0
    assert "incompatible with embedding model BAAI/bge-m3" in caplog.text


def test_session_setup_does_not_reopen_store_rejected_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.app as api_app

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    (chroma_dir / "index.bin").write_text("incompatible", encoding="utf-8")
    calls = {"retriever": 0}

    def _fake_get_retriever(*args, **kwargs):
        _ = args, kwargs
        calls["retriever"] += 1
        return object()

    monkeypatch.setattr(api_app, "_db_retry_after", float("inf"))
    monkeypatch.setattr(api_app, "_session_llm_state", {})
    monkeypatch.setattr(api_app, "_session_last_access", {})
    monkeypatch.setattr(api_app, "_vector_store", None)
    monkeypatch.setattr(api_app, "_retriever", None)
    monkeypatch.setattr(api_app, "_get_retriever", _fake_get_retriever)
    monkeypatch.setattr(api_app, "_ConversationSession", None)
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: SimpleNamespace(vectordb_chroma_dir=chroma_dir),
    )

    _, session = asyncio.run(api_app._get_or_create_session(None, "default"))

    assert calls["retriever"] == 0
    assert session == {"history": [], "tenant_id": "default"}

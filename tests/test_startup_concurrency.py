from __future__ import annotations

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

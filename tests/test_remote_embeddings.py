from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from vectordb import _base_manager as manager


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _fake_post_factory(calls: list[dict[str, object]]):
    def _fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        calls.append({"url": url, "json": json, "headers": headers})
        inputs = (json or {}).get("input") or []
        # echo back a 3-dim vector per input, shuffled index order to prove sorting
        data = [
            {"index": len(inputs) - 1 - i, "embedding": [float(i + 1), 2.0, 3.0]}
            for i in range(len(inputs))
        ]
        return _FakeResponse({"data": data})

    return _fake_post


def test_remote_embeddings_batches_normalizes_and_orders(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("httpx.post", _fake_post_factory(calls))

    emb = manager._RemoteEmbeddings(
        url="https://example/v1/embeddings",
        model="mistral-embed",
        api_key="secret",
        batch_size=2,
        timeout_sec=10.0,
    )

    vectors = emb.embed_documents(["a", "b", "c"])

    # 3 inputs, batch_size 2 -> two POSTs
    assert len(calls) == 2
    assert calls[0]["json"]["input"] == ["a", "b"]
    assert calls[1]["json"]["input"] == ["c"]
    # order preserved despite shuffled API index
    assert len(vectors) == 3
    # all vectors L2-normalized
    for vec in vectors:
        assert math.isclose(math.sqrt(sum(c * c for c in vec)), 1.0, rel_tol=1e-9)
    # bearer auth header set, key not leaked into url
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"


def test_remote_embeddings_query_returns_single_vector(monkeypatch) -> None:
    monkeypatch.setattr("httpx.post", _fake_post_factory([]))
    emb = manager._RemoteEmbeddings(
        url="u", model="m", api_key="k", batch_size=32, timeout_sec=5.0
    )
    vec = emb.embed_query("hello")
    assert isinstance(vec, list) and len(vec) == 3


def test_build_remote_embeddings_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    settings = SimpleNamespace(
        embedding_remote_api_key_env="MISTRAL_API_KEY",
        embedding_remote_url="u",
        embedding_remote_model="m",
        embedding_remote_batch=32,
        embedding_remote_timeout_sec=60.0,
    )
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY is required"):
        manager._build_remote_embeddings(settings)


def test_get_embeddings_selects_remote_backend(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "secret")
    monkeypatch.setattr(manager, "_cached_embeddings", None, raising=False)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            embedding_backend="remote",
            embedding_remote_api_key_env="MISTRAL_API_KEY",
            embedding_remote_url="https://example/v1/embeddings",
            embedding_remote_model="mistral-embed",
            embedding_remote_batch=32,
            embedding_remote_timeout_sec=60.0,
            embedding_model="BAAI/bge-m3",
        ),
        raising=False,
    )
    try:
        emb = manager.get_embeddings()
        assert isinstance(emb, manager._RemoteEmbeddings)
    finally:
        manager._cached_embeddings = None


def test_remote_embedding_settings_defaults(monkeypatch) -> None:
    for var in (
        "RAG_EMBEDDING_BACKEND",
        "RAG_EMBEDDING_REMOTE_URL",
        "RAG_EMBEDDING_REMOTE_MODEL",
        "RAG_EMBEDDING_REMOTE_API_KEY_ENV",
        "RAG_EMBEDDING_REMOTE_BATCH",
    ):
        monkeypatch.delenv(var, raising=False)
    from config.settings import Settings

    s = Settings()
    assert s.embedding_backend == "local"
    assert s.embedding_remote_model == "mistral-embed"
    assert s.embedding_remote_api_key_env == "MISTRAL_API_KEY"
    assert s.embedding_remote_batch == 32

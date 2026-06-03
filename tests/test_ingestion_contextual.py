from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import vectordb.manager as tenant_manager
from config.settings import Settings
from ingestion.pipeline import IngestPipeline
from llm.providers import LLMResponse
from vectordb import _base_manager as manager


def test_contextual_headers_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("RAG_CONTEXTUAL_HEADERS", raising=False)

    settings = Settings()

    assert settings.contextual_headers is True


def test_ingestion_batch_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("INGESTION_BATCH_ENABLED", raising=False)

    settings = Settings()

    assert settings.ingestion_batch_enabled is False


def test_ingest_pipeline_uses_tenant_vector_store_builder(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {"tenant_called": False, "root_called": False}
    pipeline = IngestPipeline(log_path=tmp_path / "ingestion_log.json")
    pipeline.loader = MagicMock()
    pipeline.loader.load_documents.return_value = [
        manager.Document(page_content="Документ", metadata={"source": "doc.txt"}),
    ]

    def _fake_build_vector_store(docs, chunk_config, **kwargs):
        _ = docs, chunk_config, kwargs
        captured["tenant_called"] = True
        return object(), []

    splitter = MagicMock()
    splitter.split_documents.return_value = []

    def _fake_root_build_chroma(docs, embeddings):
        _ = docs, embeddings
        captured["root_called"] = True
        return object()

    monkeypatch.setattr(tenant_manager, "build_vector_store", _fake_build_vector_store)
    monkeypatch.setattr(manager, "get_embeddings", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(manager, "_build_text_splitter", lambda **kwargs: splitter)
    monkeypatch.setattr(manager, "_build_chroma", _fake_root_build_chroma)

    pipeline.ingest(tmp_path)

    assert captured["tenant_called"] is True
    assert captured["root_called"] is False


def test_build_vector_store_adds_contextual_headers_when_enabled(
    monkeypatch,
    tmp_path,
) -> None:
    docs = [
        tenant_manager.Document(
            page_content="Политика возврата позволяет вернуть товар в течение 14 дней.",
            metadata={"source": "returns.md", "file_path": str(tmp_path / "returns.md")},
        ),
    ]
    split_documents = [
        tenant_manager.Document(
            page_content="Вернуть товар можно в течение 14 дней.",
            metadata={"source": "returns.md", "file_path": str(tmp_path / "returns.md")},
        ),
    ]
    splitter = MagicMock()
    splitter.split_documents.return_value = split_documents

    class FakeStore:
        def persist(self) -> None:
            return None

    class FakeChroma:
        def __init__(self, *args, **kwargs) -> None:
            _ = args, kwargs

        @classmethod
        def from_documents(
            cls,
            documents,
            embedding,
            persist_directory,
            collection_name,
        ):
            _ = embedding, persist_directory, collection_name
            store = FakeStore()
            store.documents = list(documents)
            return store

    monkeypatch.setattr(
        tenant_manager,
        "get_settings",
        lambda: SimpleNamespace(
            vector_backend="chroma",
            semantic_chunking=False,
            contextual_headers=True,
            vectordb_chroma_dir=tmp_path,
            vectordb_collection_prefix="rag_docs",
        ),
    )
    monkeypatch.setattr(tenant_manager, "Chroma", FakeChroma)
    monkeypatch.setattr(tenant_manager._base_manager, "_build_text_splitter", lambda **kwargs: splitter)

    _, chunks = tenant_manager.build_vector_store(
        docs,
        {"chunk_size": 400, "chunk_overlap": 50},
        embeddings=MagicMock(),
        tenant_id="acme",
    )

    assert chunks[0].page_content.startswith("[Контекст:")
    assert chunks[0].metadata["has_context_header"] is True


def test_build_vector_store_skips_contextual_headers_when_disabled(
    monkeypatch,
    tmp_path,
) -> None:
    docs = [
        tenant_manager.Document(
            page_content="Доставка в Москву занимает 2-3 дня.",
            metadata={"source": "shipping.md", "file_path": str(tmp_path / "shipping.md")},
        ),
    ]
    split_documents = [
        tenant_manager.Document(
            page_content="Доставка в Москву занимает 2-3 дня.",
            metadata={"source": "shipping.md", "file_path": str(tmp_path / "shipping.md")},
        ),
    ]
    splitter = MagicMock()
    splitter.split_documents.return_value = split_documents

    class FakeStore:
        def persist(self) -> None:
            return None

    class FakeChroma:
        def __init__(self, *args, **kwargs) -> None:
            _ = args, kwargs

        @classmethod
        def from_documents(
            cls,
            documents,
            embedding,
            persist_directory,
            collection_name,
        ):
            _ = embedding, persist_directory, collection_name
            store = FakeStore()
            store.documents = list(documents)
            return store

    monkeypatch.setattr(
        tenant_manager,
        "get_settings",
        lambda: SimpleNamespace(
            vector_backend="chroma",
            semantic_chunking=False,
            contextual_headers=False,
            vectordb_chroma_dir=tmp_path,
            vectordb_collection_prefix="rag_docs",
        ),
    )
    monkeypatch.setattr(tenant_manager, "Chroma", FakeChroma)
    monkeypatch.setattr(tenant_manager._base_manager, "_build_text_splitter", lambda **kwargs: splitter)

    _, chunks = tenant_manager.build_vector_store(
        docs,
        {"chunk_size": 400, "chunk_overlap": 50},
        embeddings=MagicMock(),
        tenant_id="acme",
    )

    assert not chunks[0].page_content.startswith("[Контекст:")
    assert "has_context_header" not in chunks[0].metadata


def test_ingest_pipeline_uses_provider_batch_for_contextual_headers(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}
    pipeline = IngestPipeline(log_path=tmp_path / "ingestion_log.json")
    pipeline.loader = MagicMock()
    pipeline.loader.load_documents.return_value = [
        manager.Document(page_content="Правила возврата для магазина.", metadata={"source": "returns.md"}),
    ]

    class _BatchLLM:
        provider_id = "gracekelly"
        model_name = "claude-sonnet-4-6-api"
        supports_batch = True

        def generate_batch(self, batches, **kwargs):
            captured["batches"] = batches
            captured["kwargs"] = kwargs
            return [
                LLMResponse(
                    text="Batch header",
                    provider=self.provider_id,
                    model=self.model_name,
                )
            ]

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            chunk_size=400,
            chunk_overlap=50,
            contextual_headers=True,
            ingestion_batch_enabled=True,
        ),
    )
    monkeypatch.setattr(
        "llm.providers.build_provider_runtime",
        lambda settings: SimpleNamespace(strong=_BatchLLM(), fast=_BatchLLM()),
    )

    def _fake_build_vector_store(docs, chunk_config, **kwargs):
        captured["docs"] = list(docs)
        _ = chunk_config, kwargs
        return object(), []

    monkeypatch.setattr(tenant_manager, "build_vector_store", _fake_build_vector_store)

    pipeline.ingest(tmp_path, tenant_id="acme")

    assert captured["batches"]
    assert captured["docs"][0].page_content.startswith("[Контекст: Batch header]")


def test_ingest_pipeline_falls_back_to_sequential_headers_when_batch_unsupported(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {"calls": 0}
    pipeline = IngestPipeline(log_path=tmp_path / "ingestion_log.json")
    pipeline.loader = MagicMock()
    pipeline.loader.load_documents.return_value = [
        manager.Document(page_content="Условия доставки в Москву.", metadata={"source": "shipping.md"}),
    ]

    class _SequentialLLM:
        provider_id = "ollama"
        model_name = "qwen2.5:7b"
        supports_batch = False

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            captured["calls"] = int(captured["calls"]) + 1
            return LLMResponse(
                text="Sequential header",
                provider=self.provider_id,
                model=self.model_name,
            )

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            chunk_size=400,
            chunk_overlap=50,
            contextual_headers=True,
            ingestion_batch_enabled=True,
        ),
    )
    monkeypatch.setattr(
        "llm.providers.build_provider_runtime",
        lambda settings: SimpleNamespace(strong=_SequentialLLM(), fast=_SequentialLLM()),
    )

    def _fake_build_vector_store(docs, chunk_config, **kwargs):
        captured["docs"] = list(docs)
        _ = chunk_config, kwargs
        return object(), []

    monkeypatch.setattr(tenant_manager, "build_vector_store", _fake_build_vector_store)

    pipeline.ingest(tmp_path, tenant_id="acme")

    assert captured["calls"] == 1
    assert captured["docs"][0].page_content.startswith("[Контекст: Sequential header]")

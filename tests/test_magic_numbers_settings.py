from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import agent.graph as agent_graph
from vectordb import _base_manager as manager
import vectordb.manager as tenant_manager
from ingestion.pipeline import IngestPipeline


def test_ingest_pipeline_uses_settings_chunk_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}
    pipeline = IngestPipeline(log_path=tmp_path / "ingestion_log.json")
    pipeline.loader = MagicMock()
    pipeline.loader.load_documents.return_value = [
        manager.Document(page_content="Документ", metadata={}),
    ]

    def _fake_build_vector_store(docs, chunk_config, **kwargs):
        _ = docs, kwargs
        captured["chunk_config"] = dict(chunk_config)
        return object(), []

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=321, chunk_overlap=123),
    )
    monkeypatch.setattr(manager, "build_vector_store", _fake_build_vector_store)

    pipeline.ingest(tmp_path)

    assert captured["chunk_config"] == {"chunk_size": 321, "chunk_overlap": 123}


def test_tenant_vector_store_uses_settings_chunk_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}
    docs = [tenant_manager.Document(page_content="Первый. Второй.", metadata={})]
    embeddings = MagicMock()
    split_documents = [
        tenant_manager.Document(page_content="Chunk", metadata={}),
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
            captured["documents"] = list(documents)
            return FakeStore()

    def _fake_splitter(*, chunk_size: int, chunk_overlap: int):
        captured["chunk_size"] = chunk_size
        captured["chunk_overlap"] = chunk_overlap
        return splitter

    monkeypatch.setattr(
        tenant_manager,
        "get_settings",
        lambda: SimpleNamespace(
            vector_backend="chroma",
            semantic_chunking=False,
            vectordb_chroma_dir=tmp_path,
            vectordb_collection_prefix="rag_docs",
            chunk_size=345,
            chunk_overlap=67,
        ),
    )
    monkeypatch.setattr(tenant_manager, "Chroma", FakeChroma)
    monkeypatch.setattr(tenant_manager._base_manager, "_build_text_splitter", _fake_splitter)

    _, chunks = tenant_manager.build_vector_store(
        docs,
        {},
        embeddings=embeddings,
        tenant_id="acme",
    )

    assert captured["chunk_size"] == 345
    assert captured["chunk_overlap"] == 67
    assert chunks == split_documents


def test_build_retriever_uses_rrf_settings() -> None:
    doc = manager.Document(page_content="test content", metadata={})
    vector_store = MagicMock()

    with patch("config.settings.get_settings") as mock_settings:
        mock_settings.return_value.parent_child = False
        mock_settings.return_value.hybrid_search = True
        mock_settings.return_value.retrieval_top_k = 5
        mock_settings.return_value.rerank_top_k = 3
        mock_settings.return_value.rrf_k = 91
        mock_settings.return_value.rrf_doc_key_chars = 13
        mock_settings.return_value.reranker_model = ""
        mock_settings.return_value.semantic_chunking = False

        retriever = manager.build_retriever(
            docs=[doc],
            embeddings=MagicMock(),
            vector_store=vector_store,
            chunks=[doc],
        )

    assert isinstance(retriever, manager.HybridRetriever)
    assert retriever._rrf_k == 91
    assert retriever._doc_key_chars == 13


def test_run_qa_pipeline_uses_quality_threshold_setting(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeGraph:
        def invoke(self, state):
            return state

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(quality_threshold=73),
    )
    monkeypatch.setattr(agent_graph, "start_trace", lambda trace_id=None, tenant_id="default": trace_id or "trace-1")
    monkeypatch.setattr(agent_graph, "finish_trace", lambda trace_id, final_state: None)

    def _fake_build_support_graph(*, retriever, llm=None, min_quality=80, max_iterations=2):
        _ = retriever, llm, max_iterations
        captured["min_quality"] = min_quality
        return FakeGraph()

    monkeypatch.setattr(agent_graph, "build_support_graph", _fake_build_support_graph)

    agent_graph.run_qa_pipeline(
        question="Как восстановить доступ?",
        retriever=object(),
        llm=MagicMock(),
    )

    assert captured["min_quality"] == 73

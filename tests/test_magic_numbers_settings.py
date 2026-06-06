from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import agent.graph as agent_graph
import vectordb.manager as tenant_manager
from ingestion.pipeline import IngestPipeline
from vectordb import _base_manager as manager


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


def test_chunk_defaults_pinned_to_measured_values(monkeypatch) -> None:
    # 800/200 are corpus-measured (Phase-0 co-occur gate,
    # docs/operations/2026-06-05-chunk-size-phase0-justification.md):
    # 98/100 kw-bundles live inside a single chunk at cap=800 and larger caps
    # buy nothing the production stack hasn't already closed. Changing the
    # defaults invalidates that measurement AND the graph-lane chunk threshold
    # (RAG_GRAPH_MIN_CHUNKS is calibrated as ~chars/800) — re-run the Phase-0
    # gate before bumping these.
    from config.settings import Settings

    for var in ("CHUNK_SIZE", "RAG_CHUNK_SIZE", "CHUNK_OVERLAP", "RAG_CHUNK_OVERLAP"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()

    assert settings.chunk_size == 800
    assert settings.chunk_overlap == 200


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
        mock_settings.return_value.parent_expansion = False
        mock_settings.return_value.parent_expansion_window = 1
        mock_settings.return_value.parent_expansion_max_chars = 2400

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


def test_build_support_graph_uses_fast_llm_for_evaluate_node(monkeypatch) -> None:
    from agent.state import create_initial_state

    class FakeWorkflow:
        def __init__(self, *_args, **_kwargs) -> None:
            self.nodes: dict[str, object] = {}

        def add_node(self, name: str, node) -> None:
            self.nodes[name] = node

        def set_entry_point(self, _name: str) -> None:
            return None

        def add_edge(self, *_args, **_kwargs) -> None:
            return None

        def add_conditional_edges(self, *_args, **_kwargs) -> None:
            return None

        def compile(self):
            return self

    fast_llm = MagicMock()
    fast_llm.invoke.return_value = "82"
    fast_llm.provider_id = "mistral"
    fast_llm.model_name = "ministral-3b-latest"
    strong_llm = MagicMock()
    strong_llm.invoke.return_value = "12"
    strong_llm.provider_id = "gracekelly"
    strong_llm.model_name = "claude-sonnet-4-6"

    monkeypatch.setattr(agent_graph, "StateGraph", FakeWorkflow)
    monkeypatch.setattr(
        agent_graph,
        "build_provider_runtime",
        lambda settings: SimpleNamespace(fast=fast_llm, strong=strong_llm),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(quality_threshold=80),
    )
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *args, **kwargs: None)

    workflow = agent_graph.build_support_graph(retriever=object(), llm=None)
    state = create_initial_state(question="Analyze contract X", trace_id="trace-evaluate")
    state["complexity"] = "complex"
    state["answer"] = "Answer"

    result = workflow.nodes["evaluate"](state)

    assert result["quality_score"] == 82
    fast_llm.invoke.assert_called_once()
    strong_llm.invoke.assert_not_called()


def test_suggest_questions_node_respects_disabled_setting(monkeypatch) -> None:
    llm = MagicMock()

    monkeypatch.setattr(
        agent_graph,
        "get_settings",
        lambda: SimpleNamespace(suggested_questions_enabled=False),
    )

    state = {
        "trace_id": "trace-1",
        "route": "auto",
        "question": "Как оформить возврат?",
        "answer": "Заполните форму возврата.",
        "graded_docs": [],
    }

    result = agent_graph.make_suggest_questions_node(llm)(state)

    assert result["suggested_questions"] == []
    llm.invoke.assert_not_called()


def test_get_or_create_session_uses_self_rag_max_iterations_setting(
    monkeypatch,
    tmp_path,
) -> None:
    import api.app as api_app

    captured: dict[str, object] = {}

    class FakeConversationSession:
        def __init__(self, *, retriever, llm, max_iterations, max_history):
            _ = retriever, llm, max_history
            captured["max_iterations"] = max_iterations

    monkeypatch.setattr(api_app, "_db_retry_after", float("inf"))
    monkeypatch.setattr(api_app, "_session_llm_state", {})
    monkeypatch.setattr(api_app, "_session_last_access", {})
    monkeypatch.setattr(api_app, "_retriever", object())
    monkeypatch.setattr(api_app, "_vector_store", None)
    monkeypatch.setattr(api_app, "_get_retriever", None)
    monkeypatch.setattr(api_app, "_ConversationSession", FakeConversationSession)
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: SimpleNamespace(
            vectordb_chroma_dir=tmp_path / "missing",
            self_rag_max_iterations=0,
        ),
    )

    asyncio.run(api_app._get_or_create_session(None, "default"))

    assert captured["max_iterations"] == 0

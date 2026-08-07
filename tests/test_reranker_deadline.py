"""3.1h — cooperative request deadline at hybrid reranker boundary."""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest

from agent.state import create_initial_state
from utils import request_deadline as rd
from vectordb import _base_manager as manager


@pytest.fixture(autouse=True)
def _clear_deadline() -> None:
    rd.clear_request_deadline()
    yield
    rd.clear_request_deadline()


class _CountingReranker:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls += 1
        # Prefer later docs so order change is observable when called.
        return [float(i) for i in range(len(pairs))]


class _VectorStore:
    def __init__(self, docs: list[manager.Document]) -> None:
        self._docs = docs

    def similarity_search(self, query: str, k: int) -> list[manager.Document]:
        _ = query
        return list(self._docs)[:k]


def _hybrid(
    docs: list[manager.Document],
    reranker: Any,
    *,
    rerank_k: int = 1,
) -> manager.HybridRetriever:
    return manager.HybridRetriever(
        _VectorStore(docs),
        chunks=docs,
        reranker=reranker,
        use_bm25=False,
        rerank_k=rerank_k,
        retrieval_k=20,
    )


def test_rerank_refuses_after_deadline() -> None:
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})
    reranker = _CountingReranker()
    retriever = _hybrid([alpha, beta], reranker, rerank_k=1)

    rd.bind_request_deadline(0.05, source="rerank-test")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        retriever.get_relevant_documents("question")

    assert ei.value.phase == "retriever.rerank"
    assert reranker.calls == 0


def test_rerank_runs_within_deadline() -> None:
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})
    reranker = _CountingReranker()
    retriever = _hybrid([alpha, beta], reranker, rerank_k=1)

    rd.bind_request_deadline(2.0, source="rerank-ok")
    docs = retriever.get_relevant_documents("question")

    assert reranker.calls == 1
    # Higher score on later pair → beta first when rerank_k=1
    assert docs == [beta]


def test_rerank_deadline_not_swallowed_as_top_k_fallback() -> None:
    """Broken-reranker path degrades to top-k; deadline must not use that path."""
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})

    class _DeadlineReranker:
        calls = 0

        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            self.calls += 1
            raise rd.RequestDeadlineExceeded(
                "from predict", phase="retriever.rerank.inner", source="unit"
            )

    reranker = _DeadlineReranker()
    retriever = _hybrid([alpha, beta], reranker, rerank_k=1)

    with pytest.raises(rd.RequestDeadlineExceeded):
        retriever.get_relevant_documents("question")

    assert reranker.calls == 1


def test_vector_fast_path_still_skips_rerank_under_deadline() -> None:
    """get_vector_documents must not hit reranker even when deadline is bound."""
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})
    reranker = _CountingReranker()
    retriever = _hybrid([alpha, beta], reranker, rerank_k=1)

    rd.bind_request_deadline(0.05, source="vector-fast")
    time.sleep(0.08)

    # No raise: vector path does not enter _rerank.
    docs = retriever.get_vector_documents("question")
    assert docs == [alpha]
    assert reranker.calls == 0


def test_retrieve_node_maps_rerank_deadline_to_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deadline during hybrid rerank propagates out of make_retrieve_node."""
    import agent.graph as graph

    alpha = manager.Document(page_content="alpha", metadata={"source": "a.md"})
    beta = manager.Document(page_content="beta", metadata={"source": "b.md"})
    reranker = _CountingReranker()
    hybrid = _hybrid([alpha, beta], reranker, rerank_k=1)

    node = graph.make_retrieve_node(hybrid)
    state = create_initial_state(question="q", trace_id="t-rerank-node")
    state = {**state, "search_query": "q"}

    rd.bind_request_deadline(0.05, source="node-rerank")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        node(state)

    # Either retrieve pre-check or rerank phase — both fail closed; no empty docs.
    assert ei.value.phase in {"retrieve", "retriever.rerank"}
    # If retrieve pre-check wins, reranker never runs; both are valid fail-closed.
    assert reranker.calls == 0


def test_ask_maps_mid_pipeline_rerank_deadline_to_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wall expires after retrieve entry but before rerank → route=timeout."""
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            agentic_mode=False,
            ask_budget_sec=0.0,
            quality_threshold=80,
            online_evaluators_enabled=False,
        ),
        raising=False,
    )

    alpha = manager.Document(page_content="alpha", metadata={})
    beta = manager.Document(page_content="beta", metadata={})
    reranker = _CountingReranker()
    hybrid = _hybrid([alpha, beta], reranker, rerank_k=1)

    def _pipeline(**kwargs: Any) -> dict[str, Any]:
        # Bind already expired is set by ask; burn nothing — simulate late rerank
        # by invoking hybrid under the same ContextVar after a short sleep that
        # exceeds the wall. Retrieve node check at t=0 would pass if we sleep
        # inside after retrieve-level check; call hybrid directly past wall.
        time.sleep(0.12)
        docs = kwargs["retriever"].get_relevant_documents(str(kwargs.get("question") or "q"))
        return {
            "answer": "should-not",
            "route": "auto",
            "quality_score": 90,
            "context_docs": docs,
        }

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=hybrid, llm=None)
    result = session.ask("q", deadline_sec=0.08)

    assert result["route"] == "timeout"
    assert result.get("error") is True
    assert reranker.calls == 0

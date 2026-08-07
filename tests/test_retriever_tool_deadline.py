"""3.1g — cooperative request deadline at retriever / tool boundaries."""
from __future__ import annotations

import importlib
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from agent.state import create_initial_state
from utils import request_deadline as rd

agent_graph = importlib.import_module("agent.graph")
agent_tools = importlib.import_module("agent.tools")


@pytest.fixture(autouse=True)
def _clear_deadline() -> None:
    rd.clear_request_deadline()
    yield
    rd.clear_request_deadline()


class _CountingRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def get_relevant_documents(self, query: str) -> list[Any]:
        self.calls += 1
        return [
            SimpleNamespace(
                page_content=f"doc for {query}",
                metadata={"source": "kb.md", "doc_id": "1"},
            )
        ]


def test_retrieve_node_refuses_after_deadline() -> None:
    retriever = _CountingRetriever()
    node = agent_graph.make_retrieve_node(retriever)
    state = create_initial_state(question="гарантия?", trace_id="t-retrieve-deadline")

    rd.bind_request_deadline(0.05, source="retrieve-test")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        node(state)

    assert ei.value.phase == "retrieve"
    assert retriever.calls == 0


def test_retrieve_node_runs_within_deadline() -> None:
    retriever = _CountingRetriever()
    node = agent_graph.make_retrieve_node(retriever)
    state = create_initial_state(question="гарантия?", trace_id="t-retrieve-ok")
    state = {**state, "search_query": "гарантия?"}

    rd.bind_request_deadline(2.0, source="retrieve-ok")
    out = node(state)

    assert retriever.calls == 1
    assert out.get("error") is not True
    assert out.get("context_docs")


def test_retrieve_node_does_not_swallow_deadline_as_empty_docs() -> None:
    """Inner retriever errors become empty docs; deadline must not."""
    retriever = Mock()
    retriever.get_relevant_documents.side_effect = rd.RequestDeadlineExceeded(
        "mid", phase="retrieve.inner", source="unit"
    )
    node = agent_graph.make_retrieve_node(retriever)
    state = create_initial_state(question="q", trace_id="t-no-swallow")
    state = {**state, "search_query": "q"}

    # No outer deadline; raise comes from retriever itself.
    with pytest.raises(rd.RequestDeadlineExceeded):
        node(state)

    # Must not convert to silent empty success.
    # (If swallowed, node would return context_docs=[].)


def test_search_kb_refuses_after_deadline() -> None:
    retriever = _CountingRetriever()
    rd.bind_request_deadline(0.05, source="tool-search")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        agent_tools.search_kb("возврат", "acme", retriever=retriever)

    assert "search_kb" in ei.value.phase or ei.value.phase.startswith("tool.")
    assert retriever.calls == 0


def test_search_kb_runs_within_deadline() -> None:
    retriever = _CountingRetriever()
    rd.bind_request_deadline(2.0, source="tool-search-ok")
    result = agent_tools.search_kb("возврат", "acme", retriever=retriever)
    assert retriever.calls == 1
    assert "doc for" in result


def test_create_ticket_refuses_after_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _boom(*_a: Any, **_k: Any) -> str:
        calls.append("persist")
        return "should-not"

    monkeypatch.setattr(agent_tools, "_persist_ticket", _boom)

    rd.bind_request_deadline(0.05, source="tool-ticket")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        agent_tools.create_ticket(
            summary="оплата",
            priority="high",
            tenant_id="acme",
            user_id="u1",
            session_id="s1",
        )

    assert "create_ticket" in ei.value.phase or ei.value.phase.startswith("tool.")
    assert calls == []


def test_check_order_status_refuses_after_deadline() -> None:
    rd.bind_request_deadline(0.05, source="tool-order")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded):
        agent_tools.check_order_status("42", "acme")


def test_ask_maps_retrieve_deadline_to_timeout_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired wall before retrieve → route=timeout, not silent empty auto."""
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

    retriever = _CountingRetriever()

    def _pipeline(**kwargs: Any) -> dict[str, Any]:
        # Simulate graph retrieve boundary under the same ContextVar.
        node = agent_graph.make_retrieve_node(kwargs["retriever"])
        state = create_initial_state(
            question=str(kwargs.get("question") or "q"),
            trace_id="t-ask-retrieve",
            tenant_id=str(kwargs.get("tenant_id") or "default"),
        )
        state = {**state, "search_query": state["question"]}
        # Burn wall, then retrieve refuses.
        time.sleep(0.12)
        return node(state)

    monkeypatch.setattr(agent_graph, "run_qa_pipeline", _pipeline, raising=False)
    session = agent_graph.ConversationSession(retriever=retriever, llm=None)
    result = session.ask("q", deadline_sec=0.08)

    assert result["route"] == "timeout"
    assert result.get("error") is True
    assert retriever.calls == 0


def test_ask_maps_create_ticket_deadline_to_timeout_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persist_calls: list[str] = []

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            agentic_mode=True,
            ask_budget_sec=0.0,
            quality_threshold=80,
            online_evaluators_enabled=False,
        ),
        raising=False,
    )
    monkeypatch.setattr(agent_graph, "build_provider_runtime", None)

    async def _persist(*_a: Any, **_k: Any) -> str:
        persist_calls.append("yes")
        return "T-1"

    monkeypatch.setattr(agent_tools, "_persist_ticket", _persist)

    session = agent_graph.ConversationSession(retriever=object(), llm=None)
    # Seed pending outside turn (direct field); _set_pending_action needs active turn.
    session._pending_action = {
        "summary": "проблема оплаты",
        "priority": "medium",
        "action_summary": "создать тикет по запросу: проблема оплаты",
    }

    rd.bind_request_deadline(0.05, source="ask-ticket")
    time.sleep(0.08)

    result = session.ask(
        "Подтверждаю",
        tenant_id="acme",
        user_id="u1",
        session_id="s1",
        confirm=True,
        deadline_sec=0.01,
    )

    assert result["route"] == "timeout"
    assert result.get("error") is True
    assert persist_calls == []

"""Plan §4.8: true provider token streaming through graph generate (parity SSE).

Tokens must originate from the generate-node LLM stream (token_source=
provider_generate), not post-hoc UX chunks of a finished answer
(graph_answer_chunks). Single generation only; no second stream LLM path.
"""

from __future__ import annotations

import importlib
import json
from typing import Any, TypedDict

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, StateGraph

from agent.graph_stream import stream_graph_node_events

api_app = importlib.import_module("api.app")


def _parse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for chunk in payload.split("\n\n"):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


class _S(TypedDict):
    answer: str


def test_stream_graph_node_events_relays_custom_provider_tokens() -> None:
    """LangGraph custom stream mode must surface generate tokens live."""
    from langgraph.config import get_stream_writer

    def generate(state: _S) -> dict[str, Any]:
        writer = get_stream_writer()
        writer(
            {
                "type": "token",
                "token": "Hel",
                "token_source": "provider_generate",
                "source": "graph",
            }
        )
        writer(
            {
                "type": "token",
                "token": "lo",
                "token_source": "provider_generate",
                "source": "graph",
            }
        )
        return {"answer": "Hello"}

    g = StateGraph(_S)
    g.add_node("generate", generate)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    compiled = g.compile()

    events = list(stream_graph_node_events(compiled, {"answer": ""}))
    token_events = [e for e in events if e.get("type") == "token"]
    assert [e["token"] for e in token_events] == ["Hel", "lo"]
    assert all(e.get("token_source") == "provider_generate" for e in token_events)
    assert all(e.get("source") == "graph" for e in token_events)
    result = next(e for e in events if e.get("type") == "pipeline_result")
    assert result["state"]["answer"] == "Hello"


def test_generate_node_streams_provider_tokens_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """make_generate_node must stream via generate_stream under token-stream flag."""
    from langgraph.graph import END, StateGraph

    import agent.doc_grade as doc_grade
    from agent.graph import make_generate_node
    from agent.graph_stream import provider_token_stream_enabled

    class _StreamLLM:
        def invoke(self, prompt: str, **kwargs: Any) -> str:
            raise AssertionError("invoke must not run when generate_stream works")

        async def generate_stream(self, messages, **kwargs):  # noqa: ANN001
            _ = messages, kwargs
            for part in ("Prov", "ider", "!"):
                yield part

    # resolve lives in agent.doc_grade — imported inside generate node
    monkeypatch.setattr(doc_grade, "resolve_generation_context_docs", lambda state: [])

    llm = _StreamLLM()
    node_fn = make_generate_node(llm, llm)

    class _GS(TypedDict, total=False):
        question: str
        answer: str
        complexity: str
        chat_history: list
        error: bool
        trace_id: str
        tenant_id: str
        citations: list
        claims: list
        fact_verification_skipped: bool
        factuality_score: float
        grounding_status: str
        tool_calls: list

    def wrapped(state: _GS) -> dict[str, Any]:
        return node_fn(state)  # type: ignore[arg-type]

    g = StateGraph(dict)
    g.add_node("generate", wrapped)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    compiled = g.compile()

    token = provider_token_stream_enabled.set(True)
    try:
        events = list(
            stream_graph_node_events(
                compiled,
                {
                    "question": "q?",
                    "answer": "",
                    "complexity": "simple",
                    "chat_history": [],
                    "error": False,
                    "trace_id": "t-stream-1",
                    "tenant_id": "default",
                    "tool_calls": [],
                },
            )
        )
    finally:
        provider_token_stream_enabled.reset(token)

    tokens = [e["token"] for e in events if e.get("type") == "token"]
    assert tokens == ["Prov", "ider", "!"]
    assert all(
        e.get("token_source") == "provider_generate"
        for e in events
        if e.get("type") == "token"
    )
    result = next(e for e in events if e.get("type") == "pipeline_result")
    assert result["state"]["answer"] == "Provider!"


def test_sse_parity_uses_provider_generate_token_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parity SSE must relay live provider tokens and not re-chunk the answer."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = object()
            self._llm = None
            self._history: list[dict] = []

        def iter_ask_events(self, question, **kwargs):  # noqa: ANN003
            _ = question, kwargs
            yield {
                "type": "status",
                "node": "retrieve",
                "source": "graph",
                "phase": "end",
            }
            yield {
                "type": "token",
                "token": "Live",
                "token_source": "provider_generate",
                "source": "graph",
            }
            yield {
                "type": "token",
                "token": "Tok",
                "token_source": "provider_generate",
                "source": "graph",
            }
            yield {
                "type": "status",
                "node": "generate",
                "source": "graph",
                "phase": "end",
            }
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "LiveTok"})
            yield {
                "type": "pipeline_result",
                "state": {
                    "answer": "LiveTok",
                    "quality_score": 88,
                    "quality_source": "llm",
                    "route": "auto",
                    "trace_id": "trace-provider-tok",
                    "citations": [],
                    "suggested_questions": [],
                },
                "source": "graph",
                "nodes": ["retrieve", "generate"],
            }

        def ask(self, question, **kwargs):  # noqa: ANN003
            raise AssertionError("ask() must not run when iter_ask_events exists")

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-ptok", _Session())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    api_app.get_settings().streaming_rag_parity = True

    response = client.post(
        "/api/ask/stream",
        json={"question": "provider-tokens"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    events = _parse_events(response.text)

    token_events = [e for e in events if e.get("type") == "token"]
    assert [e["token"] for e in token_events] == ["Live", "Tok"]
    assert all(e.get("token_source") == "provider_generate" for e in token_events)

    starts = [e for e in events if e.get("type") == "token_start"]
    assert starts
    assert starts[0].get("token_source") == "provider_generate"

    # Must not re-emit the finished answer as graph_answer_chunks.
    assert not any(
        e.get("token_source") == "graph_answer_chunks"
        for e in events
        if e.get("type") in {"token", "token_start"}
    )

    final = next(e for e in events if e.get("type") == "result")
    assert final["answer"] == "LiveTok"
    assert final.get("generation_source") == "graph_only"
    assert final.get("token_source") == "provider_generate"


def test_sse_parity_fallback_chunks_when_no_provider_tokens(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without provider tokens, keep §4.7 UX chunk fallback."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = object()
            self._llm = None
            self._history: list[dict] = []

        def iter_ask_events(self, question, **kwargs):  # noqa: ANN003
            _ = kwargs
            yield {
                "type": "status",
                "node": "generate",
                "source": "graph",
                "phase": "end",
            }
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "fallback-answer"})
            yield {
                "type": "pipeline_result",
                "state": {
                    "answer": "fallback-answer",
                    "quality_score": 70,
                    "quality_source": "llm",
                    "route": "auto",
                    "trace_id": "trace-fallback",
                    "citations": [],
                    "suggested_questions": [],
                },
                "source": "graph",
                "nodes": ["generate"],
            }

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-fb", _Session())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    api_app.get_settings().streaming_rag_parity = True

    response = client.post(
        "/api/ask/stream",
        json={"question": "no-provider-tokens"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    events = _parse_events(response.text)
    token_events = [e for e in events if e.get("type") == "token"]
    assert token_events
    assert all(e.get("token_source") == "graph_answer_chunks" for e in token_events)
    final = next(e for e in events if e.get("type") == "result")
    assert final.get("token_source") == "graph_answer_chunks"

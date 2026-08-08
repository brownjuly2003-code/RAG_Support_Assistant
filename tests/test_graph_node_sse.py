"""Plan §4.7: real LangGraph node status events on streaming parity path."""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from typing import TypedDict

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, StateGraph

from agent.graph_stream import stream_graph_node_events

api_app = importlib.import_module("api.app")


class _S(TypedDict):
    x: int
    answer: str


def _parse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for chunk in payload.split("\n\n"):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def test_stream_graph_node_events_emits_real_nodes() -> None:
    g = StateGraph(_S)

    def n1(state: _S) -> dict:
        return {"x": state["x"] + 1, "answer": ""}

    def n2(state: _S) -> dict:
        return {"x": state["x"] + 1, "answer": "done"}

    g.add_node("classify_complexity", n1)
    g.add_node("generate", n2)
    g.set_entry_point("classify_complexity")
    g.add_edge("classify_complexity", "generate")
    g.add_edge("generate", END)
    compiled = g.compile()

    events = list(stream_graph_node_events(compiled, {"x": 0, "answer": ""}))
    statuses = [e for e in events if e.get("type") == "status"]
    results = [e for e in events if e.get("type") == "pipeline_result"]
    assert [s["node"] for s in statuses] == ["classify_complexity", "generate"]
    assert all(s.get("source") == "graph" for s in statuses)
    assert len(results) == 1
    assert results[0]["state"]["answer"] == "done"
    assert results[0]["state"]["x"] == 2


def test_stream_graph_node_events_fallback_invoke() -> None:
    class _Fake:
        def invoke(self, state):
            return {**state, "answer": "invoked"}

    events = list(stream_graph_node_events(_Fake(), {"answer": ""}))
    assert events[0]["type"] == "status"
    assert events[-1]["type"] == "pipeline_result"
    assert events[-1]["state"]["answer"] == "invoked"


def test_sse_parity_emits_graph_node_status_events(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When session.iter_ask_events exists, SSE carries real node status events."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = object()
            self._llm = None
            self._history: list[dict] = []

        def iter_ask_events(self, question, **kwargs):  # noqa: ANN003
            _ = question, kwargs
            yield {
                "type": "status",
                "node": "classify_complexity",
                "source": "graph",
                "phase": "end",
            }
            yield {
                "type": "status",
                "node": "generate",
                "source": "graph",
                "phase": "end",
            }
            yield {
                "type": "status",
                "node": "evaluate",
                "source": "graph",
                "phase": "end",
            }
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "graph-terminal"})
            yield {
                "type": "pipeline_result",
                "state": {
                    "answer": "graph-terminal",
                    "quality_score": 91,
                    "quality_source": "llm",
                    "route": "auto",
                    "trace_id": "trace-nodes-1",
                    "citations": [],
                    "suggested_questions": [],
                },
                "source": "graph",
                "nodes": ["classify_complexity", "generate", "evaluate"],
            }

        def ask(self, question, **kwargs):  # noqa: ANN003
            raise AssertionError("ask() must not run when iter_ask_events exists")

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-nodes", _Session())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    api_app.get_settings().streaming_rag_parity = True

    response = client.post(
        "/api/ask/stream",
        json={"question": "node-events"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    events = _parse_events(response.text)
    status_nodes = [
        e.get("node")
        for e in events
        if e.get("type") == "status" and e.get("source") == "graph"
    ]
    assert "classify_complexity" in status_nodes
    assert "generate" in status_nodes
    assert "evaluate" in status_nodes
    # Initial processing status may still appear first without source=graph.
    final = next(e for e in events if e.get("type") == "result")
    assert final["answer"] == "graph-terminal"
    assert final.get("answer_source") == "graph"
    assert final.get("generation_source") == "graph_only"
    assert final.get("events_source") == "graph"
    assert "classify_complexity" in final.get("graph_nodes", [])
    token_events = [e for e in events if e.get("type") == "token"]
    assert token_events
    assert all(e.get("token_source") == "graph_answer_chunks" for e in token_events)


def test_sse_parity_without_iter_ask_events_still_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test doubles with only ask() keep §4.2 contract."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = object()
            self._llm = SimpleNamespace(supports_streaming=True)
            self._history: list[dict] = []

        def ask(self, question, **kwargs):  # noqa: ANN003
            _ = kwargs
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "ask-only"})
            return {
                "answer": "ask-only",
                "quality_score": 80,
                "route": "auto",
                "trace_id": "trace-ask-only",
                "citations": [],
                "suggested_questions": [],
            }

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-ask", _Session())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    api_app.get_settings().streaming_rag_parity = True

    response = client.post(
        "/api/ask/stream",
        json={"question": "ask-only"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    events = _parse_events(response.text)
    final = next(e for e in events if e.get("type") == "result")
    assert final["answer"] == "ask-only"
    assert final.get("events_source") == "ask"

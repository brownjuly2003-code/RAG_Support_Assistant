"""H1: parity между /api/ask/stream и full Self-RAG graph.

После Codex P1 streaming endpoint обходил graph (route/quality/citations/trace
basers на эвристике len(answer)>20 + sources). Сейчас он параллельно запускает
session.ask() через executor и при формировании финального SSE event
переписывает route/quality/citations/trace_id/suggested_questions из
graph результата.
"""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def _parse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for chunk in payload.split("\n\n"):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def _retriever_with_doc(doc_content: str = "Стрим парити содержит факты."):
    class _Retriever:
        def get_relevant_documents(self, question: str):
            _ = question
            return [
                SimpleNamespace(
                    page_content=doc_content,
                    metadata={"source": "policy.md", "doc_id": "p1", "title": "Policy"},
                )
            ]

    return _Retriever()


class _StreamingLLM:
    supports_streaming = True

    def __init__(self, tokens=("Стрим", " ответ")) -> None:
        self.tokens = tokens

    async def generate_stream(self, messages, **kwargs):
        _ = messages, kwargs
        for tok in self.tokens:
            yield tok


def _install_session(monkeypatch: pytest.MonkeyPatch, session) -> None:
    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "session-stream", session)

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)


def _enable_parity() -> None:
    api_app.get_settings().streaming_rag_parity = True


def test_stream_final_event_uses_graph_quality_and_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Graph quality/route override the streaming heuristic."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = _retriever_with_doc()
            self._llm = _StreamingLLM()
            self.history: list[dict] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            _ = question, trace_id, tenant_id
            return {
                "answer": "ground truth answer",
                "quality_score": 35,
                "route": "human",
                "graded_docs": [],
                "citations": [],
                "trace_id": "trace-from-graph-1",
                "suggested_questions": ["graph-suggested-q?"],
            }

    _install_session(monkeypatch, _Session())
    _enable_parity()

    response = client.post(
        "/api/ask/stream",
        json={"question": "test"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    events = _parse_events(response.text)
    final = next(event for event in events if event.get("type") == "result")

    assert final["quality_score"] == 35, "graph quality_score must override heuristic"
    assert final["route"] == "human", "graph route must override heuristic"
    assert final["trace_id"] == "trace-from-graph-1"
    assert final["suggested_questions"] == ["graph-suggested-q?"]
    assert final["answer"] == "Стрим ответ", "answer remains streamed text for UX"


def test_stream_uses_graph_citations_when_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Когда graph отдал citations — итоговый event использует их, не stream-вариант."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = _retriever_with_doc()
            self._llm = _StreamingLLM()
            self.history: list[dict] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            _ = question, trace_id, tenant_id
            return {
                "answer": "graph answer",
                "quality_score": 90,
                "route": "auto",
                "citations": [
                    {
                        "index": 1,
                        "doc_id": "graph-doc-1",
                        "title": "Graph Title",
                        "excerpt": "Graph excerpt fragment",
                    }
                ],
                "trace_id": "trace-graph-cite",
                "suggested_questions": [],
            }

    _install_session(monkeypatch, _Session())
    _enable_parity()

    response = client.post(
        "/api/ask/stream",
        json={"question": "test"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    events = _parse_events(response.text)
    final = next(event for event in events if event.get("type") == "result")

    assert final["citations"], "citations must be populated"
    assert final["citations"][0]["doc_id"] == "graph-doc-1"
    assert final["citations"][0]["title"] == "Graph Title"
    assert final["trace_id"] == "trace-graph-cite"


def test_stream_falls_back_when_graph_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STREAMING_RAG_PARITY=false возвращает прежнее эвристическое поведение."""

    # conftest заменяет api_app.get_settings на лямбду, возвращающую
    # SimpleNamespace из settings_factory. Дописываем атрибут напрямую.
    api_app.get_settings().streaming_rag_parity = False

    ask_called = {"value": False}

    class _Session:
        def __init__(self) -> None:
            self._retriever = _retriever_with_doc()
            self._llm = _StreamingLLM(tokens=("длинный ", "ответ ", "со многими ", "токенами"))
            self.history: list[dict] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            ask_called["value"] = True
            return {
                "answer": "graph answer",
                "quality_score": 99,
                "route": "auto",
                "trace_id": "trace-disabled",
            }

    _install_session(monkeypatch, _Session())

    response = client.post(
        "/api/ask/stream",
        json={"question": "test"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    events = _parse_events(response.text)
    final = next(event for event in events if event.get("type") == "result")

    assert ask_called["value"] is False, "ask() must NOT run when parity disabled"
    assert final["trace_id"] == "", "trace_id stays empty without graph parity"
    assert final["quality_score"] == 70, "stream heuristic computes quality from len+sources"


def test_stream_does_not_double_append_history_when_graph_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CX P2: session.ask appends to _history; streaming code must not re-append."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = _retriever_with_doc()
            self._llm = _StreamingLLM()
            self._history: list[dict] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            # mimic ConversationSession._append_history
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "ground truth"})
            return {
                "answer": "ground truth",
                "quality_score": 90,
                "route": "auto",
                "trace_id": "trace-dedup",
            }

    sess = _Session()
    _install_session(monkeypatch, sess)
    _enable_parity()

    response = client.post(
        "/api/ask/stream",
        json={"question": "Q1"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    # Exactly one user/assistant pair from session.ask, no double-append from
    # the streaming branch.
    assert len(sess._history) == 2
    assert sess._history[0]["role"] == "user"
    assert sess._history[0]["content"] == "Q1"
    assert sess._history[1]["role"] == "assistant"


def test_stream_survives_when_graph_raises(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Если parity graph упал — стрим всё равно отдаёт final event с heuristic."""

    class _Session:
        def __init__(self) -> None:
            self._retriever = _retriever_with_doc()
            self._llm = _StreamingLLM(tokens=("длинный ", "ответ ", "ещё токены"))
            self.history: list[dict] = []

        def ask(self, question, trace_id=None, tenant_id="default"):
            raise RuntimeError("simulated graph failure")

    _install_session(monkeypatch, _Session())
    _enable_parity()

    response = client.post(
        "/api/ask/stream",
        json={"question": "test"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    events = _parse_events(response.text)
    final = next(event for event in events if event.get("type") == "result")

    # graph failed → trace_id stays empty, but stream completes successfully
    assert final["answer"] == "длинный ответ ещё токены"
    assert final["trace_id"] == ""
    assert final["quality_score"] in (40, 70)

"""3.1f — streaming path capacity-hold + deadline/budget bind."""
from __future__ import annotations

import importlib
import json
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")

CLIENT_SETTINGS_OVERRIDES = {
    "streaming_enabled": True,
    "streaming_rag_parity": True,
    "request_timeout_sec": 0.25,
    "pipeline_acquire_timeout_sec": 0.15,
    "max_concurrent_pipelines": 1,
    "request_executor_max_workers": 1,
}


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for chunk in payload.split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        try:
            events.append(json.loads(chunk[6:]))
        except json.JSONDecodeError:
            continue
    return events


def test_stream_parity_timeout_holds_capacity_until_orphan_done(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
) -> None:
    """Parity orphan must keep the pipeline slot busy for a concurrent ask."""
    from utils import request_executor as re

    re.reset_request_executor_for_tests()
    api_app._pipeline_semaphore = None

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            streaming_enabled=True,
            streaming_rag_parity=True,
            request_timeout_sec=0.2,
            pipeline_acquire_timeout_sec=0.1,
            max_concurrent_pipelines=1,
            request_executor_max_workers=1,
            llm_max_calls_per_request=0,
            llm_max_input_tokens_per_request=0,
            llm_max_output_tokens_per_request=0,
            llm_max_total_tokens_per_request=0,
            ask_budget_sec=0.0,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0

    release_orphan = threading.Event()
    ask_started = threading.Event()
    ask_kwargs_seen: dict[str, Any] = {}

    class _FakeRetriever:
        def get_relevant_documents(self, question: str):
            _ = question
            return [
                SimpleNamespace(
                    page_content="doc",
                    metadata={"source": "d.md", "doc_id": "1", "title": "d"},
                )
            ]

    class _StreamingLLM:
        supports_streaming = True

        async def generate_stream(self, messages, **kwargs):  # noqa: ANN001
            _ = messages, kwargs
            yield "hi "

        def invoke(self, prompt: str, **kwargs: Any) -> str:
            _ = prompt, kwargs
            return "unused"

    class _FakeSession:
        def __init__(self) -> None:
            self._retriever = _FakeRetriever()
            self._llm = _StreamingLLM()
            self._history: list[dict[str, str]] = []
            self._max_history = 10

        def ask(self, question: str, **kwargs: Any) -> dict:
            ask_kwargs_seen.update(kwargs)
            ask_started.set()
            # Block longer than parity timeout so outer path orphans us.
            release_orphan.wait(timeout=3)
            return {
                "answer": "parity-late",
                "quality_score": 70,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "t-parity",
            }

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "sid-stream", _FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    # Stream returns once tokens + result path finish (parity may still run).
    stream_resp = client.post(
        "/api/ask/stream",
        json={"question": "q-stream"},
        headers={"Accept": "text/event-stream"},
    )
    assert stream_resp.status_code == 200
    assert ask_started.wait(timeout=2)

    # While orphan holds capacity, sync ask must be rejected busy.
    second = client.post("/api/ask", json={"question": "now"})
    assert second.status_code == 503

    release_orphan.set()
    # After orphan finishes, capacity frees.
    deadline = time.monotonic() + 4.0
    recovered = None
    while time.monotonic() < deadline:
        monkeypatch.setattr(
            api_app,
            "get_settings",
            lambda: settings_factory(
                streaming_enabled=True,
                streaming_rag_parity=False,
                request_timeout_sec=5.0,
                pipeline_acquire_timeout_sec=0.5,
                max_concurrent_pipelines=1,
                request_executor_max_workers=1,
                llm_max_calls_per_request=0,
                llm_max_input_tokens_per_request=0,
                llm_max_output_tokens_per_request=0,
                llm_max_total_tokens_per_request=0,
                ask_budget_sec=0.0,
            ),
        )

        class _FastSession:
            def ask(self, question: str, **kwargs: Any) -> dict:
                _ = question, kwargs
                return {
                    "answer": "ok",
                    "quality_score": 80,
                    "route": "auto",
                    "graded_docs": [],
                    "trace_id": "t-ok",
                }

        async def _fast_session(session_id, tenant_id="default"):
            return (session_id or "sid2", _FastSession())

        monkeypatch.setattr(api_app, "_get_or_create_session", _fast_session)
        recovered = client.post("/api/ask", json={"question": "after"})
        if recovered.status_code == 200:
            break
        time.sleep(0.05)
    else:
        pytest.fail("pipeline capacity never recovered after stream orphan finished")

    # Parity ask received cooperative deadline_sec.
    assert "deadline_sec" in ask_kwargs_seen


def test_stream_binds_budget_for_generate_stream(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
) -> None:
    """Stream path must install request budget so generate_stream charges it."""
    from llm import request_budget as rb

    rb.clear_llm_request_budget()
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            streaming_enabled=True,
            streaming_rag_parity=False,
            request_timeout_sec=30.0,
            max_concurrent_pipelines=2,
            llm_max_calls_per_request=5,
            llm_max_input_tokens_per_request=10000,
            llm_max_output_tokens_per_request=10000,
            llm_max_total_tokens_per_request=20000,
            ask_budget_sec=0.0,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0
    charged: list[int] = []

    class _FakeRetriever:
        def get_relevant_documents(self, question: str):
            return [
                SimpleNamespace(
                    page_content="x",
                    metadata={"source": "s", "doc_id": "1", "title": "t"},
                )
            ]

    class _StreamingLLM:
        supports_streaming = True

        async def generate_stream(self, messages, **kwargs):  # noqa: ANN001
            # After ProviderBackedLLM path charges; bare fakes may not.
            # Observe budget was bound when stream started.
            budget = rb.get_llm_request_budget()
            charged.append(1 if budget is not None else 0)
            yield "ok"

    class _FakeSession:
        def __init__(self) -> None:
            self._retriever = _FakeRetriever()
            self._llm = _StreamingLLM()
            self._history: list = []
            self.history: list = []

    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return (session_id or "s", _FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    response = client.post(
        "/api/ask/stream",
        json={"question": "budget-bind"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert charged == [1], "stream generate_stream must run with bound LLM budget"

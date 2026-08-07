"""3.1b — cooperative request deadline at provider boundary."""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest

from llm.providers.base import LLMResponse, ProviderBackedLLM, ProviderUnavailable
from utils import request_deadline as rd


@pytest.fixture(autouse=True)
def _clear_deadline() -> None:
    rd.clear_request_deadline()
    yield
    rd.clear_request_deadline()


class _CountingProvider:
    provider_id = "fake"
    model_name = "fake-model"

    def __init__(self, *, sleep_sec: float = 0.0, text: str = "ok") -> None:
        self.sleep_sec = sleep_sec
        self.text = text
        self.calls = 0

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls += 1
        if self.sleep_sec:
            time.sleep(self.sleep_sec)
        return LLMResponse(text=self.text, provider=self.provider_id, model=self.model_name)

    def generate_with_tools(self, messages, tools, **kwargs):  # noqa: ANN001
        return self.generate(messages, tools=tools, **kwargs)

    def generate_with_schema(self, messages, schema, **kwargs):  # noqa: ANN001
        return self.generate(messages, **kwargs)


def test_tighter_timeout_sec_picks_minimum_positive() -> None:
    assert rd.tighter_timeout_sec(0, None, -1) == 0.0
    assert rd.tighter_timeout_sec(30, 5, 0) == 5.0
    assert rd.tighter_timeout_sec(None, 12.5) == 12.5


def test_bind_and_check_deadline_expires() -> None:
    d = rd.bind_request_deadline(0.05, source="unit")
    assert d is not None
    assert d.remaining_sec() > 0
    time.sleep(0.08)
    with pytest.raises(rd.RequestDeadlineExceeded) as ei:
        rd.check_request_deadline("unit.phase")
    assert ei.value.phase == "unit.phase"
    assert ei.value.source == "unit"


def test_check_noop_without_deadline() -> None:
    rd.clear_request_deadline()
    rd.check_request_deadline("noop")  # does not raise


def test_provider_backed_llm_refuses_call_after_deadline() -> None:
    primary = _CountingProvider(text="primary")
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    rd.bind_request_deadline(0.05, source="provider-test")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded):
        llm.generate([{"role": "user", "content": "hi"}])

    assert primary.calls == 0


def test_provider_backed_llm_does_not_failover_after_deadline() -> None:
    """Deadline fail-closed: never start fallback provider work."""
    fallback = _CountingProvider(text="fallback")

    # Primary would raise unavailable if called; deadline should win first.
    class _Down(_CountingProvider):
        def generate(self, messages, tools=None, **kwargs):  # noqa: ANN001
            self.calls += 1
            raise ProviderUnavailable("down", provider_id="fake", reason="down")

    down = _Down()
    llm = ProviderBackedLLM(
        provider=down,  # type: ignore[arg-type]
        fallback_provider=fallback,  # type: ignore[arg-type]
    )
    rd.bind_request_deadline(0.05, source="failover-test")
    time.sleep(0.08)

    with pytest.raises(rd.RequestDeadlineExceeded):
        llm.generate([{"role": "user", "content": "hi"}])

    assert down.calls == 0
    assert fallback.calls == 0


def test_provider_allows_call_within_deadline() -> None:
    primary = _CountingProvider(text="within")
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    rd.bind_request_deadline(2.0, source="ok")
    response = llm.generate([{"role": "user", "content": "hi"}])
    assert response.text == "within"
    assert primary.calls == 1


def test_ask_cooperative_deadline_returns_timeout_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After wall elapses, a late provider invoke becomes route=timeout."""
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

    primary = _CountingProvider(sleep_sec=0.0, text="ok")
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    call_count = {"n": 0}

    def _pipeline(**kwargs):  # noqa: ANN003
        call_count["n"] += 1
        active = kwargs.get("llm") or llm
        # First provider call OK, then burn the wall, then refuse second call.
        _ = active.invoke("step-1")
        time.sleep(0.12)
        _ = active.invoke("step-2")
        return {"answer": "should-not", "route": "auto", "quality_score": 90}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=llm)
    result = session.ask("q", deadline_sec=0.08)

    assert result["route"] == "timeout"
    assert result["error"] is True
    assert call_count["n"] == 1
    # Second provider call must not start after deadline.
    assert primary.calls == 1


def test_ask_deadline_sec_kwarg_accepted_by_http_style_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        graph,
        "run_qa_pipeline",
        lambda **kwargs: {"answer": "ok", "route": "auto", "quality_score": 80},
        raising=False,
    )
    session = graph.ConversationSession(retriever=object(), llm=None)
    result = session.ask("q", deadline_sec=30.0)
    assert result["answer"] == "ok"

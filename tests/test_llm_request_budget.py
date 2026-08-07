"""3.1e — per-request LLM call/token budget (never route=auto on exhaust)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from llm import request_budget as rb
from llm.providers.base import LLMResponse, ProviderBackedLLM


@pytest.fixture(autouse=True)
def _clear_budget() -> None:
    rb.clear_llm_request_budget()
    yield
    rb.clear_llm_request_budget()


class _CountingProvider:
    provider_id = "fake"
    model_name = "fake-model"

    def __init__(self, *, in_tok: int = 10, out_tok: int = 5) -> None:
        self.calls = 0
        self.in_tok = in_tok
        self.out_tok = out_tok

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=f"ok-{self.calls}",
            provider=self.provider_id,
            model=self.model_name,
            input_tokens=self.in_tok,
            output_tokens=self.out_tok,
        )


def test_bind_all_zero_disables_budget() -> None:
    assert rb.bind_llm_request_budget() is None
    assert rb.get_llm_request_budget() is None
    rb.check_llm_request_budget()  # no-op


def test_max_calls_blocks_second_generate() -> None:
    primary = _CountingProvider()
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    rb.bind_llm_request_budget(max_calls=1, source="unit")

    assert llm.invoke("first") == "ok-1"
    with pytest.raises(rb.LLMBudgetExceeded) as ei:
        llm.invoke("second")
    assert ei.value.reason == "max_calls"
    assert primary.calls == 1


def test_max_input_tokens_blocks_before_call() -> None:
    primary = _CountingProvider(in_tok=100, out_tok=1)
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    rb.bind_llm_request_budget(max_input_tokens=50, source="unit")

    # First call charges 100 input → already over; second must refuse.
    llm.invoke("first")
    with pytest.raises(rb.LLMBudgetExceeded) as ei:
        llm.invoke("second")
    assert ei.value.reason in {"max_input_tokens", "max_total_tokens"}
    assert primary.calls == 1


def test_budget_exceeded_does_not_failover() -> None:
    primary = _CountingProvider()
    fallback = _CountingProvider()
    llm = ProviderBackedLLM(
        provider=primary,  # type: ignore[arg-type]
        fallback_provider=fallback,  # type: ignore[arg-type]
    )
    rb.bind_llm_request_budget(max_calls=1, source="unit")
    llm.invoke("one")
    with pytest.raises(rb.LLMBudgetExceeded):
        llm.invoke("two")
    assert fallback.calls == 0


def test_ask_maps_budget_exceeded_to_human_not_auto(
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
            llm_max_calls_per_request=1,
            llm_max_input_tokens_per_request=0,
            llm_max_output_tokens_per_request=0,
            llm_max_total_tokens_per_request=0,
        ),
        raising=False,
    )

    primary = _CountingProvider()
    llm = ProviderBackedLLM(provider=primary)  # type: ignore[arg-type]
    n = {"i": 0}

    def _pipeline(**kwargs):  # noqa: ANN003
        active = kwargs.get("llm") or llm
        n["i"] += 1
        # Two LLM calls in one pipeline → second hits budget.
        _ = active.invoke("step-1")
        _ = active.invoke("step-2")
        return {"answer": "should-not", "route": "auto", "quality_score": 90}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=llm)
    result = session.ask("q")

    assert result["route"] == "human"
    assert result["route"] != "auto"
    assert result.get("error") is True
    assert result.get("error_node") == "llm_budget"
    assert primary.calls == 1


def test_settings_defaults_are_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_LLM_MAX_CALLS_PER_REQUEST", raising=False)
    monkeypatch.delenv("RAG_LLM_MAX_INPUT_TOKENS_PER_REQUEST", raising=False)
    monkeypatch.delenv("RAG_LLM_MAX_OUTPUT_TOKENS_PER_REQUEST", raising=False)
    monkeypatch.delenv("RAG_LLM_MAX_TOTAL_TOKENS_PER_REQUEST", raising=False)
    from config.settings import Settings

    s = Settings()
    assert s.llm_max_calls_per_request == 24
    assert s.llm_max_input_tokens_per_request == 48000
    assert s.llm_max_output_tokens_per_request == 8000
    assert s.llm_max_total_tokens_per_request == 50000


def test_charge_and_snapshot() -> None:
    b = rb.bind_llm_request_budget(max_calls=5, max_total_tokens=1000)
    assert b is not None
    b.charge(input_tokens=10, output_tokens=20)
    snap = b.snapshot()
    assert snap["calls"] == 1
    assert snap["input_tokens"] == 10
    assert snap["output_tokens"] == 20
    assert snap["total_tokens"] == 30

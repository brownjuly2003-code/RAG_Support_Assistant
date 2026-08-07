"""Plan §6.3: independent judge policy and evaluate fail-closed."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.judge_policy import (
    judge_fail_closed_fields,
    parse_judge_score,
    resolve_judge_llm,
    same_llm_identity,
)
from agent.state import create_initial_state

agent_graph = importlib.import_module("agent.graph")


def _llm(provider: str, model: str, score: str = "90") -> MagicMock:
    llm = MagicMock()
    llm.provider_id = provider
    llm.model_name = model
    llm.invoke.return_value = score
    return llm


def test_same_llm_identity_by_provider_model() -> None:
    a = _llm("mistral", "ministral-3b")
    b = _llm("mistral", "ministral-3b")
    c = _llm("gracekelly", "claude-sonnet-4-6")
    assert same_llm_identity(a, b) is True
    assert same_llm_identity(a, c) is False


def test_resolve_prefers_independent_when_required() -> None:
    fast = _llm("mistral", "fast-model")
    strong = _llm("gracekelly", "strong-model")
    res = resolve_judge_llm(
        candidate_fast=fast,
        candidate_strong=strong,
        generator_llm=strong,
        require_independence=True,
    )
    assert res.ok is True
    assert res.independent is True
    assert res.judge_llm is fast


def test_resolve_fails_closed_when_no_independent_judge() -> None:
    only = _llm("ollama", "qwen2.5:7b")
    res = resolve_judge_llm(
        candidate_fast=only,
        candidate_strong=only,
        generator_llm=only,
        require_independence=True,
    )
    assert res.ok is False
    assert res.status == "unavailable"
    assert res.reason == "no_independent_judge"


def test_resolve_allows_same_when_independence_not_required() -> None:
    only = _llm("ollama", "qwen2.5:7b")
    res = resolve_judge_llm(
        candidate_fast=only,
        candidate_strong=only,
        generator_llm=only,
        require_independence=False,
    )
    assert res.ok is True
    assert res.judge_llm is only
    assert res.independent is False


def test_parse_judge_score_no_silent_default() -> None:
    assert parse_judge_score("Score: 87") == 87
    assert parse_judge_score("") is None
    assert parse_judge_score("no number here") is None


def test_judge_fail_closed_fields_never_claim_llm() -> None:
    fields = judge_fail_closed_fields(reason="judge_error", status="error")
    assert fields["quality_score"] == 0
    assert fields["quality_source"] == "unmeasured"
    assert fields["grounding_status"] == "not_verified"
    assert fields["judge_status"] == "error"


def test_evaluate_fail_closed_on_judge_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast = _llm("mistral", "fast")
    strong = _llm("gracekelly", "strong")
    fast.invoke.side_effect = RuntimeError("judge down")

    monkeypatch.setattr(
        agent_graph,
        "get_settings",
        lambda: SimpleNamespace(judge_independence_required=True),
    )
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *a, **k: None)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(judge_independence_required=True),
    )

    node = agent_graph.make_evaluate_node(fast, strong)
    state = create_initial_state("q", trace_id="t-judge-err")
    state["complexity"] = "complex"  # generator=strong → judge=fast
    state["answer"] = "Some answer"
    state["grounding_status"] = "verified"
    state["quality_score"] = 95

    out = node(state)
    assert out["quality_score"] == 0
    assert out["quality_source"] == "unmeasured"
    assert out["grounding_status"] == "not_verified"
    assert out["judge_status"] == "error"
    assert out.get("route") is None  # route_or_retry decides human


def test_evaluate_fail_closed_when_independence_required_but_same_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    only = _llm("ollama", "solo")
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(judge_independence_required=True),
    )
    monkeypatch.setattr(agent_graph, "get_settings", lambda: SimpleNamespace(
        judge_independence_required=True
    ))
    monkeypatch.setattr(agent_graph, "log_step", lambda *a, **k: None)

    node = agent_graph.make_evaluate_node(only, only)
    state = create_initial_state("q", trace_id="t-same")
    state["complexity"] = "simple"
    state["answer"] = "Answer"

    out = node(state)
    assert out["judge_status"] == "unavailable"
    assert out["quality_score"] == 0
    assert out["quality_source"] != "llm"
    only.invoke.assert_not_called()


def test_evaluate_uses_independent_judge_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast = _llm("mistral", "fast", score="77")
    strong = _llm("gracekelly", "strong", score="12")
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(judge_independence_required=True),
    )
    monkeypatch.setattr(agent_graph, "get_settings", lambda: SimpleNamespace(
        judge_independence_required=True
    ))
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *a, **k: None)

    node = agent_graph.make_evaluate_node(fast, strong)
    state = create_initial_state("q", trace_id="t-indep")
    state["complexity"] = "complex"
    state["answer"] = "Answer"

    out = node(state)
    assert out["quality_score"] == 77
    assert out["quality_source"] == "llm"
    assert out["judge_status"] == "ok"
    assert out.get("judge_independent") is True
    fast.invoke.assert_called_once()
    strong.invoke.assert_not_called()


def test_evaluate_parse_failure_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast = _llm("mistral", "fast", score="not-a-score")
    strong = _llm("gracekelly", "strong")
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(judge_independence_required=False),
    )
    monkeypatch.setattr(agent_graph, "get_settings", lambda: SimpleNamespace(
        judge_independence_required=False
    ))
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *a, **k: None)

    node = agent_graph.make_evaluate_node(fast, strong)
    state = create_initial_state("q", trace_id="t-parse")
    state["complexity"] = "simple"
    state["answer"] = "Answer"

    out = node(state)
    assert out["quality_score"] == 0
    assert out["judge_status"] == "parse_failure"
    assert out["quality_source"] == "unmeasured"


def test_route_after_judge_unavailable_is_human() -> None:
    node = agent_graph.make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state("q")
    state.update(
        {
            "answer": "x" * 50,
            "quality_score": 0,
            "relevance_score": 0.0,
            "quality_source": "unmeasured",
            "grounding_status": "not_verified",
            "judge_status": "unavailable",
            "context_docs": [{"page_content": "doc"}],
            "knowledge_gap": False,
            "iteration": 0,
            "max_iterations": 2,
        }
    )
    out = node(state)
    assert out["route"] == "human"


def test_build_support_graph_wires_both_llms_to_evaluate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeWorkflow:
        def __init__(self, *_a, **_k) -> None:
            self.nodes: dict[str, object] = {}

        def add_node(self, name: str, node) -> None:
            self.nodes[name] = node

        def set_entry_point(self, _n: str) -> None:
            return None

        def add_edge(self, *_a, **_k) -> None:
            return None

        def add_conditional_edges(self, *_a, **_k) -> None:
            return None

        def compile(self):
            captured["wf"] = self
            return self

    fast = _llm("mistral", "fast", score="82")
    strong = _llm("gracekelly", "strong", score="12")
    monkeypatch.setattr(agent_graph, "StateGraph", FakeWorkflow)
    monkeypatch.setattr(
        agent_graph,
        "build_provider_runtime",
        lambda settings: SimpleNamespace(fast=fast, strong=strong),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            quality_threshold=80,
            judge_independence_required=True,
        ),
    )
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *a, **k: None)
    agent_graph.clear_support_graph_cache()
    agent_graph.build_support_graph(retriever=object(), llm=None)

    state = create_initial_state("Analyze X", trace_id="trace-evaluate")
    state["complexity"] = "complex"
    state["answer"] = "Answer"
    result = captured["wf"].nodes["evaluate"](state)
    # Independence: generator=strong → judge=fast
    assert result["quality_score"] == 82
    fast.invoke.assert_called_once()
    strong.invoke.assert_not_called()

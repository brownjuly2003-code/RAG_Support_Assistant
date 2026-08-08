"""Plan §5.4: retrieval relevance independent of answer quality."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.relevance import (
    RELEVANCE_SOURCE_CONTEXT_KEPT,
    RELEVANCE_SOURCE_EMPTY,
    RELEVANCE_SOURCE_GRADED_FRACTION,
    RELEVANCE_SOURCE_RETRIEVAL_SCORES,
    measure_retrieval_relevance,
)


def test_empty_context_is_zero_not_quality_derived() -> None:
    score, source = measure_retrieval_relevance(context_docs=[], graded_docs=[])
    assert score == 0.0
    assert source == RELEVANCE_SOURCE_EMPTY


def test_graded_fraction_independent_of_quality() -> None:
    context = [{"page_content": f"d{i}"} for i in range(4)]
    graded = context[:3]
    score, source = measure_retrieval_relevance(
        context_docs=context,
        graded_docs=graded,
    )
    assert score == pytest.approx(0.75)
    assert source == RELEVANCE_SOURCE_GRADED_FRACTION


def test_all_docs_rejected_relevance_zero() -> None:
    context = [{"page_content": "noise"}, {"page_content": "more noise"}]
    score, source = measure_retrieval_relevance(
        context_docs=context,
        graded_docs=[],
    )
    assert score == 0.0
    assert source == RELEVANCE_SOURCE_GRADED_FRACTION


def test_retrieval_metadata_scores_mean() -> None:
    docs = [
        {"page_content": "a", "metadata": {"score": 0.9}},
        {"page_content": "b", "metadata": {"score": 0.7}},
    ]
    score, source = measure_retrieval_relevance(context_docs=docs, graded_docs=None)
    assert score == pytest.approx(0.8)
    assert source == RELEVANCE_SOURCE_RETRIEVAL_SCORES


def test_never_uses_quality_score_kwarg() -> None:
    """API must not accept quality as a relevance input (regression guard)."""
    score, source = measure_retrieval_relevance(
        context_docs=[{"page_content": "x"}],
        graded_docs=[{"page_content": "x"}],
    )
    # Full keep → fraction 1.0; quality is irrelevant to this function.
    assert score == pytest.approx(1.0)
    assert source == RELEVANCE_SOURCE_GRADED_FRACTION
    assert not hasattr(measure_retrieval_relevance, "quality_score")


def test_context_only_without_scores_is_full_keep_not_quality() -> None:
    """Agentic search hits without metadata scores: keep-all, not quality/100."""
    score, source = measure_retrieval_relevance(
        context_docs=[{"page_content": "only text"}],
        graded_docs=None,
    )
    assert score == pytest.approx(1.0)
    assert source == RELEVANCE_SOURCE_CONTEXT_KEPT


def test_evaluate_node_sets_relevance_not_quality_over_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """make_evaluate_node must not set relevance = quality/100."""
    from agent.graph import make_evaluate_node

    class _Judge:
        def invoke(self, prompt: str, **kwargs):  # noqa: ANN003
            _ = prompt, kwargs
            return "90"

    # Patch the name bound inside agent.graph (already imported).
    import agent.graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "resolve_judge_llm",
        lambda **kwargs: SimpleNamespace(
            ok=True,
            judge_llm=_Judge(),
            independent=True,
            reason="test",
            judge_provider="test",
            judge_model="test",
            provider_id="test",
            model_name="test",
        ),
    )

    node = make_evaluate_node(_Judge(), _Judge())
    state = {
        "question": "q?",
        "answer": "a",
        "context_docs": [
            {"page_content": "c1"},
            {"page_content": "c2"},
            {"page_content": "c3"},
            {"page_content": "c4"},
        ],
        "graded_docs": [
            {"page_content": "c1"},
            {"page_content": "c2"},
        ],
        "error": False,
        "trace_id": "t-rel-1",
        "tenant_id": "default",
        "tool_calls": [],
    }
    out = node(state)
    assert out["quality_score"] == 90
    # Independent: 2/4 graded, not 0.90 from quality.
    assert out["relevance_score"] == pytest.approx(0.5)
    assert out.get("relevance_source") == RELEVANCE_SOURCE_GRADED_FRACTION
    assert out["relevance_score"] != pytest.approx(0.9)


def test_agentic_evaluate_relevance_not_quality_over_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from agent.agentic_evaluate import evaluate_agentic_answer

    judge = MagicMock()
    judge.provider_id = "mistral"
    judge.model_name = "fast"
    judge.invoke.return_value = "88"
    gen = MagicMock()
    gen.provider_id = "other"
    gen.model_name = "strong"

    docs = [
        {"page_content": "policy A", "metadata": {"score": 0.6}},
        {"page_content": "policy B", "metadata": {"score": 0.4}},
    ]
    result = evaluate_agentic_answer(
        question="q",
        answer="a [1]",
        context_docs=docs,
        candidate_fast=judge,
        candidate_strong=gen,
        generator_llm=gen,
        require_independence=True,
    )
    assert result.measured is True
    assert result.quality_score == 88
    assert result.relevance_score == pytest.approx(0.5)
    assert result.relevance_score != pytest.approx(0.88)


def test_agentic_measure_does_not_derive_relevance_from_quality() -> None:
    from agent.agentic_measure import measure_agentic_terminal

    docs = [
        {
            "page_content": "Гарантия 3 года на двигатель.",
            "metadata": {"doc_id": "d1", "score": 0.4},
        }
    ]
    fields = measure_agentic_terminal(
        answer="Гарантия 3 года [1]",
        kb_docs=docs,
        quality_score=95,
        quality_source="llm",
        # no relevance_score passed — must not become 0.95
    )
    assert fields["quality_score"] == 95
    assert float(fields["relevance_score"]) == pytest.approx(0.4)
    assert float(fields["relevance_score"]) != pytest.approx(0.95)

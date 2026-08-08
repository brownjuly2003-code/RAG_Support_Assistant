"""Plan §6.6: agentic LLM evaluate wire on KB terminals."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.agentic_evaluate import (
    agentic_quality_eval_enabled,
    evaluate_agentic_answer,
)
from agent.agentic_measure import measure_agentic_terminal


def _llm(provider: str, model: str, score: str = "90") -> MagicMock:
    llm = MagicMock()
    llm.provider_id = provider
    llm.model_name = model
    llm.invoke.return_value = score
    return llm


def test_no_kb_context_skips_evaluate() -> None:
    result = evaluate_agentic_answer(
        question="q",
        answer="a",
        context_docs=None,
        candidate_fast=_llm("mistral", "fast"),
    )
    assert result.measured is False
    assert result.quality_source is None
    assert result.judge_reason == "no_kb_context"


def test_empty_answer_skips_evaluate() -> None:
    docs = [{"page_content": "policy text"}]
    result = evaluate_agentic_answer(
        question="q",
        answer="  ",
        context_docs=docs,
        candidate_fast=_llm("mistral", "fast"),
    )
    assert result.measured is False
    assert result.judge_reason == "empty_answer"


def test_measured_llm_score_on_success() -> None:
    docs = [{"page_content": "доставка в Москву стоит 500 ₽"}]
    judge = _llm("mistral", "fast", score="Score: 92")
    generator = _llm("gracekelly", "strong", score="unused")
    result = evaluate_agentic_answer(
        question="Сколько доставка?",
        answer="Доставка стоит 500 ₽ [1]",
        context_docs=docs,
        candidate_fast=judge,
        candidate_strong=generator,
        generator_llm=generator,
        require_independence=True,
    )
    assert result.measured is True
    assert result.quality_source == "llm"
    assert result.quality_score == 92
    # Plan §5.4: relevance is retrieval keep-all for unscored docs — not 0.92.
    assert result.relevance_score == pytest.approx(1.0)
    assert result.relevance_score != pytest.approx(0.92)
    assert result.judge_status == "ok"
    assert result.judge_independent is True
    kwargs = result.as_measure_kwargs()
    assert kwargs["quality_source"] == "llm"
    assert kwargs["quality_score"] == 92


def test_parse_failure_fail_closed() -> None:
    docs = [{"page_content": "policy"}]
    judge = _llm("mistral", "fast", score="not a number")
    result = evaluate_agentic_answer(
        question="q",
        answer="a [1]",
        context_docs=docs,
        candidate_fast=judge,
        require_independence=False,
    )
    assert result.measured is False
    assert result.quality_source is None
    assert result.judge_status == "parse_failure"
    assert result.as_measure_kwargs() == {}


def test_judge_error_fail_closed() -> None:
    docs = [{"page_content": "policy"}]
    judge = _llm("mistral", "fast")
    judge.invoke.side_effect = RuntimeError("boom")
    result = evaluate_agentic_answer(
        question="q",
        answer="a [1]",
        context_docs=docs,
        candidate_fast=judge,
        require_independence=False,
    )
    assert result.measured is False
    assert result.judge_status == "error"
    assert "judge_error" in result.judge_reason


def test_no_independent_judge_fail_closed() -> None:
    docs = [{"page_content": "policy"}]
    only = _llm("ollama", "qwen")
    result = evaluate_agentic_answer(
        question="q",
        answer="a [1]",
        context_docs=docs,
        candidate_fast=only,
        candidate_strong=only,
        generator_llm=only,
        require_independence=True,
    )
    assert result.measured is False
    assert result.judge_status == "unavailable"
    assert result.judge_reason == "no_independent_judge"


def test_measure_gate_auto_when_evaluate_supplies_llm() -> None:
    """§6.6 → §6.5: measured llm quality + citations can unlock auto."""
    docs = [{"page_content": "возврат в течение 14 дней"}]
    answer = "Можно вернуть заказ [1] в течение 14 дней."
    eval_result = evaluate_agentic_answer(
        question="Как вернуть?",
        answer=answer,
        context_docs=docs,
        candidate_fast=_llm("mistral", "fast", score="88"),
        require_independence=False,
    )
    fields = measure_agentic_terminal(
        answer=answer,
        kb_docs=docs,
        **eval_result.as_measure_kwargs(),
        min_quality=80,
        min_factuality=80,
        min_relevance=0.8,
    )
    assert fields["quality_source"] == "llm"
    assert fields["quality_score"] == 88
    assert fields["grounding_status"] == "verified"
    assert fields["route"] == "auto"
    assert fields["agentic_measure"] == "kb_grounding+quality"


def test_judge_failure_keeps_grounding_not_auto() -> None:
    """Judge fail must not invent quality; grounding still measured if citations."""
    docs = [{"page_content": "policy text long enough"}]
    answer = "[1] policy text long enough"
    eval_result = evaluate_agentic_answer(
        question="q",
        answer=answer,
        context_docs=docs,
        candidate_fast=_llm("mistral", "fast", score="n/a"),
        require_independence=False,
    )
    fields = measure_agentic_terminal(
        answer=answer,
        kb_docs=docs,
        **eval_result.as_measure_kwargs(),
    )
    fields = {**fields, **eval_result.as_state_fields()}
    assert fields["quality_source"] == "unmeasured"
    assert fields["quality_score"] == 0
    assert fields["route"] == "agentic"
    assert fields["grounding_status"] == "verified"
    assert fields["judge_status"] == "parse_failure"


def test_agentic_quality_eval_flag() -> None:
    assert agentic_quality_eval_enabled(None) is True
    assert agentic_quality_eval_enabled(SimpleNamespace(agentic_quality_eval=True)) is True
    assert agentic_quality_eval_enabled(SimpleNamespace(agentic_quality_eval=False)) is False

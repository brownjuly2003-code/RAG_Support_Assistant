"""Plan §6.5: measured agentic terminal when KB context exists."""

from __future__ import annotations

from agent.agentic_measure import (
    has_kb_context,
    measure_agentic_terminal,
    normalize_context_docs,
    unmeasured_agentic_fields,
)


def test_no_kb_docs_is_unmeasured() -> None:
    fields = measure_agentic_terminal(answer="hello", kb_docs=None)
    assert fields["quality_source"] == "unmeasured"
    assert fields["route"] == "agentic"
    assert fields["grounding_status"] == "not_verified"
    assert fields["quality_score"] == 0


def test_kb_docs_without_citations_not_auto() -> None:
    docs = [{"page_content": "доставка стоит 500 рублей"}]
    fields = measure_agentic_terminal(
        answer="Доставка стоит 500 рублей",
        kb_docs=docs,
    )
    assert fields["route"] == "agentic"
    assert fields["quality_source"] == "unmeasured"
    assert fields["grounding_status"] == "not_verified"
    assert fields["agentic_measure"] == "kb_context_no_citations"
    assert fields["context_docs"]


def test_kb_docs_with_citations_measures_grounding() -> None:
    docs = [{"page_content": "доставка в Москву стоит 500 ₽"}]
    answer = "[1] доставка в Москву стоит 500 ₽"
    fields = measure_agentic_terminal(answer=answer, kb_docs=docs)
    assert fields["grounding_status"] == "verified"
    assert fields["fact_verification_skipped"] is False
    assert fields["factuality_score"] == 100
    assert fields["agentic_measure"] == "kb_grounding"
    # No evaluate score → still not auto
    assert fields["quality_source"] == "unmeasured"
    assert fields["route"] == "agentic"


def test_measured_quality_plus_grounding_can_auto() -> None:
    docs = [{"page_content": "возврат в течение 14 дней"}]
    answer = "Можно вернуть заказ [1] в течение 14 дней."
    fields = measure_agentic_terminal(
        answer=answer,
        kb_docs=docs,
        quality_score=90,
        relevance_score=0.9,
        quality_source="llm",
        min_quality=80,
        min_factuality=80,
        min_relevance=0.8,
    )
    assert fields["quality_source"] == "llm"
    assert fields["quality_score"] == 90
    assert fields["grounding_status"] == "verified"
    assert fields["route"] == "auto"
    assert fields["agentic_measure"] == "kb_grounding+quality"


def test_fixed_quality_source_rejected() -> None:
    docs = [{"page_content": "policy text here"}]
    answer = "[1] policy text here"
    fields = measure_agentic_terminal(
        answer=answer,
        kb_docs=docs,
        quality_score=85,
        quality_source="fixed",
    )
    assert fields["quality_source"] == "unmeasured"
    assert fields["quality_score"] == 0
    assert fields["route"] != "auto"


def test_low_quality_blocks_auto() -> None:
    docs = [{"page_content": "policy text long enough"}]
    answer = "[1] policy text long enough"
    fields = measure_agentic_terminal(
        answer=answer,
        kb_docs=docs,
        quality_score=50,
        relevance_score=0.5,
        quality_source="llm",
        min_quality=80,
        min_factuality=80,
        min_relevance=0.8,
    )
    assert fields["route"] == "agentic"
    assert fields["quality_source"] == "llm"


def test_normalize_and_has_context() -> None:
    assert has_kb_context(None) is False
    assert has_kb_context([]) is False
    assert has_kb_context([{"page_content": "x"}]) is True
    assert normalize_context_docs([{"page_content": "a"}])[0]["page_content"] == "a"
    assert unmeasured_agentic_fields()["quality_source"] == "unmeasured"

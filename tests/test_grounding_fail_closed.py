"""5.1 — grounding fail-closed foundations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent import grounding as g
from agent.graph import make_route_or_retry_node, make_verify_facts_node
from agent.state import create_initial_state


def test_status_helpers_never_fake_100_on_skip() -> None:
    status, score, skipped = g.status_for_skip(reason="disabled")
    assert status == "not_verified"
    assert score == 0
    assert skipped is True

    status, score, skipped = g.status_for_short_answer()
    assert status == "not_verified"
    assert score == 0

    status, score, skipped = g.status_for_no_claims_none()
    assert status == "verified"
    assert score == 0  # not 100


def test_status_for_claims_partial_and_full() -> None:
    st, score, _ = g.status_for_claims(
        [{"supported": True}, {"supported": False}]
    )
    assert st == "unsupported"
    assert score == 50

    st, score, _ = g.status_for_claims(
        [{"supported": True}, {"supported": True}]
    )
    assert st == "verified"
    assert score == 100

    # §5.2: without citation_bound, effective support is zero when required.
    st, score, _ = g.status_for_claims(
        [{"supported": True, "citation_bound": False}],
        require_citation_bound=True,
    )
    assert st == "unsupported"
    assert score == 0


def test_grounding_allows_auto_requires_verified_and_context() -> None:
    base = {
        "error": False,
        "knowledge_gap": False,
        "graded_docs": [{"page_content": "x"}],
        "grounding_status": "verified",
        "factuality_score": 100,
        "claims": [{"supported": True, "citation_bound": True}],
    }
    assert g.grounding_allows_auto(base) is True

    no_ctx = {**base, "graded_docs": [], "context_docs": []}
    assert g.grounding_allows_auto(no_ctx) is False

    not_v = {**base, "grounding_status": "not_verified"}
    assert g.grounding_allows_auto(not_v) is False

    gap = {**base, "knowledge_gap": True}
    assert g.grounding_allows_auto(gap) is False

    low = {**base, "factuality_score": 50}
    assert g.grounding_allows_auto(low) is False

    unbound = {
        **base,
        "claims": [{"supported": True, "citation_bound": False}],
    }
    assert g.grounding_allows_auto(unbound) is False


def test_verify_disabled_is_not_verified_not_100(monkeypatch: pytest.MonkeyPatch) -> None:
    import config.settings as settings_module

    monkeypatch.setenv("FACT_VERIFICATION_ENABLED", "false")
    settings_module._settings = None

    llm = MagicMock()
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Something factual looking."
    state["graded_docs"] = [{"page_content": "evidence"}]

    out = node(state)
    assert out["fact_verification_skipped"] is True
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "not_verified"
    llm.invoke.assert_not_called()
    settings_module._settings = None


def test_verify_no_context_not_100() -> None:
    llm = MagicMock()
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Answer without docs."
    state["graded_docs"] = []
    state["context_docs"] = []

    out = node(state)
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "not_verified"
    assert out["fact_verification_skipped"] is True


def test_verify_none_claims_vacuous_verified_score_0() -> None:
    llm = MagicMock()
    llm.invoke.return_value = "NONE"
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Привет! Как дела?"
    state["graded_docs"] = [{"page_content": "anything"}]

    out = node(state)
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "verified"
    assert out["claims"] == []


def test_verify_all_supported_verified() -> None:
    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was released in 1991.\n- It is open source.",
        "SUPPORTED: Python released 1991",
        "SUPPORTED: Python is open source",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Python was released in 1991 [1] and is open source [1]."
    state["graded_docs"] = [{"page_content": "Python 1.0 released 1991. Open source."}]

    out = node(state)
    assert out["factuality_score"] == 100
    assert out["grounding_status"] == "verified"


def test_route_blocks_auto_when_not_verified() -> None:
    node = make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state(question="q", trace_id="t")
    state["quality_score"] = 95
    state["relevance_score"] = 0.95
    state["knowledge_gap"] = False
    state["graded_docs"] = [{"page_content": "x"}]
    state["grounding_status"] = "not_verified"
    state["factuality_score"] = 0
    state["claims"] = []
    state["iteration"] = 2
    state["max_iterations"] = 2

    out = node(state)
    assert out["route"] == "human"


def test_route_allows_auto_when_grounding_ok() -> None:
    node = make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state(question="q", trace_id="t")
    state["quality_score"] = 95
    state["relevance_score"] = 0.95
    state["knowledge_gap"] = False
    state["graded_docs"] = [{"page_content": "x"}]
    state["grounding_status"] = "verified"
    state["factuality_score"] = 100
    state["claims"] = [{"text": "c", "supported": True, "citation_bound": True}]

    out = node(state)
    assert out["route"] == "auto"


def test_route_blocks_auto_on_knowledge_gap_even_if_scores_high() -> None:
    node = make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state(question="q", trace_id="t")
    state["quality_score"] = 99
    state["relevance_score"] = 0.99
    state["knowledge_gap"] = True
    state["graded_docs"] = [{"page_content": "x"}]
    state["grounding_status"] = "verified"
    state["factuality_score"] = 100
    state["claims"] = [{"supported": True, "citation_bound": True}]
    state["iteration"] = 2
    state["max_iterations"] = 2

    out = node(state)
    assert out["route"] != "auto"

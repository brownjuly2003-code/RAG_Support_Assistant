"""5.2 — citation-bound claim support for auto."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent import grounding as g
from agent.graph import make_route_or_retry_node, make_verify_facts_node
from agent.state import create_initial_state


def test_parse_answer_citation_indices() -> None:
    assert g.parse_answer_citation_indices("See policy [1] and FAQ [2].") == [1, 2]
    assert g.parse_answer_citation_indices("no citations") == []
    assert g.parse_answer_citation_indices("dup [1] again [1]") == [1]


def test_missing_citations_force_not_verified() -> None:
    claims = [
        {
            "text": "Return window is 14 days",
            "supported": True,
            "evidence": "Return window is 14 days",
        }
    ]
    docs = [{"page_content": "Return window is 14 days with receipt."}]
    updated, override = g.apply_citation_bound_claims(
        answer="Return window is 14 days.",  # no [N]
        claims=claims,
        docs=docs,
    )
    assert override == "not_verified"
    assert updated[0]["citation_bound"] is False

    status, score, _ = g.status_for_claims(updated, require_citation_bound=True)
    assert status == "unsupported"
    assert score == 0


def test_claim_bound_to_cited_doc_verified() -> None:
    claims = [
        {
            "text": "Return window is 14 days",
            "supported": True,
            "evidence": "Return window is 14 days",
        }
    ]
    docs = [
        {"page_content": "Return window is 14 days with receipt."},
        {"page_content": "Unrelated warehouse hours only."},
    ]
    updated, override = g.apply_citation_bound_claims(
        answer="Return window is 14 days [1].",
        claims=claims,
        docs=docs,
    )
    assert override is None
    assert updated[0]["citation_bound"] is True
    assert 1 in updated[0]["citation_indices"]

    status, score, _ = g.status_for_claims(updated, require_citation_bound=True)
    assert status == "verified"
    assert score == 100


def test_evidence_only_in_uncited_doc_not_bound() -> None:
    claims = [
        {
            "text": "Refund takes 30 days",
            "supported": True,
            "evidence": "Refund takes 30 days",
        }
    ]
    docs = [
        {"page_content": "Shipping is free over 50."},  # [1] cited but no evidence
        {"page_content": "Refund takes 30 days after approval."},  # [2] uncited
    ]
    updated, override = g.apply_citation_bound_claims(
        answer="Refund takes 30 days [1].",
        claims=claims,
        docs=docs,
    )
    assert override is None
    assert updated[0]["citation_bound"] is False

    status, score, _ = g.status_for_claims(updated, require_citation_bound=True)
    assert status == "unsupported"
    assert score == 0


def test_invalid_citation_index_not_verified() -> None:
    claims = [
        {
            "text": "Something true enough",
            "supported": True,
            "evidence": "Something true enough for binding",
        }
    ]
    docs = [{"page_content": "Something true enough for binding here."}]
    updated, override = g.apply_citation_bound_claims(
        answer="Something true enough [9].",
        claims=claims,
        docs=docs,
    )
    assert override == "not_verified"
    assert updated[0]["citation_bound"] is False


def test_verify_facts_requires_citation_for_supported_claims() -> None:
    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was released in 1991.",
        "SUPPORTED: Python released 1991",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    # Answer without [N] despite a factual claim.
    state["answer"] = "Python was released in 1991."
    state["graded_docs"] = [{"page_content": "Python 1.0 released 1991. Open source."}]

    out = node(state)
    assert out["grounding_status"] == "not_verified"
    assert out["claims"]
    assert out["claims"][0].get("citation_bound") is False


def test_verify_facts_with_citation_stays_verified() -> None:
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
    assert out["grounding_status"] == "verified"
    assert out["factuality_score"] == 100
    assert all(c.get("citation_bound") for c in out["claims"])


def test_auto_blocked_without_citation_bound() -> None:
    node = make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state(question="q", trace_id="t")
    state["quality_score"] = 95
    state["relevance_score"] = 0.95
    state["knowledge_gap"] = False
    state["graded_docs"] = [{"page_content": "x"}]
    state["grounding_status"] = "verified"  # should not trust without binds
    state["factuality_score"] = 100
    state["claims"] = [
        {"text": "fact", "supported": True, "citation_bound": False},
    ]
    state["iteration"] = 2
    state["max_iterations"] = 2

    out = node(state)
    assert out["route"] != "auto"


def test_auto_allowed_when_claims_citation_bound() -> None:
    node = make_route_or_retry_node(min_quality=80, min_relevance=0.8)
    state = create_initial_state(question="q", trace_id="t")
    state["quality_score"] = 95
    state["relevance_score"] = 0.95
    state["knowledge_gap"] = False
    state["graded_docs"] = [{"page_content": "x"}]
    state["grounding_status"] = "verified"
    state["factuality_score"] = 100
    state["claims"] = [
        {
            "text": "fact about returns",
            "supported": True,
            "citation_bound": True,
            "citation_indices": [1],
        },
    ]

    out = node(state)
    assert out["route"] == "auto"

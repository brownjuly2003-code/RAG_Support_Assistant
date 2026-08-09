"""Тесты узла verify_facts."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_all_supported_claims_give_score_100() -> None:
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was released in 1991.\n- It is open source.",
        "SUPPORTED: Python released 1991",
        "SUPPORTED: Python is open source",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    # §5.2: substantial claims require answer citations [N].
    state["answer"] = "Python was released in 1991 [1] and is open source [1]."
    state["graded_docs"] = [{"page_content": "Python 1.0 released 1991. Open source."}]

    out = node(state)

    assert out["factuality_score"] == 100
    assert out["grounding_status"] == "verified"
    assert all(claim["supported"] for claim in out["claims"])
    assert all(claim.get("citation_bound") for claim in out["claims"])


def test_mixed_claims_give_partial_score() -> None:
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was created by Guido.\n- Python was created in 1987.",
        "SUPPORTED: Python created by Guido",
        "UNSUPPORTED",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Python was created by Guido in 1987 [1]."
    state["graded_docs"] = [{"page_content": "Python was created by Guido van Rossum."}]

    out = node(state)

    # One claim citation-bound+supported, one unsupported → 50 and not verified auto.
    assert out["factuality_score"] == 50
    assert out["grounding_status"] == "unsupported"


def test_no_claims_answer_vacuous_verified_not_100() -> None:
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    llm.invoke.return_value = "NONE"
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Привет! Как дела?"
    state["graded_docs"] = [{"page_content": "anything"}]

    out = node(state)

    # Plan §5.1: NONE is not a free factuality 100.
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "verified"
    assert out["claims"] == []


def test_disabled_via_settings_skips_verification(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    monkeypatch.setenv("FACT_VERIFICATION_ENABLED", "false")
    settings_module._settings = None

    llm = MagicMock()
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "x"
    state["graded_docs"] = [{"page_content": "y"}]

    out = node(state)

    assert out["fact_verification_skipped"] is True
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "not_verified"
    llm.invoke.assert_not_called()

    settings_module._settings = None


def test_verifier_provider_outage_fail_closed_preserves_answer_routes_human() -> None:
    """QG-03: verifier LLM transport failure must not escalate via handle_error.

    A generated answer must be preserved fail-closed (human route, not_verified),
    bypassing evaluate / handle_error while still reaching the safety/log lane.
    """
    import agent.graph as agent_graph
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    # Transport-class failure analogous to httpx.ReadError / WinError 10054.
    llm.invoke.side_effect = RuntimeError("simulated verifier transport failure")
    node = make_verify_facts_node(llm)

    answer = "Проверьте фильтр и насос при ошибке E20 [1]."
    citations = [{"index": 1, "source": "manual.md"}]
    graded = [{"page_content": "E20: filter clog or pump fault."}]
    context = [{"page_content": "E20 diagnostics context"}]

    state = create_initial_state(question="Что проверить при E20?", trace_id="t-qg03")
    state["answer"] = answer
    state["citations"] = citations
    state["graded_docs"] = graded
    state["context_docs"] = context
    state["complexity"] = "complex"
    state["error"] = False

    out = node(state)

    # Generic graph error boundary must NOT fire for expected provider outage.
    assert out.get("error") is False
    assert out.get("route") == "human"
    assert out.get("route") not in {"auto", "retry", "error", "error_escalation"}

    # Preserve already-generated answer and retrieval artifacts.
    assert out["answer"] == answer
    assert out["citations"] == citations
    assert out["graded_docs"] == graded
    assert out["context_docs"] == context

    # Fail-closed verification provenance (no secret / stack payload).
    assert out["claims"] == []
    assert out["factuality_score"] == 0
    assert out["grounding_status"] == "not_verified"
    assert out["fact_verification_skipped"] is True
    reason = out.get("fact_verification_error") or ""
    assert reason
    assert "provider_error" in reason
    assert "Traceback" not in reason
    assert "simulated verifier transport failure" not in reason

    # Post-verify branch: skip evaluate + handle_error → safety/log terminal.
    route_fn = getattr(agent_graph, "_route_after_verify_facts", None)
    assert callable(route_fn), "_route_after_verify_facts must wire the fail-closed branch"
    branch = route_fn(out)
    assert branch == "safety"
    assert branch not in {"evaluate", "error"}


def test_verify_facts_records_trace_calls(monkeypatch) -> None:
    import agent.graph as graph
    import config.settings as settings_module
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(
            fact_verification_enabled=True,
            fact_verify_consensus_enabled=False,
            fact_verify_reliability_level="standard",
        ),
    )
    captured: list[dict] = []
    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: captured.append(kwargs))

    llm = MagicMock()
    llm.provider_id = "mistral"
    llm.model_name = "mistral-small-latest"
    llm.invoke.side_effect = [
        "- Возврат доступен 14 дней.\n- Чек не требуется.",
        "SUPPORTED: 14 days",
        "UNSUPPORTED",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="trace-facts")
    state["answer"] = "Возврат доступен 14 дней [1], чек не требуется [1]."
    state["graded_docs"] = [{"page_content": "Возврат доступен 14 дней при наличии чека."}]

    out = node(state)

    assert out["factuality_score"] == 50
    assert out["grounding_status"] == "unsupported"
    assert [item["node_name"] for item in captured] == [
        "verify_facts.extract_claims",
        "verify_facts.verify_claim",
        "verify_facts.verify_claim",
    ]
    assert all(item["trace_id"] == "trace-facts" for item in captured)

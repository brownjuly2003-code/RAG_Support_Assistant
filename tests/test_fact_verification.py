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
    state["answer"] = "Python was released in 1991 and is open source."
    state["graded_docs"] = [{"page_content": "Python 1.0 released 1991. Open source."}]

    out = node(state)

    assert out["factuality_score"] == 100
    assert all(claim["supported"] for claim in out["claims"])


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
    state["answer"] = "Python was created by Guido in 1987."
    state["graded_docs"] = [{"page_content": "Python was created by Guido van Rossum."}]

    out = node(state)

    assert out["factuality_score"] == 50


def test_no_claims_answer_scores_100() -> None:
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    llm.invoke.return_value = "NONE"
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Привет! Как дела?"
    state["graded_docs"] = [{"page_content": "anything"}]

    out = node(state)

    assert out["factuality_score"] == 100
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
    assert out["factuality_score"] == 100
    llm.invoke.assert_not_called()

    settings_module._settings = None


def test_llm_error_produces_error_state() -> None:
    from agent.graph import make_verify_facts_node
    from agent.state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("ollama down")
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "anything"
    state["graded_docs"] = [{"page_content": "y"}]

    out = node(state)

    assert out.get("error") is not None


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
    state["answer"] = "Возврат доступен 14 дней, чек не требуется."
    state["graded_docs"] = [{"page_content": "Возврат доступен 14 дней при наличии чека."}]

    out = node(state)

    assert out["factuality_score"] == 50
    assert [item["node_name"] for item in captured] == [
        "verify_facts.extract_claims",
        "verify_facts.verify_claim",
        "verify_facts.verify_claim",
    ]
    assert all(item["trace_id"] == "trace-facts" for item in captured)

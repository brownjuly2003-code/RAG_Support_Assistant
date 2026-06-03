"""Тесты classify_complexity и routing по моделям."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_classifier_returns_simple_and_records_metric(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_classify_complexity_node
    from agent.state import create_initial_state
    from monitoring.prometheus import MODEL_ROUTING, PROMETHEUS_AVAILABLE

    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "true")
    settings_module._settings = None

    def _sum(complexity: str) -> float:
        for metric in MODEL_ROUTING.collect():
            for sample in metric.samples:
                if sample.labels.get("complexity") == complexity and sample.name.endswith("_total"):
                    return sample.value
        return 0.0

    before = _sum("simple") if PROMETHEUS_AVAILABLE else 0.0
    llm = MagicMock()
    llm.invoke.return_value = "SIMPLE"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="How to reset password?", trace_id="t")

    out = node(state)

    assert out["complexity"] == "simple"
    if PROMETHEUS_AVAILABLE:
        assert _sum("simple") > before

    settings_module._settings = None


def test_classifier_returns_complex_on_complex_question(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_classify_complexity_node
    from agent.state import create_initial_state

    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "true")
    settings_module._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "COMPLEX"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="Compare X and Y in detail", trace_id="t")

    out = node(state)

    assert out["complexity"] == "complex"

    settings_module._settings = None


def test_classifier_returns_global_on_global_question(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_classify_complexity_node
    from agent.state import create_initial_state

    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "true")
    settings_module._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "GLOBAL"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="Какие политики связаны с договором X?", trace_id="t")

    out = node(state)

    assert out["complexity"] == "global"

    settings_module._settings = None


def test_ambiguous_response_defaults_to_complex(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_classify_complexity_node
    from agent.state import create_initial_state

    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "true")
    settings_module._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "something off-script"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="?", trace_id="t")

    out = node(state)

    assert out["complexity"] == "complex"

    settings_module._settings = None


def test_routing_disabled_skips_classification(monkeypatch) -> None:
    import config.settings as settings_module
    from agent.graph import make_classify_complexity_node
    from agent.state import create_initial_state

    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "false")
    settings_module._settings = None

    llm = MagicMock()
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="?", trace_id="t")

    out = node(state)

    assert out["complexity"] == "unknown"
    llm.invoke.assert_not_called()

    settings_module._settings = None


def test_generate_and_evaluate_route_by_complexity() -> None:
    from agent.graph import make_evaluate_node, make_generate_node
    from agent.state import create_initial_state

    llm_fast = MagicMock()
    llm_fast.invoke.side_effect = ["fast answer", "75"]
    llm_strong = MagicMock()
    llm_strong.invoke.side_effect = ["strong answer", "90"]

    generate_node = make_generate_node(llm_fast, llm_strong)
    evaluate_node = make_evaluate_node(llm_fast, llm_strong)

    simple_state = create_initial_state(question="How to reset password?", trace_id="simple")
    simple_state["complexity"] = "simple"
    simple_generated = generate_node(simple_state)
    simple_evaluated = evaluate_node(simple_generated)

    complex_state = create_initial_state(question="Analyze contract X", trace_id="complex")
    complex_state["complexity"] = "complex"
    complex_generated = generate_node(complex_state)
    complex_evaluated = evaluate_node(complex_generated)

    assert simple_generated["answer"] == "fast answer"
    assert simple_evaluated["quality_score"] == 75
    assert complex_generated["answer"] == "strong answer"
    assert complex_evaluated["quality_score"] == 90
    assert llm_fast.invoke.call_count == 2
    assert llm_strong.invoke.call_count == 2


def test_simple_graph_fast_path_skips_grade_docs_and_verify(monkeypatch) -> None:
    import agent.graph as graph
    import config.settings as settings_module
    from agent.state import create_initial_state

    settings = SimpleNamespace(
        model_routing_enabled=True,
        quality_threshold=80,
        hyde=False,
        suggested_questions_enabled=False,
        fact_verification_enabled=True,
        retrieval_strategy="hybrid",
    )
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda *args, **kwargs: None)

    class _Retriever:
        def get_relevant_documents(self, query: str):
            assert query == "password reset"
            return [
                SimpleNamespace(
                    page_content="Password reset instructions.",
                    metadata={"source": "reset.md"},
                )
            ]

    llm = MagicMock()
    llm.invoke.side_effect = ["SIMPLE", "password reset", "Answer", "95"]

    support_graph = graph.build_support_graph(retriever=_Retriever(), llm=llm)
    final_state = support_graph.invoke(
        create_initial_state(question="How to reset password?", trace_id="simple-fast-path")
    )

    assert final_state["complexity"] == "simple"
    assert final_state["route"] == "auto"
    assert final_state["doc_grade_reason"] is None
    assert final_state["claims"] == []
    assert final_state["fact_verification_skipped"] is True
    assert final_state["factuality_score"] == 100
    assert llm.invoke.call_count == 4

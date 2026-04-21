import importlib
import types
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pytest

from agent.state import create_initial_state

graph = importlib.import_module("agent.graph")


def test_handle_error_triggered_when_node_raises() -> None:
    retriever = Mock()
    retriever.get_relevant_documents.return_value = []

    support_graph = graph.build_support_graph(
        retriever=retriever,
        llm=Mock(),
    )
    initial_state = create_initial_state(
        question="Почему пайплайн упал?",
        trace_id="trace-error-1",
    )

    with (
        patch(
            "agent.graph.build_query_transform_prompt",
            side_effect=RuntimeError("Сбой трансформации запроса"),
        ),
        patch("agent.graph._escalate_to_inbox") as escalate_to_inbox,
        patch("agent.graph.log_step"),
    ):
        final_state = support_graph.invoke(initial_state)

    assert final_state["error"] is True
    assert final_state["error_node"] == "transform_query"
    assert "RuntimeError: Сбой трансформации запроса" in final_state["error_message"]
    assert "Ваш вопрос передан оператору" in final_state["answer"]
    assert final_state["route"] == "error_escalation"
    escalate_to_inbox.assert_called_once()
    escalated_state = escalate_to_inbox.call_args.args[0]
    assert escalated_state["error"] is True
    assert escalated_state["route"] == "error"
    assert escalated_state["answer"] is None


@pytest.mark.parametrize(
    ("node_name", "patch_target", "llm_responses"),
    [
        ("retrieve", "agent.graph._docs_to_plain_dicts", ["поисковый запрос"]),
        ("grade_docs", "agent.graph.build_doc_grade_prompt", ["поисковый запрос"]),
        ("generate", "agent.graph.build_qa_prompt", ["поисковый запрос", "YES"]),
        (
            "evaluate",
            "agent.graph.build_self_eval_prompt",
            ["поисковый запрос", "YES", "Сформированный ответ"],
        ),
        (
            "route_or_retry",
            None,
            ["поисковый запрос", "YES", "Сформированный ответ", "95"],
        ),
    ],
)
def test_handle_error_triggered_for_remaining_nodes(
    node_name: str,
    patch_target: str | None,
    llm_responses: list[str],
) -> None:
    retriever = Mock()
    retriever.get_relevant_documents.return_value = [
        types.SimpleNamespace(
            page_content="Инструкция по восстановлению пайплайна",
            metadata={"source": "kb.md"},
        )
    ]
    llm = Mock()
    llm.invoke.side_effect = llm_responses

    support_graph = graph.build_support_graph(
        retriever=retriever,
        llm=llm,
    )
    initial_state = create_initial_state(
        question="Почему пайплайн упал?",
        trace_id=f"trace-error-{node_name}",
    )

    def log_step_side_effect(trace_id, current_node, state):
        _ = (trace_id, state)
        if node_name == "route_or_retry" and current_node == "route_or_retry":
            raise RuntimeError("Сбой route_or_retry")
        return None

    failing_patch = (
        patch(
            patch_target,
            side_effect=RuntimeError(f"Сбой узла {node_name}"),
        )
        if patch_target is not None
        else nullcontext()
    )

    with (
        failing_patch,
        patch("agent.graph._escalate_to_inbox") as escalate_to_inbox,
        patch("agent.graph.log_step", side_effect=log_step_side_effect),
    ):
        final_state = support_graph.invoke(initial_state)

    assert final_state["error"] is True
    assert final_state["error_node"] == node_name
    assert "передан оператору" in final_state["answer"]
    escalate_to_inbox.assert_called_once()

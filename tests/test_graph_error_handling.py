import importlib
import sys
import types
from unittest.mock import Mock, patch

from state import create_initial_state


def _install_sqlite_trace_stub() -> None:
    if "sqlite_trace" in sys.modules:
        return

    sqlite_trace_module = types.ModuleType("sqlite_trace")
    sqlite_trace_module.start_trace = lambda: "trace-stub"
    sqlite_trace_module.log_step = lambda *args, **kwargs: None
    sqlite_trace_module.finish_trace = lambda *args, **kwargs: None
    sys.modules["sqlite_trace"] = sqlite_trace_module


_install_sqlite_trace_stub()

graph = importlib.import_module("graph")


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
            "graph.build_query_transform_prompt",
            side_effect=RuntimeError("Сбой трансформации запроса"),
        ),
        patch("graph._escalate_to_inbox") as escalate_to_inbox,
        patch("graph.log_step"),
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

from agent.state import create_initial_state


def test_create_initial_state_has_error_fields_with_safe_defaults() -> None:
    state = create_initial_state(
        question="Какой статус моего обращения?",
        trace_id="trace-state-1",
    )

    assert state["error"] is False
    assert "error" in state
    assert "error_message" in state
    assert "error_node" in state
    assert state["error_message"] == ""
    assert state["error_node"] == ""

from __future__ import annotations

import importlib
import sys
import warnings


def _reload_root_module(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_agent_package_modules_are_importable() -> None:
    graph_module = importlib.import_module("agent.graph")
    state_module = importlib.import_module("agent.state")
    prompts_module = importlib.import_module("agent.prompts")

    assert graph_module.create_initial_state.__module__ == "agent.state"
    assert state_module.create_initial_state.__module__ == "agent.state"
    assert callable(prompts_module.build_qa_prompt)


def test_root_modules_warn_and_reexport_agent_modules() -> None:
    importlib.import_module("agent.graph")
    importlib.import_module("agent.state")
    importlib.import_module("agent.prompts")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        graph_module = _reload_root_module("graph")
        state_module = _reload_root_module("state")
        prompts_module = _reload_root_module("prompts")

    assert any("agent.graph" in str(item.message) for item in caught)
    assert any("agent.state" in str(item.message) for item in caught)
    assert any("agent.prompts" in str(item.message) for item in caught)
    assert graph_module.create_initial_state.__module__ == "agent.state"
    assert state_module.create_initial_state.__module__ == "agent.state"
    assert prompts_module.build_qa_prompt.__module__ == "agent.prompts"

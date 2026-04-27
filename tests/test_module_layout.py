from __future__ import annotations

import importlib
import sys


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


def test_root_deprecation_shims_are_removed() -> None:
    importlib.import_module("agent.graph")
    importlib.import_module("agent.state")
    importlib.import_module("agent.prompts")

    for module_name in ("graph", "state", "prompts"):
        try:
            _reload_root_module(module_name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module_name} root shim should be removed")

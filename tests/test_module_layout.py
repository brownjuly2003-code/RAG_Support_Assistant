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


def test_vectordb_base_manager_is_canonical_home() -> None:
    base_manager = importlib.import_module("vectordb._base_manager")
    tenant_manager = importlib.import_module("vectordb.manager")
    root_manager = _reload_root_module("manager")

    assert tenant_manager._base_manager is base_manager
    assert root_manager.build_vector_store is base_manager.build_vector_store
    assert root_manager.build_vector_store.__module__ == "vectordb._base_manager"


def test_tracing_base_trace_is_canonical_home() -> None:
    base_trace = importlib.import_module("tracing._base_trace")
    pii_trace = importlib.import_module("tracing.sqlite_trace")
    root_trace = _reload_root_module("sqlite_trace")

    assert pii_trace._sqlite_trace is base_trace
    assert root_trace.start_trace is base_trace.start_trace
    assert root_trace.start_trace.__module__ == "tracing._base_trace"


def test_chunking_eval_script_is_canonical_home() -> None:
    chunking_eval = importlib.import_module("scripts.chunking_eval")

    try:
        _reload_root_module("chunking")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("chunking root script should be moved to scripts.chunking_eval")

    assert chunking_eval.ChunkingEvaluator.__module__ == "scripts.chunking_eval"


def test_ingestion_loader_is_canonical_home() -> None:
    ingestion_loader = importlib.import_module("ingestion.loader")
    root_loader = _reload_root_module("loader")

    assert root_loader.DocumentLoader is ingestion_loader.DocumentLoader
    assert root_loader.DocumentChangeTracker is ingestion_loader.DocumentChangeTracker
    assert root_loader.DocumentChangeTracker.__module__ == "ingestion.loader"

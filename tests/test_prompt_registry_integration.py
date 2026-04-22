from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from evaluation.experiment_schema import Experiment, save_experiment


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        quality_threshold=80,
        online_evaluators_enabled=False,
    )


def _write_stage_files(
    tmp_path: Path,
    experiment_id: str,
    prompt_overrides: dict[str, str],
) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    experiments_dir = tmp_path / "evaluation" / "experiments"
    config_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    experiment = Experiment(
        id=experiment_id,
        name="stage test",
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        created_by="tests",
        description="stage override",
        prompt_overrides=prompt_overrides,
        settings_overrides={},
        parent_experiment_id=None,
        status="draft",
        tags=[],
    )
    experiment_path = experiments_dir / f"{experiment_id}.yaml"
    save_experiment(experiment, experiment_path)

    override_path = config_dir / "experiment_override.yaml"
    override_path.write_text(
        yaml.safe_dump(
            {
                "experiment_id": experiment_id,
                "prompt_overrides": prompt_overrides,
                "settings_overrides": {},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return experiment_path, override_path


def test_graph_uses_default_prompt_without_experiment_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = importlib.import_module("agent.graph")
    prompts = importlib.import_module("agent.prompts")
    registry = importlib.import_module("agent.prompt_registry")

    class _FakeGraph:
        def invoke(self, state):
            return {
                **state,
                "answer": prompts.build_qa_prompt(state["question"], []),
                "route": "auto",
                "quality_score": 91,
            }

    monkeypatch.delenv("EXPERIMENT_ID", raising=False)
    monkeypatch.setattr(graph, "get_settings", lambda: _settings(), raising=False)
    monkeypatch.setattr(graph, "start_trace", lambda trace_id=None, tenant_id="default": "trace-default")
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _FakeGraph())
    monkeypatch.setattr(registry, "EXPERIMENT_OVERRIDE_PATH", Path("__missing_override__.yaml"))
    monkeypatch.setitem(prompts.PROMPT_REGISTRY["qa"], "text", "DEFAULT PROMPT {question}")

    result = graph.run_qa_pipeline(question="hello", retriever=object(), llm=object())

    assert result["answer"] == "DEFAULT PROMPT hello"


def test_graph_uses_staged_override_when_experiment_id_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    graph = importlib.import_module("agent.graph")
    prompts = importlib.import_module("agent.prompts")
    registry = importlib.import_module("agent.prompt_registry")

    class _FakeGraph:
        def invoke(self, state):
            return {
                **state,
                "answer": prompts.build_qa_prompt(state["question"], []),
                "route": "auto",
                "quality_score": 91,
            }

    experiment_id = "2026-04-22-stage-override"
    _, override_path = _write_stage_files(
        tmp_path,
        experiment_id=experiment_id,
        prompt_overrides={"qa": "OVERRIDE {question}"},
    )

    monkeypatch.setenv("EXPERIMENT_ID", experiment_id)
    monkeypatch.setattr(graph, "get_settings", lambda: _settings(), raising=False)
    monkeypatch.setattr(graph, "start_trace", lambda trace_id=None, tenant_id="default": "trace-stage")
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _FakeGraph())
    monkeypatch.setattr(registry, "EXPERIMENT_OVERRIDE_PATH", override_path)
    monkeypatch.setattr(registry, "_load_staged_prompt_overrides", lambda: {})
    monkeypatch.setitem(prompts.PROMPT_REGISTRY["qa"], "text", "DEFAULT PROMPT {question}")

    result = graph.run_qa_pipeline(question="hello", retriever=object(), llm=object())

    assert result["answer"] == "OVERRIDE hello"


def test_experiment_context_isolated_per_task() -> None:
    prompts = importlib.import_module("agent.prompts")
    registry = importlib.import_module("agent.prompt_registry")

    experiment_one = Experiment(
        id="2026-04-22-exp-one",
        name="one",
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        created_by="tests",
        description="one",
        prompt_overrides={"qa": "ONE {question}"},
        settings_overrides={},
        parent_experiment_id=None,
        status="draft",
        tags=[],
    )
    experiment_two = Experiment(
        id="2026-04-22-exp-two",
        name="two",
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        created_by="tests",
        description="two",
        prompt_overrides={"qa": "TWO {question}"},
        settings_overrides={},
        parent_experiment_id=None,
        status="draft",
        tags=[],
    )

    async def _render(exp: Experiment, question: str) -> str:
        token = registry.set_current_experiment(exp)
        try:
            await asyncio.sleep(0)
            return prompts.build_qa_prompt(question, [])
        finally:
            registry.CURRENT_EXPERIMENT.reset(token)

    async def _main() -> tuple[str, str]:
        return await asyncio.gather(
            _render(experiment_one, "alpha"),
            _render(experiment_two, "beta"),
        )

    rendered_one, rendered_two = asyncio.run(_main())

    assert rendered_one == "ONE alpha"
    assert rendered_two == "TWO beta"


def test_graph_uses_assigned_experiment_when_resolver_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = importlib.import_module("agent.graph")
    prompts = importlib.import_module("agent.prompts")
    registry = importlib.import_module("agent.prompt_registry")

    class _FakeGraph:
        def invoke(self, state):
            return {
                **state,
                "answer": prompts.build_qa_prompt(state["question"], []),
                "route": "auto",
                "quality_score": 91,
            }

    experiment = Experiment(
        id="2026-04-22-assigned-exp",
        name="assigned",
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        created_by="tests",
        description="assigned override",
        prompt_overrides={"qa": "ASSIGNED {question}"},
        settings_overrides={},
        parent_experiment_id=None,
        status="running",
        tags=[],
    )

    monkeypatch.delenv("EXPERIMENT_ID", raising=False)
    monkeypatch.setattr(graph, "get_settings", lambda: _settings(), raising=False)
    monkeypatch.setattr(
        graph,
        "start_trace",
        lambda trace_id=None, tenant_id="default", experiment_id=None: "trace-assigned",
    )
    monkeypatch.setattr(graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph, "build_support_graph", lambda **kwargs: _FakeGraph())
    monkeypatch.setattr(
        registry,
        "resolve_active_experiment",
        lambda tenant_id="default", user_id="anonymous", session_id=None: experiment,
        raising=False,
    )
    monkeypatch.setitem(prompts.PROMPT_REGISTRY["qa"], "text", "DEFAULT PROMPT {question}")

    result = graph.run_qa_pipeline(
        question="hello",
        retriever=object(),
        llm=object(),
        tenant_id="acme",
        user_id="user-42",
        session_id="session-42",
    )

    assert result["answer"] == "ASSIGNED hello"

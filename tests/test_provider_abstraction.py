from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.experiment_schema import Experiment


def _settings(profile: str = "latency-first") -> SimpleNamespace:
    return SimpleNamespace(
        provider_registry_path=Path(__file__).resolve().parent.parent / "config" / "providers.yml",
        llm_provider_profile=profile,
        ollama_base_url="http://ollama.test",
        ollama_request_timeout_sec=30.0,
        daily_cost_limit_usd=5.0,
    )


def test_build_provider_runtime_resolves_latency_first_profile() -> None:
    from llm.providers import build_provider_runtime

    runtime = build_provider_runtime(settings=_settings("latency-first"))

    assert runtime.profile_name == "latency-first"
    assert runtime.fast.provider_id == "ollama"
    assert runtime.strong.provider_id == "ollama"
    assert runtime.fast.model_name == "qwen2.5:7b"


def test_provider_backed_llm_invoke_tracks_last_response() -> None:
    from llm.providers import LLMProvider, LLMResponse, ProviderBackedLLM

    class _FakeProvider(LLMProvider):
        provider_id = "fake"
        model_name = "fake-model"

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            return LLMResponse(
                text="ready",
                provider="fake",
                model="fake-model",
                input_tokens=12,
                output_tokens=4,
                cost_usd=0.123,
            )

    llm = ProviderBackedLLM(_FakeProvider())

    assert llm.invoke("hello") == "ready"
    assert llm.last_response is not None
    assert llm.last_response.provider == "fake"
    assert llm.last_response.model == "fake-model"
    assert llm.last_response.cost_usd == 0.123


def test_build_provider_runtime_prefers_experiment_profile_override() -> None:
    from agent.prompt_registry import reset_current_experiment, set_current_experiment
    from llm.providers import build_provider_runtime

    experiment = Experiment(
        id="2026-04-22-quality-profile",
        name="quality profile",
        created_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        created_by="tests",
        description="override provider profile",
        prompt_overrides={},
        settings_overrides={"llm_provider_profile": "quality-first"},
        parent_experiment_id=None,
        status="draft",
        tags=[],
    )

    token = set_current_experiment(experiment)
    try:
        runtime = build_provider_runtime(settings=_settings("latency-first"))
    finally:
        reset_current_experiment(token)

    assert runtime.profile_name == "quality-first"
    assert runtime.strong.provider_id == "claude"


def test_build_provider_runtime_rejects_paid_profile_when_daily_cost_limit_exceeded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from llm.providers import build_provider_runtime

    db_path = tmp_path / "traces.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT,
                cost_usd REAL,
                ts TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO trace_steps (provider_name, cost_usd, ts)
            VALUES (?, ?, ?)
            """,
            ("claude", 0.75, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    monkeypatch.setenv("OPENAI_API_KEY", "changeme")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "changeme")

    settings = SimpleNamespace(
        provider_registry_path=Path(__file__).resolve().parent.parent / "config" / "providers.yml",
        llm_provider_profile="quality-first",
        ollama_base_url="http://ollama.test",
        ollama_request_timeout_sec=30.0,
        daily_cost_limit_usd=0.5,
        tracing_db_path=db_path,
    )

    with pytest.raises(RuntimeError, match="DAILY_COST_LIMIT_USD"):
        build_provider_runtime(settings)

"""F-4 guards: provider-runtime cache, compiled-graph cache, and the four traps.

Spec: codex-tasks/task-F4-cache-runtime-graph.md. The money-critical invariant
is that _enforce_daily_cost_limit runs on EVERY build_provider_runtime call,
cache hit or not; the concurrency-critical invariant is that a shared
ProviderBackedLLM never leaks one thread's last_response into another.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import agent.graph as agent_graph
import llm.providers.runtime as runtime_module
from llm.providers.base import LLMResponse, ProviderBackedLLM


def _write_registry(path: Path, *, paid: bool = False) -> None:
    providers = [
        {
            "id": "ollama",
            "label": "Ollama",
            "kind": "local",
            "enabled": True,
            "api_key_env": None,
            "default_models": {"fast": "qwen2.5:7b", "strong": "qwen2.5:7b"},
            "capabilities": {
                "supports_tool_use": False,
                "supports_structured_output": False,
                "supports_vision": False,
            },
            "rate_limits": {"requests_per_minute": 0, "tokens_per_minute": 0},
            "models": [
                {
                    "name": "qwen2.5:7b",
                    "aliases": ["ollama-small"],
                    "input_price_per_1m_tokens": 0.0,
                    "output_price_per_1m_tokens": 0.0,
                }
            ],
        }
    ]
    profiles = {
        "local-first": {
            "description": "Ollama only",
            "fast": {"provider": "ollama", "model": "qwen2.5:7b"},
            "strong": {"provider": "ollama", "model": "qwen2.5:7b"},
        }
    }
    if paid:
        providers.append(
            {
                "id": "mistral",
                "label": "Mistral",
                "kind": "paid",
                "enabled": True,
                "api_key_env": "MISTRAL_API_KEY",
                "default_models": {
                    "fast": "ministral-3b-latest",
                    "strong": "mistral-small-latest",
                },
                "capabilities": {
                    "supports_tool_use": False,
                    "supports_structured_output": False,
                    "supports_vision": False,
                },
                "rate_limits": {"requests_per_minute": 0, "tokens_per_minute": 0},
                "models": [
                    {
                        "name": "ministral-3b-latest",
                        "aliases": [],
                        "input_price_per_1m_tokens": 0.04,
                        "output_price_per_1m_tokens": 0.04,
                    },
                    {
                        "name": "mistral-small-latest",
                        "aliases": [],
                        "input_price_per_1m_tokens": 0.1,
                        "output_price_per_1m_tokens": 0.3,
                    },
                ],
            }
        )
        profiles["paid-first"] = {
            "description": "Mistral only",
            "fast": {"provider": "mistral", "model": "ministral-3b-latest"},
            "strong": {"provider": "mistral", "model": "mistral-small-latest"},
        }
    path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "local-first",
                "providers": providers,
                "routing_profiles": profiles,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _runtime_settings(path: Path, profile: str = "local-first", **overrides) -> SimpleNamespace:
    values = {
        "provider_registry_path": path,
        "llm_provider_profile": profile,
        "ollama_base_url": "http://ollama.test",
        "ollama_request_timeout_sec": 5.0,
        "failover_chain_enabled": False,
        "daily_cost_limit_usd": 0.0,
        "tracing_db_path": path.parent / "missing-traces.db",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _EchoProvider:
    provider_id = "fake"
    model_name = "fake-model"

    def __init__(self, delay_sec: float = 0.0) -> None:
        self._delay_sec = delay_sec

    def generate(self, messages, tools=None, **kwargs):
        _ = tools, kwargs
        text = str(messages[-1]["content"])
        if self._delay_sec:
            time.sleep(self._delay_sec)
        return LLMResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_name,
            input_tokens=1,
            output_tokens=1,
        )


def test_last_response_is_thread_isolated() -> None:
    llm = ProviderBackedLLM(_EchoProvider(delay_sec=0.05))
    barrier = threading.Barrier(2)
    seen: dict[str, str] = {}
    errors: list[BaseException] = []

    def _worker(marker: str) -> None:
        try:
            barrier.wait(timeout=5)
            llm.generate([{"role": "user", "content": marker}])
            time.sleep(0.1)  # give the other thread time to overwrite, if it could
            seen[marker] = llm.last_response.text
        except BaseException as exc:  # pragma: no cover - thread handoff
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(f"marker-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert seen == {"marker-0": "marker-0", "marker-1": "marker-1"}


def test_last_response_visible_within_one_thread() -> None:
    llm = ProviderBackedLLM(_EchoProvider())

    response = llm.generate([{"role": "user", "content": "hello"}])

    assert llm.last_response is response


def test_runtime_cache_reuses_providers_until_mtime_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path)
    settings = _runtime_settings(registry_path)

    calls: list[str] = []
    original_build = runtime_module._build_provider

    def _counting_build(settings_arg, profile_name, provider_id, model_name, fallback=None):
        calls.append(provider_id)
        return original_build(settings_arg, profile_name, provider_id, model_name, fallback)

    monkeypatch.setattr(runtime_module, "_build_provider", _counting_build)

    first = runtime_module.build_provider_runtime(settings)
    second = runtime_module.build_provider_runtime(settings)

    assert second is first
    assert len(calls) == 2  # fast + strong, built exactly once

    # mtime bump invalidates: the registry file was "edited".
    stat = registry_path.stat()
    os.utime(registry_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    third = runtime_module.build_provider_runtime(settings)

    assert third is not first
    assert len(calls) == 4


def test_daily_cost_limit_enforced_on_every_call_including_cache_hits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path, paid=True)
    settings = _runtime_settings(registry_path, profile="paid-first", daily_cost_limit_usd=5.0)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")

    spent = {"value": 0.0}
    monkeypatch.setattr(
        runtime_module, "_daily_paid_cost_usd", lambda settings_arg, ids: spent["value"]
    )

    calls: list[str] = []
    original_build = runtime_module._build_provider

    def _counting_build(settings_arg, profile_name, provider_id, model_name, fallback=None):
        calls.append(provider_id)
        return original_build(settings_arg, profile_name, provider_id, model_name, fallback)

    monkeypatch.setattr(runtime_module, "_build_provider", _counting_build)

    runtime = runtime_module.build_provider_runtime(settings)
    assert runtime.profile_name == "paid-first"
    assert len(calls) == 2

    spent["value"] = 99.0
    with pytest.raises(RuntimeError, match="DAILY_COST_LIMIT_USD"):
        runtime_module.build_provider_runtime(settings)
    # The cap must fire again on the next call too — not just once.
    with pytest.raises(RuntimeError, match="DAILY_COST_LIMIT_USD"):
        runtime_module.build_provider_runtime(settings)
    # Both rejected calls were cache hits: no provider was re-instantiated.
    assert len(calls) == 2

    spent["value"] = 0.0
    again = runtime_module.build_provider_runtime(settings)
    assert again is runtime
    assert len(calls) == 2


def _stable_runtime() -> SimpleNamespace:
    fast = SimpleNamespace(
        invoke=lambda prompt: "85", provider_id="fake", model_name="fake-fast"
    )
    strong = SimpleNamespace(
        invoke=lambda prompt: "85", provider_id="fake", model_name="fake-strong"
    )
    return SimpleNamespace(profile_name="local-first", fast=fast, strong=strong)


def test_compiled_graph_cache_identity_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _stable_runtime()
    monkeypatch.setattr(agent_graph, "build_provider_runtime", lambda settings: runtime)
    monkeypatch.setattr(
        "config.settings.get_settings", lambda: SimpleNamespace(quality_threshold=80)
    )

    retriever = object()
    first = agent_graph.build_support_graph(retriever=retriever)
    second = agent_graph.build_support_graph(retriever=retriever)
    assert second is first

    other_quality = agent_graph.build_support_graph(retriever=retriever, min_quality=55)
    assert other_quality is not first

    other_retriever = agent_graph.build_support_graph(retriever=object())
    assert other_retriever is not first

    # An explicitly passed llm has no stable identity guarantee — never cached.
    explicit_llm = SimpleNamespace(invoke=lambda prompt: "85")
    third = agent_graph.build_support_graph(retriever=retriever, llm=explicit_llm)
    fourth = agent_graph.build_support_graph(retriever=retriever, llm=explicit_llm)
    assert third is not fourth


def test_concurrent_run_qa_pipeline_shares_cached_graph_without_state_bleed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _invoke(prompt: str) -> str:
        text = str(prompt)
        marker_match = re.search(r"QMARK-\d+", text)
        marker = marker_match.group(0) if marker_match else "QMARK-NONE"
        if "ANSWER::" in text:
            return "95"  # evaluate
        if "KBDOC" in text:
            time.sleep(0.05)  # generate; encourage thread interleaving
            return f"ANSWER::{marker}"
        return "SIMPLE"  # classify / transform

    shared_llm = SimpleNamespace(
        invoke=_invoke, provider_id="fake", model_name="fake-model"
    )
    runtime = SimpleNamespace(profile_name="local-first", fast=shared_llm, strong=shared_llm)

    class _Retriever:
        def get_relevant_documents(self, query: str):
            _ = query
            return [
                SimpleNamespace(
                    page_content="KBDOC shared knowledge", metadata={"source": "kb.md"}
                )
            ]

    settings = SimpleNamespace(
        quality_threshold=80,
        model_routing_enabled=True,
        fact_verification_enabled=False,
        suggested_questions_enabled=False,
        online_evaluators_enabled=False,
        retrieval_strategy="hybrid",
        hyde=False,
        parent_child=False,
        agentic_mode=False,
    )

    compile_count = {"value": 0}
    original_state_graph = agent_graph.StateGraph

    def _counting_state_graph(*args, **kwargs):
        compile_count["value"] += 1
        return original_state_graph(*args, **kwargs)

    monkeypatch.setattr(agent_graph, "StateGraph", _counting_state_graph)
    monkeypatch.setattr(agent_graph, "build_provider_runtime", lambda s: runtime)
    monkeypatch.setattr("config.settings.get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_graph,
        "start_trace",
        lambda trace_id=None, tenant_id="default": trace_id or "trace-f4",
    )
    monkeypatch.setattr(agent_graph, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(agent_graph, "log_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_graph, "trace_llm_call", lambda **kwargs: None)

    retriever = _Retriever()
    # Warm the cache once; the threaded calls below must reuse this graph.
    agent_graph.build_support_graph(retriever=retriever, min_quality=80, max_iterations=2)
    assert compile_count["value"] == 1

    results: dict[int, str] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            state = agent_graph.run_qa_pipeline(
                question=f"QMARK-{index} how?",
                retriever=retriever,
            )
            results[index] = str(state.get("answer"))
        except BaseException as exc:  # pragma: no cover - thread handoff
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == {0: "ANSWER::QMARK-0", 1: "ANSWER::QMARK-1"}
    # No recompilation happened: both threads ran the warmed cached graph.
    assert compile_count["value"] == 1

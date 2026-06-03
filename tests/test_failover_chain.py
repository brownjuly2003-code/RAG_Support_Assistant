from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


def _write_registry(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "gracekelly-primary",
                "providers": [
                    {
                        "id": "ollama",
                        "label": "Ollama",
                        "kind": "local",
                        "enabled": True,
                        "api_key_env": None,
                        "default_models": {
                            "fast": "qwen2.5:7b",
                            "strong": "qwen2.5:7b",
                        },
                        "capabilities": {
                            "supports_tool_use": False,
                            "supports_structured_output": False,
                            "supports_vision": False,
                        },
                        "rate_limits": {
                            "requests_per_minute": 0,
                            "tokens_per_minute": 0,
                        },
                        "models": [
                            {
                                "name": "qwen2.5:7b",
                                "aliases": ["ollama-small"],
                                "input_price_per_1m_tokens": 0.0,
                                "output_price_per_1m_tokens": 0.0,
                            }
                        ],
                    },
                    {
                        "id": "gracekelly",
                        "label": "GraceKelly",
                        "kind": "local",
                        "enabled": True,
                        "api_key_env": "GRACEKELLY_API_KEY",
                        "default_models": {
                            "fast": "mistral-small",
                            "strong": "claude-sonnet-4-6-api",
                        },
                        "capabilities": {
                            "supports_tool_use": False,
                            "supports_structured_output": False,
                            "supports_vision": False,
                        },
                        "rate_limits": {
                            "requests_per_minute": 0,
                            "tokens_per_minute": 0,
                        },
                        "models": [
                            {
                                "name": "mistral-small",
                                "aliases": ["gk-fast"],
                                "input_price_per_1m_tokens": 0.0,
                                "output_price_per_1m_tokens": 0.0,
                            },
                            {
                                "name": "claude-sonnet-4-6-api",
                                "aliases": ["gk-strong"],
                                "input_price_per_1m_tokens": 0.0,
                                "output_price_per_1m_tokens": 0.0,
                            },
                        ],
                    },
                ],
                "routing_profiles": {
                    "gracekelly-primary": {
                        "description": "GraceKelly with local fallback",
                        "fast": {"provider": "gracekelly", "model": "gk-fast"},
                        "strong": {"provider": "gracekelly", "model": "gk-strong"},
                        "fallback": {"provider": "ollama", "model": "ollama-small"},
                    }
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _settings(path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        provider_registry_path=path,
        llm_provider_profile="gracekelly-primary",
        ollama_base_url="http://ollama.test",
        ollama_request_timeout_sec=30.0,
        gracekelly_base_url="http://127.0.0.1:8011",
        gracekelly_request_timeout_sec=30.0,
        gracekelly_health_check_timeout_sec=2.0,
        failover_chain_enabled=True,
        failover_fallback_cache_seconds=300,
        daily_cost_limit_usd=5.0,
    )


def test_failover_uses_ollama_when_gracekelly_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import llm.providers.runtime as runtime_module
    from llm.providers.base import LLMResponse, ProviderUnavailable
    from llm.providers.runtime import build_provider_runtime

    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path)
    primary_calls = {"count": 0}
    fallback_calls = {"count": 0}

    class _GraceKellyProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "gracekelly"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            primary_calls["count"] += 1
            raise ProviderUnavailable("gracekelly down", provider_id="gracekelly", reason="health_check")

    class _OllamaProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "ollama"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            fallback_calls["count"] += 1
            return LLMResponse(text="fallback", provider="ollama", model=self.model_name)

    monkeypatch.setattr(runtime_module, "GraceKellyProvider", _GraceKellyProvider)
    monkeypatch.setattr(runtime_module, "OllamaProvider", _OllamaProvider)

    runtime = build_provider_runtime(_settings(registry_path))
    response = runtime.fast.generate([{"role": "user", "content": "hello"}])

    assert runtime.fast.model_name == "mistral-small"
    assert response.provider == "ollama"
    assert primary_calls["count"] == 1
    assert fallback_calls["count"] == 1


def test_failover_cache_skips_primary_checks_for_five_minutes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import llm.providers.runtime as runtime_module
    from llm.providers.base import LLMResponse, ProviderUnavailable
    from llm.providers.runtime import build_provider_runtime

    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path)
    primary_calls = {"count": 0}
    fallback_calls = {"count": 0}

    class _GraceKellyProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "gracekelly"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            primary_calls["count"] += 1
            raise ProviderUnavailable("gracekelly down", provider_id="gracekelly", reason="health_check")

    class _OllamaProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "ollama"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            fallback_calls["count"] += 1
            return LLMResponse(text="fallback", provider="ollama", model=self.model_name)

    monkeypatch.setattr(runtime_module, "GraceKellyProvider", _GraceKellyProvider)
    monkeypatch.setattr(runtime_module, "OllamaProvider", _OllamaProvider)

    runtime = build_provider_runtime(_settings(registry_path))
    runtime.fast.generate([{"role": "user", "content": "hello"}])
    runtime = build_provider_runtime(_settings(registry_path))
    runtime.fast.generate([{"role": "user", "content": "hello again"}])

    assert primary_calls["count"] == 1
    assert fallback_calls["count"] == 2


def test_failover_increments_prometheus_metric(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import llm.providers.runtime as runtime_module
    from llm.providers.base import LLMResponse, ProviderUnavailable
    from llm.providers.runtime import build_provider_runtime
    from monitoring import prometheus as metrics

    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path)

    class _GraceKellyProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "gracekelly"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            raise ProviderUnavailable("gracekelly down", provider_id="gracekelly", reason="health_check")

    class _OllamaProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "ollama"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            return LLMResponse(text="fallback", provider="ollama", model=self.model_name)

    def _metric_value() -> float:
        for family in metrics.LLM_PROVIDER_FALLBACK_TOTAL.collect():
            for sample in family.samples:
                if sample.labels == {
                    "from_provider": "gracekelly",
                    "to_provider": "ollama",
                    "reason": "health_check",
                }:
                    return float(sample.value)
        return 0.0

    monkeypatch.setattr(runtime_module, "GraceKellyProvider", _GraceKellyProvider)
    monkeypatch.setattr(runtime_module, "OllamaProvider", _OllamaProvider)

    before = _metric_value()
    runtime = build_provider_runtime(_settings(registry_path))
    runtime.fast.generate([{"role": "user", "content": "hello"}])

    assert _metric_value() == before + 1.0


def test_failover_depth_is_limited_to_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import llm.providers.runtime as runtime_module
    from llm.providers.base import ProviderUnavailable
    from llm.providers.runtime import build_provider_runtime

    registry_path = tmp_path / "providers.yml"
    _write_registry(registry_path)
    primary_calls = {"count": 0}
    fallback_calls = {"count": 0}

    class _GraceKellyProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "gracekelly"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            primary_calls["count"] += 1
            raise ProviderUnavailable("gracekelly down", provider_id="gracekelly", reason="health_check")

    class _OllamaProvider:
        def __init__(self, **kwargs) -> None:
            self.provider_id = "ollama"
            self.model_name = kwargs["model_name"]

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            fallback_calls["count"] += 1
            raise ProviderUnavailable("ollama down", provider_id="ollama", reason="request_failed")

    monkeypatch.setattr(runtime_module, "GraceKellyProvider", _GraceKellyProvider)
    monkeypatch.setattr(runtime_module, "OllamaProvider", _OllamaProvider)

    runtime = build_provider_runtime(_settings(registry_path))

    with pytest.raises(ProviderUnavailable, match="ollama down"):
        runtime.fast.generate([{"role": "user", "content": "hello"}])

    assert primary_calls["count"] == 1
    assert fallback_calls["count"] == 1

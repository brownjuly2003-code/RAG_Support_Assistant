from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError


def test_load_provider_registry_from_yaml() -> None:
    from config.provider_schema import load_provider_registry

    registry = load_provider_registry(
        Path(__file__).resolve().parent.parent / "config" / "providers.yml"
    )

    assert registry.default_profile == "gracekelly-primary"
    assert set(registry.provider_ids()) == {"gracekelly", "mistral", "ollama"}
    assert registry.get_profile("gracekelly-primary").strong.provider == "gracekelly"
    assert registry.get_provider("ollama").default_models.fast == "qwen2.5:7b"
    assert registry.get_provider("mistral").default_models.fast == "ministral-3b-latest"


def test_provider_registry_resolves_model_alias_and_pricing() -> None:
    from config.provider_schema import load_provider_registry

    registry = load_provider_registry(
        Path(__file__).resolve().parent.parent / "config" / "providers.yml"
    )

    resolved = registry.resolve_model("gk-fast")

    assert resolved.provider == "gracekelly"
    assert resolved.model == "mistral-small"
    assert resolved.input_price_per_1m_tokens == 0.0
    assert resolved.output_price_per_1m_tokens == 0.0


def test_provider_registry_exposes_streaming_and_batch_capabilities() -> None:
    from config.provider_schema import load_provider_registry

    registry = load_provider_registry(
        Path(__file__).resolve().parent.parent / "config" / "providers.yml"
    )

    gracekelly = registry.get_provider("gracekelly")
    ollama = registry.get_provider("ollama")

    assert gracekelly is not None
    assert gracekelly.capabilities.supports_streaming is True
    assert gracekelly.capabilities.supports_batch is True
    assert ollama is not None
    assert ollama.capabilities.supports_streaming is True


def test_provider_registry_rejects_unknown_default_model(tmp_path: Path) -> None:
    from config.provider_schema import load_provider_registry

    config_path = tmp_path / "providers.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "default_profile": "local-first",
                "providers": [
                    {
                        "id": "ollama",
                        "label": "Ollama",
                        "kind": "local",
                        "enabled": True,
                        "api_key_env": None,
                        "default_models": {
                            "fast": "missing-model",
                            "strong": "missing-model",
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
                    }
                ],
                "routing_profiles": {
                    "local-first": {
                        "description": "Local profile",
                        "fast": {"provider": "ollama", "model": "qwen2.5:7b"},
                        "strong": {"provider": "ollama", "model": "qwen2.5:7b"},
                    }
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValidationError):
        load_provider_registry(config_path, reload=True)

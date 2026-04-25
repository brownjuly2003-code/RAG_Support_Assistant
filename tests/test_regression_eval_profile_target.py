from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent

import pytest
import yaml


@pytest.fixture
def tiny_registry_path(tmp_path: Path) -> Path:
    registry = tmp_path / "providers.yml"
    registry.write_text(
        dedent(
            """
            default_profile: local-first

            providers:
              - id: ollama
                label: Ollama
                kind: local
                enabled: true
                api_key_env: null
                default_models:
                  fast: qwen2.5:7b
                  strong: qwen2.5:7b
                capabilities:
                  supports_tool_use: true
                  supports_structured_output: true
                  supports_streaming: true
                  supports_batch: false
                  supports_vision: false
                rate_limits:
                  requests_per_minute: 0
                  tokens_per_minute: 0
                models:
                  - name: qwen2.5:7b
                    aliases: []
                    input_price_per_1m_tokens: 0.0
                    output_price_per_1m_tokens: 0.0

              - id: mistral
                label: Mistral
                kind: paid
                enabled: true
                api_key_env: MISTRAL_API_KEY
                default_models:
                  fast: ministral-3b-latest
                  strong: ministral-3b-latest
                capabilities:
                  supports_tool_use: true
                  supports_structured_output: true
                  supports_streaming: true
                  supports_batch: false
                  supports_vision: false
                rate_limits:
                  requests_per_minute: 60
                  tokens_per_minute: 500000
                models:
                  - name: ministral-3b-latest
                    aliases: [ministral-3b]
                    input_price_per_1m_tokens: 0.04
                    output_price_per_1m_tokens: 0.04

              - id: gracekelly
                label: GraceKelly
                kind: local
                enabled: true
                api_key_env: GRACEKELLY_API_KEY
                default_models:
                  fast: claude-sonnet-4-6
                  strong: claude-sonnet-4-6
                capabilities:
                  supports_tool_use: true
                  supports_structured_output: true
                  supports_streaming: true
                  supports_batch: true
                  supports_vision: false
                rate_limits:
                  requests_per_minute: 0
                  tokens_per_minute: 0
                models:
                  - name: claude-sonnet-4-6
                    aliases: []
                    input_price_per_1m_tokens: 0.0
                    output_price_per_1m_tokens: 0.0

            routing_profiles:
              local-first:
                description: Local-only routing.
                fast: { provider: ollama, model: qwen2.5:7b }
                strong: { provider: ollama, model: qwen2.5:7b }

              gracekelly-mixed:
                description: Mixed routing.
                fast: { provider: mistral, model: ministral-3b-latest }
                strong: { provider: gracekelly, model: claude-sonnet-4-6 }
            """
        ).strip(),
        encoding="utf-8",
    )
    return registry


def test_resolve_provider_target_returns_model_kind_for_known_model(tiny_registry_path: Path) -> None:
    from scripts.regression_eval import _resolve_provider_target

    resolution = _resolve_provider_target("ministral-3b-latest", tiny_registry_path)

    assert resolution is not None
    assert resolution["kind"] == "model"
    assert resolution["provider_id"] == "mistral"
    assert resolution["model_name"] == "ministral-3b-latest"
    assert "profile_name" not in resolution


def test_resolve_provider_target_returns_profile_kind_for_known_profile(
    tiny_registry_path: Path,
) -> None:
    from scripts.regression_eval import _resolve_provider_target

    resolution = _resolve_provider_target("gracekelly-mixed", tiny_registry_path)

    assert resolution is not None
    assert resolution["kind"] == "profile"
    assert resolution["profile_name"] == "gracekelly-mixed"
    assert resolution["provider_id"] == "gracekelly"
    assert resolution["model_name"] == "claude-sonnet-4-6"


def test_resolve_provider_target_returns_none_for_unknown_target(
    tiny_registry_path: Path,
) -> None:
    from scripts.regression_eval import _resolve_provider_target

    assert _resolve_provider_target("does-not-exist", tiny_registry_path) is None


def test_provider_target_runtime_does_not_inject_synthetic_profile_for_profile_target(
    tiny_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings as settings_module
    from scripts.regression_eval import _provider_target_runtime

    monkeypatch.setattr(
        settings_module.get_settings(),
        "provider_registry_path",
        tiny_registry_path,
        raising=False,
    )

    captured: dict[str, object] = {}

    @contextmanager
    def _capture_registry_state():
        with _provider_target_runtime("gracekelly-mixed", project_root=tiny_registry_path.parent) as resolution:
            override_path = settings_module.EXPERIMENT_OVERRIDE_PATH
            assert override_path is not None
            override_payload = yaml.safe_load(Path(override_path).read_text(encoding="utf-8"))
            registry_path = Path(override_payload["settings_overrides"]["provider_registry_path"])
            captured["registry_payload"] = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            captured["llm_provider_profile"] = override_payload["settings_overrides"]["llm_provider_profile"]
            captured["resolution"] = resolution
            yield

    with _capture_registry_state():
        pass

    routing_profile_keys = set(captured["registry_payload"]["routing_profiles"].keys())
    assert "gracekelly-mixed" in routing_profile_keys
    assert not any(key.startswith("benchmark-") for key in routing_profile_keys), routing_profile_keys
    assert captured["llm_provider_profile"] == "gracekelly-mixed"
    assert captured["resolution"]["kind"] == "profile"


def test_provider_target_runtime_injects_synthetic_profile_for_model_target(
    tiny_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings as settings_module
    from scripts.regression_eval import _provider_target_runtime

    monkeypatch.setattr(
        settings_module.get_settings(),
        "provider_registry_path",
        tiny_registry_path,
        raising=False,
    )

    captured: dict[str, object] = {}

    @contextmanager
    def _capture_registry_state():
        with _provider_target_runtime("ministral-3b-latest", project_root=tiny_registry_path.parent) as resolution:
            override_path = settings_module.EXPERIMENT_OVERRIDE_PATH
            assert override_path is not None
            override_payload = yaml.safe_load(Path(override_path).read_text(encoding="utf-8"))
            registry_path = Path(override_payload["settings_overrides"]["provider_registry_path"])
            captured["registry_payload"] = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            captured["llm_provider_profile"] = override_payload["settings_overrides"]["llm_provider_profile"]
            captured["resolution"] = resolution
            yield

    with _capture_registry_state():
        pass

    routing_profile_keys = set(captured["registry_payload"]["routing_profiles"].keys())
    benchmark_keys = [key for key in routing_profile_keys if key.startswith("benchmark-")]
    assert len(benchmark_keys) == 1, routing_profile_keys
    synthetic = captured["registry_payload"]["routing_profiles"][benchmark_keys[0]]
    assert synthetic["fast"]["model"] == "ministral-3b-latest"
    assert synthetic["strong"]["model"] == "ministral-3b-latest"
    assert captured["llm_provider_profile"] == benchmark_keys[0]
    assert captured["resolution"]["kind"] == "model"


def test_parse_args_accepts_baseline_profile_and_candidate_profile() -> None:
    from scripts.regression_eval import parse_args

    args = parse_args(
        [
            "--baseline",
            "ministral-3b-latest",
            "--candidate-profile",
            "gracekelly-mixed",
            "--max-cases",
            "2",
            "--allow-paid-apis",
        ]
    )
    assert args.baseline == "ministral-3b-latest"
    assert args.baseline_profile is None
    assert args.candidate is None
    assert args.candidate_profile == "gracekelly-mixed"


def test_parse_args_rejects_baseline_and_baseline_profile_together() -> None:
    from scripts.regression_eval import parse_args

    with pytest.raises(SystemExit):
        parse_args(
            [
                "--baseline",
                "ministral-3b-latest",
                "--baseline-profile",
                "gracekelly-mixed",
                "--candidate",
                "claude-sonnet-4-6",
            ]
        )

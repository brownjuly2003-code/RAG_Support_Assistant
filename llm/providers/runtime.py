from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.provider_schema import load_provider_registry
from llm.providers.anthropic import ClaudeProvider
from llm.providers.base import ProviderBackedLLM
from llm.providers.gemini import GeminiProvider
from llm.providers.ollama import OllamaProvider
from llm.providers.openai import OpenAIProvider

try:
    from agent.prompt_registry import CURRENT_EXPERIMENT
except ImportError:  # pragma: no cover
    CURRENT_EXPERIMENT = None  # type: ignore[assignment]


@dataclass
class ProviderRuntime:
    profile_name: str
    fast: ProviderBackedLLM
    strong: ProviderBackedLLM


def _active_profile_name(settings: Any) -> str:
    if CURRENT_EXPERIMENT is not None:
        experiment = CURRENT_EXPERIMENT.get()
        if experiment is not None:
            overrides = getattr(experiment, "settings_overrides", {}) or {}
            override_value = overrides.get("llm_provider_profile")
            if override_value:
                return str(override_value)
    return str(getattr(settings, "llm_provider_profile", "latency-first") or "latency-first")


def _build_provider(settings: Any, provider_id: str, model_name: str) -> ProviderBackedLLM:
    registry = load_provider_registry(getattr(settings, "provider_registry_path"))
    provider_config = registry.get_provider(provider_id)
    if provider_config is None:
        raise KeyError(f"unknown provider '{provider_id}'")
    model = provider_config.resolve_model(model_name)
    if model is None:
        raise KeyError(f"unknown model '{model_name}' for provider '{provider_id}'")

    timeout_sec = float(getattr(settings, "ollama_request_timeout_sec", 60.0))
    common_kwargs = {
        "model_name": model.name,
        "input_price_per_1m_tokens": model.input_price_per_1m_tokens,
        "output_price_per_1m_tokens": model.output_price_per_1m_tokens,
        "timeout_sec": timeout_sec,
    }
    if provider_id == "ollama":
        provider = OllamaProvider(
            base_url=str(getattr(settings, "ollama_base_url", "http://localhost:11434")),
            **common_kwargs,
        )
    elif provider_id == "claude":
        provider = ClaudeProvider(api_key_env=str(provider_config.api_key_env or ""), **common_kwargs)
    elif provider_id == "openai":
        provider = OpenAIProvider(api_key_env=str(provider_config.api_key_env or ""), **common_kwargs)
    elif provider_id == "gemini":
        provider = GeminiProvider(api_key_env=str(provider_config.api_key_env or ""), **common_kwargs)
    else:  # pragma: no cover
        raise KeyError(f"unsupported provider '{provider_id}'")
    return ProviderBackedLLM(provider)


def _daily_paid_cost_usd(settings: Any, provider_ids: set[str]) -> float:
    db_path = Path(getattr(settings, "tracing_db_path", ""))
    if not provider_ids or not db_path.exists():
        return 0.0

    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    placeholders = ",".join("?" for _ in provider_ids)
    query = (
        f"SELECT COALESCE(SUM(cost_usd), 0.0) FROM trace_steps "
        f"WHERE provider_name IN ({placeholders}) AND ts >= ?"
    )
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(query, (*sorted(provider_ids), cutoff)).fetchone()
    except sqlite3.Error:
        return 0.0
    return float((row[0] if row is not None else 0.0) or 0.0)


def _enforce_daily_cost_limit(settings: Any, registry: Any, profile_name: str) -> None:
    daily_cost_limit_usd = float(getattr(settings, "daily_cost_limit_usd", 0.0) or 0.0)
    if daily_cost_limit_usd <= 0:
        return

    profile = registry.get_profile(profile_name)
    paid_provider_ids: set[str] = set()
    for target in (profile.fast, profile.strong):
        provider = registry.get_provider(target.provider)
        if provider is not None and provider.kind == "paid":
            paid_provider_ids.add(provider.id)

    if not paid_provider_ids:
        return

    spent_today = _daily_paid_cost_usd(settings, paid_provider_ids)
    if spent_today >= daily_cost_limit_usd:
        provider_list = ", ".join(sorted(paid_provider_ids))
        raise RuntimeError(
            "DAILY_COST_LIMIT_USD exceeded for paid provider profile "
            f"'{profile_name}': spent {spent_today:.4f} USD today across {provider_list}, "
            f"limit is {daily_cost_limit_usd:.4f} USD"
        )


def build_provider_runtime(settings: Any) -> ProviderRuntime:
    registry = load_provider_registry(getattr(settings, "provider_registry_path"))
    profile_name = _active_profile_name(settings)
    _enforce_daily_cost_limit(settings, registry, profile_name)
    profile = registry.get_profile(profile_name)
    return ProviderRuntime(
        profile_name=profile_name,
        fast=_build_provider(settings, profile.fast.provider, profile.fast.model),
        strong=_build_provider(settings, profile.strong.provider, profile.strong.model),
    )

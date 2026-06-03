from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from config.provider_schema import load_provider_registry
from llm.providers.base import ProviderBackedLLM
from llm.providers.gracekelly import GraceKellyProvider
from llm.providers.mistral import MistralProvider
from llm.providers.ollama import OllamaProvider

try:
    from agent.prompt_registry import CURRENT_EXPERIMENT
except ImportError:  # pragma: no cover
    CURRENT_EXPERIMENT = None  # type: ignore[assignment]


_FAILOVER_CACHE_UNTIL: dict[tuple[str, str, str, str, str, str], float] = {}


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
    return str(getattr(settings, "llm_provider_profile", "local-first") or "local-first")


def _instantiate_provider(settings: Any, provider_id: str, model_name: str) -> Any:
    registry = load_provider_registry(settings.provider_registry_path)
    provider_config = registry.get_provider(provider_id)
    if provider_config is None:
        raise KeyError(f"unknown provider '{provider_id}'")
    model = provider_config.resolve_model(model_name)
    if model is None:
        raise KeyError(f"unknown model '{model_name}' for provider '{provider_id}'")

    timeout_sec = float(getattr(settings, "ollama_request_timeout_sec", 60.0))
    model_pricing_name: str = str(model.name)
    input_price: float = float(model.input_price_per_1m_tokens)
    output_price: float = float(model.output_price_per_1m_tokens)
    if provider_id == "ollama":
        ollama_provider = OllamaProvider(
            base_url=str(getattr(settings, "ollama_base_url", "http://localhost:11434")),
            model_name=model_pricing_name,
            input_price_per_1m_tokens=input_price,
            output_price_per_1m_tokens=output_price,
            timeout_sec=timeout_sec,
        )
        ollama_provider.supports_tool_use = provider_config.capabilities.supports_tool_use
        ollama_provider.supports_structured_output = provider_config.capabilities.supports_structured_output
        ollama_provider.supports_streaming = provider_config.capabilities.supports_streaming
        ollama_provider.supports_batch = provider_config.capabilities.supports_batch
        return ollama_provider
    if provider_id == "mistral":
        mistral_provider = MistralProvider(
            api_key_env=str(provider_config.api_key_env or ""),
            model_name=model_pricing_name,
            input_price_per_1m_tokens=input_price,
            output_price_per_1m_tokens=output_price,
            timeout_sec=timeout_sec,
        )
        mistral_provider.supports_tool_use = provider_config.capabilities.supports_tool_use
        mistral_provider.supports_structured_output = provider_config.capabilities.supports_structured_output
        mistral_provider.supports_streaming = provider_config.capabilities.supports_streaming
        mistral_provider.supports_batch = provider_config.capabilities.supports_batch
        return mistral_provider
    if provider_id == "gracekelly":
        gracekelly_provider = GraceKellyProvider(
            base_url=str(getattr(settings, "gracekelly_base_url", "http://127.0.0.1:8011")),
            api_key_env=str(getattr(settings, "gracekelly_api_key_env", provider_config.api_key_env or "")),
            health_check_timeout_sec=float(
                getattr(settings, "gracekelly_health_check_timeout_sec", 2.0)
            ),
            timeout_sec=float(getattr(settings, "gracekelly_request_timeout_sec", 30.0)),
            use_orchestrate_for_tools=bool(
                getattr(settings, "gracekelly_use_orchestrate_for_tools", True)
            ),
            model_name=model.name,
            input_price_per_1m_tokens=model.input_price_per_1m_tokens,
            output_price_per_1m_tokens=model.output_price_per_1m_tokens,
        )
        gracekelly_provider.supports_tool_use = provider_config.capabilities.supports_tool_use
        gracekelly_provider.supports_structured_output = provider_config.capabilities.supports_structured_output
        gracekelly_provider.supports_streaming = provider_config.capabilities.supports_streaming
        gracekelly_provider.supports_batch = provider_config.capabilities.supports_batch
        return gracekelly_provider
    raise KeyError(f"unsupported provider '{provider_id}'")


def _load_profile_fallback(
    settings: Any,
    profile_name: str,
) -> tuple[str, str] | None:
    if not bool(getattr(settings, "failover_chain_enabled", True)):
        return None
    registry_path = Path(settings.provider_registry_path)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    profile = ((payload.get("routing_profiles") or {}).get(profile_name)) or {}
    fallback = profile.get("fallback") if isinstance(profile, dict) else None
    if not isinstance(fallback, dict):
        return None
    provider = str(fallback.get("provider") or "").strip()
    model = str(fallback.get("model") or "").strip()
    if not provider or not model:
        return None
    return provider, model


def _failover_cache_key(
    settings: Any,
    profile_name: str,
    provider_id: str,
    model_name: str,
    fallback_provider_id: str,
    fallback_model_name: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        str(Path(settings.provider_registry_path).resolve()),
        profile_name,
        provider_id,
        model_name,
        fallback_provider_id,
        fallback_model_name,
    )


def _is_failover_cache_active(key: tuple[str, str, str, str, str, str]) -> bool:
    until = _FAILOVER_CACHE_UNTIL.get(key, 0.0)
    if until <= time.monotonic():
        _FAILOVER_CACHE_UNTIL.pop(key, None)
        return False
    return True


def _activate_failover_cache(key: tuple[str, str, str, str, str, str], ttl_sec: float) -> None:
    if ttl_sec <= 0:
        return
    _FAILOVER_CACHE_UNTIL[key] = time.monotonic() + ttl_sec


def _record_provider_fallback(from_provider: str, to_provider: str, reason: str) -> None:
    try:
        from monitoring.prometheus import record_provider_fallback

        record_provider_fallback(from_provider, to_provider, reason)
    except Exception:
        return None


def _build_provider(
    settings: Any,
    profile_name: str,
    provider_id: str,
    model_name: str,
    fallback_target: tuple[str, str] | None = None,
) -> ProviderBackedLLM:
    provider = _instantiate_provider(settings, provider_id, model_name)
    if provider_id != "gracekelly" or fallback_target is None:
        return ProviderBackedLLM(provider)

    fallback_provider_id, fallback_model_name = fallback_target
    registry = load_provider_registry(settings.provider_registry_path)
    fallback_provider_config = registry.get_provider(fallback_provider_id)
    if fallback_provider_config is None or fallback_provider_config.kind != "local":
        return ProviderBackedLLM(provider)

    fallback_provider = _instantiate_provider(settings, fallback_provider_id, fallback_model_name)
    cache_key = _failover_cache_key(
        settings,
        profile_name,
        provider.provider_id,
        provider.model_name,
        fallback_provider.provider_id,
        fallback_provider.model_name,
    )

    def fallback_cache_is_active() -> bool:
        return _is_failover_cache_active(cache_key)

    def fallback_cache_activate(ttl_sec: float) -> None:
        _activate_failover_cache(cache_key, ttl_sec)

    return ProviderBackedLLM(
        provider,
        fallback_provider=fallback_provider,
        fallback_cache_is_active=fallback_cache_is_active,
        fallback_cache_activate=fallback_cache_activate,
        fallback_cache_ttl_sec=float(getattr(settings, "failover_fallback_cache_seconds", 300) or 300),
        on_fallback=_record_provider_fallback,
    )


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
    registry = load_provider_registry(settings.provider_registry_path)
    profile_name = _active_profile_name(settings)
    _enforce_daily_cost_limit(settings, registry, profile_name)
    profile = registry.get_profile(profile_name)
    fallback_target = _load_profile_fallback(settings, profile_name)
    return ProviderRuntime(
        profile_name=profile_name,
        fast=_build_provider(settings, profile_name, profile.fast.provider, profile.fast.model, fallback_target),
        strong=_build_provider(settings, profile_name, profile.strong.provider, profile.strong.model, fallback_target),
    )

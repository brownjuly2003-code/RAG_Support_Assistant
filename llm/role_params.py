"""Per-LLM-role generation parameters (plan §3.1d).

Safe production defaults favour low temperature for grading/routing-critical
roles and modest max_tokens caps. Operators may override via
``RAG_LLM_ROLE_PARAMS`` JSON (merged on top of defaults).

Example::

    RAG_LLM_ROLE_PARAMS={"generate":{"temperature":0.1,"max_tokens":2048}}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Canonical role names used by graph / agentic paths.
LLM_ROLES: tuple[str, ...] = (
    "default",
    "generate",
    "grade",
    "transform",
    "evaluate",
    "verify",
    "classify",
    "suggest",
    "rewrite",
    "agentic",
)

# Safe production defaults (deterministic judges; capped free-form answers).
_DEFAULT_ROLE_PARAMS: dict[str, dict[str, float | int]] = {
    "default": {"temperature": 0.0, "max_tokens": 512},
    "generate": {"temperature": 0.2, "max_tokens": 1024},
    "grade": {"temperature": 0.0, "max_tokens": 256},
    "transform": {"temperature": 0.0, "max_tokens": 256},
    "evaluate": {"temperature": 0.0, "max_tokens": 128},
    "verify": {"temperature": 0.0, "max_tokens": 512},
    "classify": {"temperature": 0.0, "max_tokens": 32},
    "suggest": {"temperature": 0.3, "max_tokens": 256},
    "rewrite": {"temperature": 0.2, "max_tokens": 256},
    "agentic": {"temperature": 0.2, "max_tokens": 1024},
}

_TEMP_MIN = 0.0
_TEMP_MAX = 2.0
_MAX_TOKENS_MIN = 1
_MAX_TOKENS_MAX = 128_000


def default_role_params() -> dict[str, dict[str, float | int]]:
    """Return a deep copy of built-in role defaults."""
    return {
        role: {"temperature": float(vals["temperature"]), "max_tokens": int(vals["max_tokens"])}
        for role, vals in _DEFAULT_ROLE_PARAMS.items()
    }


def _clamp_temperature(value: float) -> float:
    return max(_TEMP_MIN, min(_TEMP_MAX, float(value)))


def _clamp_max_tokens(value: int) -> int:
    return max(_MAX_TOKENS_MIN, min(_MAX_TOKENS_MAX, int(value)))


def _normalize_role(role: str | None) -> str:
    name = (role or "default").strip().lower() or "default"
    if name not in _DEFAULT_ROLE_PARAMS:
        return "default"
    return name


def _parse_override_map(raw: str | None) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Invalid RAG_LLM_ROLE_PARAMS JSON; ignoring overrides")
        return {}
    if not isinstance(payload, dict):
        logger.warning("RAG_LLM_ROLE_PARAMS must be a JSON object; ignoring")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        role = _normalize_role(str(key))
        if not isinstance(value, dict):
            continue
        entry: dict[str, Any] = {}
        if "temperature" in value and value["temperature"] is not None:
            try:
                entry["temperature"] = _clamp_temperature(float(value["temperature"]))
            except (TypeError, ValueError):
                pass
        if "max_tokens" in value and value["max_tokens"] is not None:
            try:
                entry["max_tokens"] = _clamp_max_tokens(int(value["max_tokens"]))
            except (TypeError, ValueError):
                pass
        if entry:
            out[role] = entry
    return out


def _settings_override_raw(settings: Any | None) -> str:
    if settings is None:
        try:
            from config.settings import get_settings

            settings = get_settings()
        except Exception:
            return ""
    return str(getattr(settings, "llm_role_params_json", "") or "")


def resolve_role_params(
    role: str | None = "default",
    *,
    settings: Any | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, float | int]:
    """Resolve ``temperature`` + ``max_tokens`` for one LLM role.

    Merge order: built-in defaults ← ``RAG_LLM_ROLE_PARAMS`` ← explicit overrides.
    """
    name = _normalize_role(role)
    base = default_role_params()[name]
    merged: dict[str, float | int] = {
        "temperature": float(base["temperature"]),
        "max_tokens": int(base["max_tokens"]),
    }
    env_map = _parse_override_map(_settings_override_raw(settings))
    if name in env_map:
        merged.update(env_map[name])  # type: ignore[arg-type]
    if overrides:
        if "temperature" in overrides and overrides["temperature"] is not None:
            try:
                merged["temperature"] = _clamp_temperature(float(overrides["temperature"]))
            except (TypeError, ValueError):
                pass
        if "max_tokens" in overrides and overrides["max_tokens"] is not None:
            try:
                merged["max_tokens"] = _clamp_max_tokens(int(overrides["max_tokens"]))
            except (TypeError, ValueError):
                pass
    return merged


def generation_kwargs_for_role(
    role: str | None = "default",
    *,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Kwargs suitable for ``ProviderBackedLLM.generate`` / ``invoke``."""
    params = resolve_role_params(role, settings=settings)
    return {
        "temperature": float(params["temperature"]),
        "max_tokens": int(params["max_tokens"]),
    }

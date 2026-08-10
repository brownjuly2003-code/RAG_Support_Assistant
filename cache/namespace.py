"""Versioned LLM response-cache namespace (§9.1c).

Builds a deterministic, non-secret Redis key for history-less ``/api/ask``
responses. The key binds tenant, durable index identity, effective prompt
content, configured provider/model routing, and a Unicode-safe normalized
query. Identity-resolution failure returns ``None`` so callers fail closed
(skip cache lookup/write) without blocking the ordinary pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

# Schema marker embedded in the Redis key after the tenant segment.
SCHEMA_VERSION = "v1"

_WHITESPACE_RE = re.compile(r"\s+", flags=re.UNICODE)


class CacheIdentityError(Exception):
    """Raised when a required cache identity cannot be resolved safely."""


def normalize_query(question: str) -> str:
    """Unicode-safe query normalization for cache hashing.

    Applies NFKC, casefold, boundary trim, and equivalent-whitespace collapse.
    """
    text = unicodedata.normalize("NFKC", question or "")
    text = text.casefold()
    text = text.strip()
    return _WHITESPACE_RE.sub(" ", text)


def resolve_prompt_identity(*, experiment: Any | None = None) -> str:
    """Hash effective prompt content (registry + staged/deployed/experiment)."""
    from agent.prompt_registry import get_prompt
    from agent.prompts import PROMPT_REGISTRY

    hasher = hashlib.sha256()
    for name in sorted(PROMPT_REGISTRY):
        text = get_prompt(name, experiment=experiment)
        entry = PROMPT_REGISTRY[name]
        prompt_id = str(entry.get("prompt_id") or name)
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(prompt_id.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(text.encode("utf-8"))
        hasher.update(b"\0")
    return f"p:{hasher.hexdigest()[:24]}"


def resolve_model_identity(
    *,
    settings: Any | None = None,
    experiment: Any | None = None,
) -> str:
    """Resolve configured provider/model route identity without instantiation."""
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()

    profile_name = str(getattr(settings, "llm_provider_profile", "local-first") or "local-first")
    if experiment is not None:
        overrides = getattr(experiment, "settings_overrides", None) or {}
        if isinstance(overrides, dict):
            override_profile = overrides.get("llm_provider_profile")
            if override_profile:
                profile_name = str(override_profile)

    from config.provider_schema import (
        DEFAULT_PROVIDER_REGISTRY_PATH,
        load_provider_registry,
    )

    registry_path = getattr(settings, "provider_registry_path", None)
    if registry_path is None:
        # Resolve configuration only: fall back to the packaged registry path
        # when a partial settings object omits the field (common in tests).
        registry_path = DEFAULT_PROVIDER_REGISTRY_PATH

    try:
        registry = load_provider_registry(registry_path)
        profile = registry.get_profile(profile_name)
    except Exception as exc:  # KeyError / validation / IO
        raise CacheIdentityError(f"unable to resolve routing profile '{profile_name}'") from exc

    def _slot(label: str, target: Any) -> str:
        provider_id = str(getattr(target, "provider", "") or "")
        model_ref = str(getattr(target, "model", "") or "")
        provider = registry.get_provider(provider_id)
        if provider is None:
            raise CacheIdentityError(f"unknown provider '{provider_id}'")
        model = provider.resolve_model(model_ref)
        if model is None:
            raise CacheIdentityError(f"unknown model '{model_ref}' for provider '{provider_id}'")
        return f"{label}={provider.id}:{model.name}"

    routing_enabled = bool(getattr(settings, "model_routing_enabled", True))
    return "|".join(
        (
            f"profile={profile_name}",
            _slot("fast", profile.fast),
            _slot("strong", profile.strong),
            f"routing={int(routing_enabled)}",
        )
    )


def resolve_index_identity(
    tenant: str,
    *,
    settings: Any | None = None,
) -> str | None:
    """Return durable index identity, or ``None`` when not trustworthy."""
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()

    backend = str(getattr(settings, "vector_backend", "chroma") or "chroma").strip().lower()
    if backend != "chroma":
        # Non-Chroma backends currently lack a durable generation identity.
        return None

    try:
        from vectordb.manager import resolve_response_cache_index_identity
    except Exception:
        return None

    try:
        return resolve_response_cache_index_identity(
            tenant or "default",
            settings=settings,
        )
    except Exception:
        logger.debug("index identity resolution failed", exc_info=True)
        return None


def _resolve_request_experiment(
    tenant: str,
    *,
    user_id: str,
    session_id: str | None,
    experiment: Any | None,
) -> Any | None:
    if experiment is not None:
        return experiment
    try:
        from agent.prompt_registry import (
            load_current_experiment,
            resolve_active_experiment,
        )

        assigned = resolve_active_experiment(
            tenant_id=tenant or "default",
            user_id=user_id or "anonymous",
            session_id=session_id,
        )
        if assigned is not None:
            return assigned
        return load_current_experiment()
    except Exception:
        return None


def build_llm_response_cache_key(
    tenant: str,
    question: str,
    *,
    settings: Any | None = None,
    user_id: str = "anonymous",
    session_id: str | None = None,
    experiment: Any | None = None,
) -> str | None:
    """Build ``llm_resp:<tenant>:v1:<digest>`` or ``None`` on identity failure.

    The literal prefix ``llm_resp:<tenant>:`` is preserved so existing upload
    invalidation patterns ``llm_resp:<tenant>:*`` continue to match.
    """
    try:
        if settings is None:
            from config.settings import get_settings

            settings = get_settings()

        tenant_id = tenant or "default"
        active_experiment = _resolve_request_experiment(
            tenant_id,
            user_id=user_id,
            session_id=session_id,
            experiment=experiment,
        )

        index_id = resolve_index_identity(tenant_id, settings=settings)
        if not index_id:
            return None

        prompt_id = resolve_prompt_identity(experiment=active_experiment)
        if not prompt_id:
            return None

        model_id = resolve_model_identity(
            settings=settings,
            experiment=active_experiment,
        )
        if not model_id:
            return None

        query = normalize_query(question)
        material = "\0".join(
            (
                SCHEMA_VERSION,
                tenant_id,
                index_id,
                prompt_id,
                model_id,
                query,
            )
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
        return f"llm_resp:{tenant_id}:{SCHEMA_VERSION}:{digest}"
    except CacheIdentityError:
        logger.debug("cache identity unresolved; fail closed", exc_info=True)
        return None
    except Exception:
        logger.debug("cache key build failed; fail closed", exc_info=True)
        return None

from __future__ import annotations

import hashlib
import os
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from evaluation.experiment_schema import Experiment, load_experiment

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_OVERRIDE_PATH = PROJECT_ROOT / "config" / "experiment_override.yaml"
CURRENT_EXPERIMENT: ContextVar[Experiment | None] = ContextVar(
    "current_experiment",
    default=None,
)

# Task-154 sticky rollout: in-memory cache keyed by tenant_id. Populated by
# the admin assignments upsert endpoint and (optionally) a lifespan refresh
# hook. Kept deliberately simple because assignments change rarely and the
# sync resolver must stay callable from the graph hot path.
_ASSIGNMENTS_CACHE: dict[str, dict[str, Any]] = {}


def _load_staged_override_payload() -> dict[str, object]:
    experiment_id = (os.getenv("EXPERIMENT_ID", "") or "").strip()
    if not experiment_id or not EXPERIMENT_OVERRIDE_PATH.exists():
        return {}

    payload = yaml.safe_load(EXPERIMENT_OVERRIDE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}

    configured_id = payload.get("experiment_id")
    if configured_id and configured_id != experiment_id:
        return {}
    return payload


def _load_staged_prompt_overrides() -> dict[str, str]:
    payload = _load_staged_override_payload()
    overrides = payload.get("prompt_overrides") or {}
    return {str(key): str(value) for key, value in overrides.items()}


def load_current_experiment() -> Experiment | None:
    experiment_id = (os.getenv("EXPERIMENT_ID", "") or "").strip()
    payload = _load_staged_override_payload()
    if not experiment_id or not payload:
        return None

    experiment_path = (
        EXPERIMENT_OVERRIDE_PATH.parent.parent
        / "evaluation"
        / "experiments"
        / f"{experiment_id}.yaml"
    )
    if experiment_path.exists():
        try:
            return load_experiment(experiment_path)
        except Exception:
            return None

    prompt_overrides = payload.get("prompt_overrides") or {}
    settings_overrides = payload.get("settings_overrides") or {}
    return Experiment(
        id="2026-01-01-staged-runtime",
        name=f"staged:{experiment_id}",
        created_at=datetime.now(timezone.utc),
        created_by="runtime",
        description="staged experiment override loaded at runtime",
        prompt_overrides={
            str(key): str(value) for key, value in prompt_overrides.items()
        },
        settings_overrides=dict(settings_overrides) if isinstance(settings_overrides, dict) else {},
        parent_experiment_id=None,
        status="running",
        tags=["staged"],
    )


def set_assignment_cache_entry(
    tenant_id: str,
    experiment_id: str,
    rollout_percentage: int,
) -> None:
    """Populate or update the sticky rollout cache for a tenant."""
    _ASSIGNMENTS_CACHE[tenant_id] = {
        "experiment_id": experiment_id,
        "rollout_percentage": max(0, min(100, int(rollout_percentage))),
    }


def clear_assignment_cache_entry(tenant_id: str) -> None:
    _ASSIGNMENTS_CACHE.pop(tenant_id, None)


def clear_assignment_cache() -> None:
    _ASSIGNMENTS_CACHE.clear()


def _stable_rollout_bucket(tenant_id: str, user_id: str, session_id: str | None) -> int:
    """Deterministic 0-99 bucket for sticky rollout decisions."""
    key = f"{tenant_id}:{session_id or user_id or 'anonymous'}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:4]
    return int.from_bytes(digest, "big") % 100


async def refresh_assignment_cache_from_db(session) -> int:
    """Async refresh of the sticky rollout cache from `experiment_assignments`.

    Intended to be called from FastAPI lifespan/startup or a periodic task.
    Returns the number of tenants loaded.
    """
    from sqlalchemy import text as sql_text  # noqa: PLC0415

    result = await session.execute(
        sql_text(
            "SELECT tenant_id, experiment_id, rollout_percentage "
            "FROM experiment_assignments"
        ),
        {},
    )
    rows = list(result.mappings().all())
    _ASSIGNMENTS_CACHE.clear()
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "").strip()
        experiment_id = str(row.get("experiment_id") or "").strip()
        if not tenant_id or not experiment_id:
            continue
        _ASSIGNMENTS_CACHE[tenant_id] = {
            "experiment_id": experiment_id,
            "rollout_percentage": int(row.get("rollout_percentage") or 0),
        }
    return len(_ASSIGNMENTS_CACHE)


def resolve_active_experiment(
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> Experiment | None:
    """Sticky hash-based rollout lookup.

    Returns the experiment assigned to this tenant when:
    - `EXPERIMENT_ASSIGNMENT_ENABLED` is true in settings;
    - the tenant has a cached assignment with `rollout_percentage > 0`;
    - the stable bucket for `(tenant_id, session_id or user_id)` falls
      below `rollout_percentage`;
    - the experiment YAML loads successfully.

    Tests may still monkeypatch the function directly to simulate specific
    resolver outputs.
    """
    settings = None
    try:
        from config.settings import get_settings  # noqa: PLC0415

        settings = get_settings()
        if not getattr(settings, "experiment_assignment_enabled", False):
            return None
    except Exception:
        return None

    assignment = _ASSIGNMENTS_CACHE.get(tenant_id)
    if not assignment:
        return None

    rollout = int(assignment.get("rollout_percentage") or 0)
    if rollout <= 0:
        return None

    bucket = _stable_rollout_bucket(tenant_id, user_id, session_id)
    if bucket >= rollout:
        return None

    experiment_id = str(assignment.get("experiment_id") or "").strip()
    if not experiment_id:
        return None

    project_root = Path(getattr(settings, "project_root", PROJECT_ROOT))
    experiment_path = project_root / "evaluation" / "experiments" / f"{experiment_id}.yaml"
    if not experiment_path.exists():
        return None
    try:
        return load_experiment(experiment_path)
    except Exception:
        return None


def set_current_experiment(exp: Experiment | None) -> Token[Experiment | None]:
    return CURRENT_EXPERIMENT.set(exp)


def reset_current_experiment(token: Token[Experiment | None]) -> None:
    CURRENT_EXPERIMENT.reset(token)


def get_prompt(name: str, experiment: Experiment | None = None) -> str:
    from agent.prompts import DEPLOYED_PROMPT_OVERRIDES, PROMPT_REGISTRY

    if name not in PROMPT_REGISTRY:
        raise KeyError(f"unknown prompt: {name}")

    if experiment is None:
        experiment = CURRENT_EXPERIMENT.get()

    if experiment is not None and name in experiment.prompt_overrides:
        return experiment.prompt_overrides[name]

    staged_overrides = _load_staged_prompt_overrides()
    if name in staged_overrides:
        return staged_overrides[name]

    if name in DEPLOYED_PROMPT_OVERRIDES:
        return DEPLOYED_PROMPT_OVERRIDES[name]

    return PROMPT_REGISTRY[name]["text"]

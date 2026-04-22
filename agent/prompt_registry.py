from __future__ import annotations

import os
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path

import yaml

from evaluation.experiment_schema import Experiment, load_experiment

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_OVERRIDE_PATH = PROJECT_ROOT / "config" / "experiment_override.yaml"
CURRENT_EXPERIMENT: ContextVar[Experiment | None] = ContextVar(
    "current_experiment",
    default=None,
)


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


def resolve_active_experiment(
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> Experiment | None:
    """Return the experiment assigned to this tenant/user, or None.

    Real resolution (tenant assignment lookup + sticky hash-based rollout)
    is wired into the admin assignment layer; tests override this function
    directly via monkeypatch.
    """
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

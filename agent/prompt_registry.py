from __future__ import annotations

import os
from pathlib import Path

import yaml

from evaluation.experiment_schema import Experiment

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_OVERRIDE_PATH = PROJECT_ROOT / "config" / "experiment_override.yaml"


def _load_staged_prompt_overrides() -> dict[str, str]:
    experiment_id = (os.getenv("EXPERIMENT_ID", "") or "").strip()
    if not experiment_id or not EXPERIMENT_OVERRIDE_PATH.exists():
        return {}

    payload = yaml.safe_load(EXPERIMENT_OVERRIDE_PATH.read_text(encoding="utf-8")) or {}
    configured_id = payload.get("experiment_id")
    if configured_id and configured_id != experiment_id:
        return {}

    overrides = payload.get("prompt_overrides") or {}
    return {str(key): str(value) for key, value in overrides.items()}


def get_prompt(name: str, experiment: Experiment | None = None) -> str:
    from agent.prompts import DEPLOYED_PROMPT_OVERRIDES, PROMPT_REGISTRY

    if name not in PROMPT_REGISTRY:
        raise KeyError(f"unknown prompt: {name}")

    if experiment is not None and name in experiment.prompt_overrides:
        return experiment.prompt_overrides[name]

    staged_overrides = _load_staged_prompt_overrides()
    if name in staged_overrides:
        return staged_overrides[name]

    if name in DEPLOYED_PROMPT_OVERRIDES:
        return DEPLOYED_PROMPT_OVERRIDES[name]

    return PROMPT_REGISTRY[name]["text"]

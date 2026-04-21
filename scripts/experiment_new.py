# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.prompt_registry import get_prompt
from agent.prompts import PROMPT_REGISTRY
from config.settings import EXPERIMENT_SETTINGS_KEYS, get_settings
from evaluation.experiment_schema import Experiment, load_experiment, save_experiment


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _created_by() -> str:
    for env_name in ("USEREMAIL", "GIT_AUTHOR_EMAIL", "EMAIL", "USERNAME", "USER"):
        value = (os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return "system"


def _experiments_dir() -> Path:
    settings = get_settings()
    return Path(getattr(settings, "project_root", PROJECT_ROOT)) / "evaluation" / "experiments"


def _current_prompt_snapshot() -> dict[str, str]:
    return {name: get_prompt(name) for name in PROMPT_REGISTRY}


def _current_settings_snapshot() -> dict[str, object]:
    settings = get_settings()
    if not any(hasattr(settings, key) for key in EXPERIMENT_SETTINGS_KEYS):
        from config.settings import get_settings as runtime_get_settings

        settings = runtime_get_settings()
    return {
        key: getattr(settings, key)
        for key in EXPERIMENT_SETTINGS_KEYS
        if hasattr(settings, key)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--from", dest="source", default="current")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    slug = _slugify(args.name)
    if not slug:
        raise SystemExit("experiment name must contain letters or numbers")

    experiments_dir = _experiments_dir()
    timestamp = datetime.now(timezone.utc)
    experiment_id = f"{timestamp.date().isoformat()}-{slug}"
    experiment_path = experiments_dir / f"{experiment_id}.yaml"
    if experiment_path.exists():
        raise SystemExit(f"experiment already exists: {experiment_id}")

    parent_experiment_id: str | None = None
    if args.source == "current":
        prompt_overrides = _current_prompt_snapshot()
        settings_overrides = _current_settings_snapshot()
    else:
        parent = load_experiment(experiments_dir / f"{args.source}.yaml")
        parent_experiment_id = parent.id
        prompt_overrides = dict(parent.prompt_overrides)
        settings_overrides = dict(parent.settings_overrides)

    experiment = Experiment(
        id=experiment_id,
        name=args.name,
        created_at=timestamp,
        created_by=_created_by(),
        description=args.description,
        prompt_overrides=prompt_overrides,
        settings_overrides=settings_overrides,
        parent_experiment_id=parent_experiment_id,
        status="draft",
        tags=[],
    )
    save_experiment(experiment, experiment_path)
    print(experiment_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from pprint import pformat

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.prompt_registry import get_prompt
from agent.prompts import PROMPT_REGISTRY
from config.settings import EXPERIMENT_SETTINGS_KEYS, get_settings
from evaluation.experiment_schema import Experiment, load_experiment, save_experiment

SETTINGS_BEGIN = "# BEGIN DEPLOYED_EXPERIMENT_SETTINGS"
SETTINGS_END = "# END DEPLOYED_EXPERIMENT_SETTINGS"
PROMPTS_BEGIN = "# BEGIN DEPLOYED_PROMPT_OVERRIDES"
PROMPTS_END = "# END DEPLOYED_PROMPT_OVERRIDES"


def _experiments_dir() -> Path:
    settings = get_settings()
    return Path(getattr(settings, "project_root", PROJECT_ROOT)) / "evaluation" / "experiments"


def _project_root() -> Path:
    settings = get_settings()
    return Path(getattr(settings, "project_root", PROJECT_ROOT))


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


def _diff_block(title: str, current: dict[str, object], target: dict[str, object]) -> str:
    current_dump = yaml.safe_dump(current, sort_keys=True, allow_unicode=True).splitlines()
    target_dump = yaml.safe_dump(target, sort_keys=True, allow_unicode=True).splitlines()
    diff = difflib.unified_diff(current_dump, target_dump, fromfile=f"{title}:current", tofile=f"{title}:target", lineterm="")
    return "\n".join(diff)


def _replace_block(text: str, begin_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(begin_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"missing markers {begin_marker} / {end_marker}")
    end += len(end_marker)
    return text[:start] + replacement + text[end:]


def _write_override_file(project_root: Path, experiment: Experiment) -> Path:
    override_path = project_root / "config" / "experiment_override.yaml"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment_id": experiment.id,
        "prompt_overrides": experiment.prompt_overrides,
        "settings_overrides": experiment.settings_overrides,
    }
    override_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    return override_path


def _render_settings_block(settings_overrides: dict[str, object]) -> str:
    return (
        f"{SETTINGS_BEGIN}\n"
        f"DEPLOYED_EXPERIMENT_SETTINGS: dict[str, Any] = {pformat(settings_overrides, width=100)}\n"
        f"{SETTINGS_END}"
    )


def _render_prompt_block(prompt_overrides: dict[str, str]) -> str:
    return (
        f"{PROMPTS_BEGIN}\n"
        f"DEPLOYED_PROMPT_OVERRIDES: dict[str, str] = {pformat(prompt_overrides, width=100)}\n"
        f"{PROMPTS_END}"
    )


def _deploy(project_root: Path, experiment: Experiment) -> None:
    settings_path = project_root / "config" / "settings.py"
    prompts_path = project_root / "agent" / "prompts.py"

    settings_text = settings_path.read_text(encoding="utf-8")
    prompts_text = prompts_path.read_text(encoding="utf-8")

    settings_text = _replace_block(
        settings_text,
        SETTINGS_BEGIN,
        SETTINGS_END,
        _render_settings_block(experiment.settings_overrides),
    )
    prompts_text = _replace_block(
        prompts_text,
        PROMPTS_BEGIN,
        PROMPTS_END,
        _render_prompt_block(experiment.prompt_overrides),
    )

    settings_path.write_text(settings_text, encoding="utf-8", newline="\n")
    prompts_path.write_text(prompts_text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_id")
    parser.add_argument("--mode", choices=("dry-run", "stage", "deploy"), default="dry-run")
    args = parser.parse_args()

    experiment_path = _experiments_dir() / f"{args.experiment_id}.yaml"
    experiment = load_experiment(experiment_path)

    if args.mode == "dry-run":
        print(_diff_block("settings", _current_settings_snapshot(), experiment.settings_overrides))
        print(_diff_block("prompts", _current_prompt_snapshot(), experiment.prompt_overrides))
        return 0

    if args.mode == "stage":
        override_path = _write_override_file(_project_root(), experiment)
        print(override_path)
        return 0

    _deploy(_project_root(), experiment)
    experiment.status = "deployed"
    save_experiment(experiment, experiment_path)
    print(f"Updated {Path('config/settings.py')}")
    print(f"Updated {Path('agent/prompts.py')}")
    print(f"Updated {experiment_path.relative_to(_project_root())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

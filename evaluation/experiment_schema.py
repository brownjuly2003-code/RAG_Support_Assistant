from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


_EXPERIMENT_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


class Experiment(BaseModel):
    id: str
    name: str
    created_at: datetime
    created_by: str
    description: str
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    settings_overrides: dict[str, Any] = Field(default_factory=dict)
    parent_experiment_id: str | None = None
    status: Literal["draft", "running", "completed", "deployed", "archived"]
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _EXPERIMENT_ID_RE.fullmatch(value):
            raise ValueError("experiment id must match YYYY-MM-DD-name-slug")
        return value


def load_experiment(path: str | Path) -> Experiment:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Experiment.model_validate(payload)


def save_experiment(exp: Experiment, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = exp.model_dump(mode="json")
    target.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class CuratedInput(BaseModel):
    query: str = ""
    context_hint: str = ""
    channel: str = "web"


class CuratedExpected(BaseModel):
    answer_contains: list[str] = Field(default_factory=list)
    answer_not_contains: list[str] = Field(default_factory=list)
    route: str = "auto"
    min_quality: int = 70
    min_factuality: int = 70
    citations_min_count: int = 1


class CuratedCase(BaseModel):
    case_id: str
    tenant_id: str
    input: CuratedInput
    expected: CuratedExpected
    human_verdict: Literal["good", "bad"]
    reviewer_notes: str = ""
    source_trace_id: str
    created_at: datetime
    tags: list[str] = Field(default_factory=list)


def load_curated_cases(path: Path) -> list[CuratedCase]:
    target = Path(path)
    if not target.exists():
        return []

    cases: list[CuratedCase] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            cases.append(CuratedCase.model_validate_json(payload))
    return cases


def _case_hash(case_id: str) -> int:
    return int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16)


def split_cases(
    cases: list[CuratedCase],
    ratio: float = 0.8,
) -> tuple[list[CuratedCase], list[CuratedCase]]:
    stable_cases = sorted(cases, key=lambda item: item.case_id)
    ordered_cases = sorted(stable_cases, key=lambda item: (_case_hash(item.case_id), item.case_id))

    if ratio <= 0:
        return [], ordered_cases
    if ratio >= 1:
        return ordered_cases, []

    boundary = int(len(ordered_cases) * ratio)
    return ordered_cases[:boundary], ordered_cases[boundary:]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_since(value: str | date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(value)
    if len(value) == 10:
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=timezone.utc)
    return _as_utc(parsed)


def filter_cases(
    cases: list[CuratedCase],
    tenant: str | None = None,
    tags: list[str] | None = None,
    since: str | date | datetime | None = None,
) -> list[CuratedCase]:
    since_dt = _normalize_since(since)
    required_tags = {item for item in (tags or []) if item}

    filtered: list[CuratedCase] = []
    for case in cases:
        if tenant is not None and case.tenant_id != tenant:
            continue
        if required_tags and not required_tags.issubset(set(case.tags)):
            continue
        if since_dt is not None and _as_utc(case.created_at) < since_dt:
            continue
        filtered.append(case)
    return filtered

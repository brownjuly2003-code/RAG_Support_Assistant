# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import random
import sqlite3
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class InfrastructureError(RuntimeError):
    pass


class CaseExpectation(BaseModel):
    model_config = ConfigDict(extra="allow")

    answer_contains: list[str] = Field(default_factory=list)
    answer_contains_any: list[list[str]] = Field(default_factory=list)
    answer_not_contains: list[str] = Field(default_factory=list)
    route: str | None = None
    min_quality: float | None = None
    min_factuality: float | None = None
    citations_min_count: int | None = None
    # Plan §7.4: optional context-recall floor (0..1 or 0..100; compared to run metric).
    min_context_recall: float | None = None


class CuratedCase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    case_id: str
    tenant_id: str = Field(default="default", validation_alias=AliasChoices("tenant_id", "tenant"))
    query: str = Field(validation_alias=AliasChoices("query", "question"))
    expected: CaseExpectation = Field(default_factory=CaseExpectation)
    # Plan §7.4: versioned dataset slices for coverage validation / filtering.
    slices: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    session_id: str | None = None
    turn_index: int | None = None


class CaseRunResult(BaseModel):
    answer: str = ""
    quality_score: float = 0.0
    factuality_score: float = 0.0
    citations: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None
    cost_usd: float | None = None
    route: str = "unknown"
    trace_id: str = ""
    context_recall: float | None = None
    # Plan §7.1: skipped/infra must fail the release gate (never graceful pass).
    skipped: bool = False
    skip_reason: str = ""
    infrastructure_error: bool = False


# Plan §7.4 required coverage dimensions (at least one case each).
REQUIRED_DATASET_SLICES: frozenset[str] = frozenset(
    {
        "multi_tenant",
        "multi_turn",
        "claim_citation",
        "no_answer",
        "tools",
        "streaming",
        "adversarial",
        "pii",
        "durable_escalation",
        "context_recall",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "current"


def _estimate_mock_tokens(text: str) -> int:
    from llm.providers.base import estimate_tokens

    return estimate_tokens(text)


def _is_refusal_answer(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    if not normalized:
        return False
    patterns = (
        "i don't know",
        "cannot help",
        "не знаю",
        "не могу помочь",
        "обратитесь",
    )
    return any(pattern in normalized for pattern in patterns)


def _is_infrastructure_failure(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    return "[provider_unavailable]" in normalized or "[model_mismatch]" in normalized


def decide_regression_gate(
    *,
    total_cases: int,
    effective_cases: int,
    infrastructure_failures: int,
    skipped_cases: int,
    regressions: int,
    max_regressions: int,
    baseline_pass_rate: float,
    candidate_pass_rate: float,
    min_pass_rate: float,
) -> dict[str, Any]:
    """Compute release-gate verdict (plan §7.1 fail-closed).

    Infrastructure failures, skipped cases, and empty effective sets **never**
    pass. Pass rates are only evaluated when ``effective_cases > 0`` so an
    all-skipped run cannot claim 1.0 / PASSED via division edge cases.
    Verdict is always ``PASS`` or ``FAIL`` — never ``PASSED (graceful skip)``.
    """
    reasons: list[str] = []
    if total_cases <= 0:
        reasons.append("no cases executed")
    if infrastructure_failures > 0:
        reasons.append(
            f"infrastructure failures: {infrastructure_failures} "
            "(provider/pipeline/import errors fail the gate)"
        )
    if skipped_cases > 0:
        reasons.append(
            f"skipped cases: {skipped_cases} "
            "(graceful skip is not a pass)"
        )
    if total_cases > 0 and effective_cases <= 0:
        reasons.append(
            "no effective cases after infrastructure/skip "
            "(cannot claim pass rates)"
        )

    if effective_cases > 0:
        if regressions > max_regressions:
            reasons.append(
                f"max regressions exceeded: {regressions} > {max_regressions}"
            )
        if candidate_pass_rate < min_pass_rate:
            reasons.append(
                f"candidate pass rate {candidate_pass_rate:.2%} "
                f"below minimum {min_pass_rate:.2%}"
            )
        if candidate_pass_rate + 1e-9 < baseline_pass_rate:
            reasons.append(
                f"candidate pass rate {candidate_pass_rate:.2%} "
                f"below baseline {baseline_pass_rate:.2%}"
            )

    passed = not reasons
    return {
        "passed": passed,
        "reasons": reasons,
        "verdict": "PASS" if passed else "FAIL",
        # Explicit anti-pattern: never report graceful-skip as success evidence.
        "graceful_skip_pass_forbidden": True,
    }


MOCK_EVIDENCE_MODES = frozenset(
    {
        "mock-provider-benchmark",
        "mock-experiment-regression",
    }
)

# Plan §7.3: durable merge-base baseline artifact (not re-run of candidate SHA).
BASELINE_ARTIFACT_SCHEMA_VERSION = 1
BASELINE_ARTIFACT_KIND = "regression-baseline"


def build_baseline_artifact(
    *,
    case_results: dict[str, CaseRunResult | dict[str, Any]],
    git_sha: str | None = None,
    merge_base: str | None = None,
    dataset_path: str | None = None,
    baseline_label: str = "baseline",
    mode: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a versioned baseline artifact payload from per-case run results."""
    cases_payload: dict[str, dict[str, Any]] = {}
    for case_id, result in case_results.items():
        if isinstance(result, CaseRunResult):
            cases_payload[str(case_id)] = result.model_dump(mode="json")
        elif isinstance(result, dict):
            cases_payload[str(case_id)] = dict(result)
        else:
            raise TypeError(f"unsupported baseline result type for {case_id}: {type(result)}")
    stamp = created_at or _utc_now()
    return {
        "schema_version": BASELINE_ARTIFACT_SCHEMA_VERSION,
        "kind": BASELINE_ARTIFACT_KIND,
        "created_at": stamp.isoformat(),
        "git_sha": git_sha,
        "merge_base": merge_base or git_sha,
        "dataset_path": dataset_path,
        "baseline_label": baseline_label,
        "mode": mode,
        "cases": cases_payload,
    }


def write_baseline_artifact(artifact: dict[str, Any], path: Path) -> Path:
    """Persist baseline artifact JSON (UTF-8, trailing newline)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(artifact)
    # Never serialize the runtime case_map helper.
    payload.pop("case_map", None)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def load_baseline_artifact(path: Path) -> dict[str, Any]:
    """Load and validate a baseline artifact; attach ``case_map`` of CaseRunResult."""
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError(f"baseline artifact not found: {artifact_path}")
    raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("baseline artifact must be a JSON object")
    kind = raw.get("kind")
    if kind != BASELINE_ARTIFACT_KIND:
        raise ValueError(
            f"baseline artifact kind must be {BASELINE_ARTIFACT_KIND!r}, got {kind!r}"
        )
    version = int(raw.get("schema_version") or 0)
    if version != BASELINE_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported baseline artifact schema_version={version}; "
            f"expected {BASELINE_ARTIFACT_SCHEMA_VERSION}"
        )
    cases_raw = raw.get("cases")
    if not isinstance(cases_raw, dict) or not cases_raw:
        raise ValueError("baseline artifact must include non-empty cases map")
    case_map: dict[str, CaseRunResult] = {}
    for case_id, payload in cases_raw.items():
        if not isinstance(payload, dict):
            raise ValueError(f"baseline case {case_id!r} must be an object")
        case_map[str(case_id)] = CaseRunResult.model_validate(payload)
    out = dict(raw)
    out["case_map"] = case_map
    out["path"] = str(artifact_path)
    return out


def baseline_artifact_from_report(
    report: dict[str, Any],
    *,
    git_sha: str | None = None,
    merge_base: str | None = None,
) -> dict[str, Any]:
    """Extract baseline-side case results from a full regression report."""
    case_results: dict[str, dict[str, Any]] = {}
    for entry in report.get("cases") or []:
        if not isinstance(entry, dict):
            continue
        case_id = entry.get("case_id")
        baseline_payload = entry.get("baseline")
        if not case_id or not isinstance(baseline_payload, dict):
            continue
        case_results[str(case_id)] = baseline_payload
    if not case_results:
        raise ValueError("report has no baseline case payloads to artifactize")
    return build_baseline_artifact(
        case_results=case_results,
        git_sha=git_sha,
        merge_base=merge_base,
        dataset_path=str(report.get("dataset") or "") or None,
        baseline_label=str(report.get("baseline") or "baseline"),
        mode=str(report.get("mode") or "") or None,
    )


def resolve_git_rev(project_root: Path, rev: str = "HEAD") -> str | None:
    """Best-effort ``git rev-parse``; returns None when git is unavailable."""
    import subprocess

    try:
        completed = subprocess.run(
            ["git", "rev-parse", rev],
            cwd=str(project_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def resolve_git_merge_base(
    project_root: Path,
    base_ref: str = "origin/master",
) -> str | None:
    """Best-effort ``git merge-base HEAD <base_ref>`` for artifact metadata."""
    import subprocess

    try:
        completed = subprocess.run(
            ["git", "merge-base", "HEAD", base_ref],
            cwd=str(project_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def _empty_baseline_required_report(
    *,
    baseline: str,
    candidate: str,
    dataset_path: Path | None,
    release_gate: bool,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail-closed report when a required baseline artifact is missing/unusable."""
    current_time = now or _utc_now()
    gate = {
        "passed": False,
        "metrics_passed": False,
        "verdict": "FAIL",
        "max_regressions": 0,
        "min_pass_rate": 0.0,
        "reasons": [reason],
        "graceful_skip_pass_forbidden": True,
    }
    report: dict[str, Any] = {
        "run_id": _make_run_id(current_time),
        "created_at": current_time.isoformat(),
        "baseline": baseline,
        "candidate": candidate,
        "dataset": str(dataset_path) if dataset_path is not None else None,
        "tenant": "all",
        "baseline_source": "missing",
        # Real fail-closed gate (not mock smoke): missing merge-base baseline.
        "mode": "experiment-regression",
        "evidence_valid": True,
        "aggregate": {
            "total_cases": 0,
            "effective_cases": 0,
            "infrastructure_failures": 0,
            "skipped_cases": 0,
            "baseline_pass_rate": 0.0,
            "candidate_pass_rate": 0.0,
            "regressions": 0,
            "new_passes": 0,
            "neutral": 0,
            "baseline_total_cost_usd": 0.0,
            "candidate_total_cost_usd": 0.0,
            "baseline_avg_latency_ms": 0.0,
            "candidate_avg_latency_ms": 0.0,
            "baseline_refusal_rate": 0.0,
            "candidate_refusal_rate": 0.0,
        },
        "gate": gate,
        "cases": [],
        "regressions": [],
        "new_passes": [],
        "exit_code": 1,
    }
    return apply_evidence_policy(report, release_gate=release_gate)


def apply_evidence_policy(
    report: dict[str, Any],
    *,
    release_gate: bool = False,
) -> dict[str, Any]:
    """Plan §7.2: mock expected-copy must never claim release PASS.

    - ``metrics_passed`` — quantitative gate only (may be green under mock).
    - ``evidence_valid`` — real pipeline/provider evidence (false for mock modes).
    - ``release_passed`` / ``gate.passed`` — only true when metrics **and** evidence.
    - Verdict ``PASS`` is reserved for release-eligible green; mock green is
      ``SMOKE_PASS`` (smoke only).
    - Exit code: smoke path uses metrics; ``release_gate=True`` uses release.
    """
    gate = report.setdefault("gate", {})
    mode = str(report.get("mode") or "")
    evidence_valid = bool(report.get("evidence_valid", mode not in MOCK_EVIDENCE_MODES))
    if mode in MOCK_EVIDENCE_MODES:
        evidence_valid = False
    report["evidence_valid"] = evidence_valid

    # Metrics result was stored as gate.passed before evidence policy runs.
    metrics_passed = bool(gate.get("metrics_passed", gate.get("passed", False)))
    reasons = list(gate.get("reasons") or [])
    release_passed = bool(metrics_passed and evidence_valid)

    gate["metrics_passed"] = metrics_passed
    gate["evidence_valid"] = evidence_valid
    gate["release_passed"] = release_passed
    gate["release_eligible"] = release_passed
    gate["release_gate"] = bool(release_gate)
    gate["graceful_skip_pass_forbidden"] = True

    if not evidence_valid:
        note = (
            "mock expected-copy / mock provider scores are not release evidence"
        )
        gate["evidence_note"] = note
        if note not in reasons:
            reasons.append(note)
        if metrics_passed:
            gate["verdict"] = "SMOKE_PASS"
        else:
            # Keep fail-closed metrics reasons; never label as release PASS.
            gate["verdict"] = "SMOKE_FAIL"
        gate["passed"] = False
        gate["reasons"] = reasons
        if release_gate:
            report["exit_code"] = 1
        else:
            report["exit_code"] = 0 if metrics_passed else 1
    else:
        gate["evidence_note"] = ""
        gate["verdict"] = "PASS" if release_passed else "FAIL"
        gate["passed"] = release_passed
        gate["reasons"] = reasons
        report["exit_code"] = 0 if release_passed else 1

    return report


def _resolve_provider_target(target: str, provider_registry_path: Path | None) -> dict[str, Any] | None:
    from config.provider_schema import load_provider_registry

    try:
        registry = load_provider_registry(provider_registry_path)
    except Exception:
        return None

    try:
        resolution = registry.resolve_model(target)
        provider = registry.get_provider(resolution.provider)
        model = provider.resolve_model(resolution.model) if provider is not None else None
        if provider is not None and model is not None:
            return {
                "kind": "model",
                "provider_id": provider.id,
                "provider_kind": provider.kind,
                "model_name": model.name,
                "input_price_per_1m_tokens": float(model.input_price_per_1m_tokens),
                "output_price_per_1m_tokens": float(model.output_price_per_1m_tokens),
            }
    except Exception:
        pass

    profile = registry.routing_profiles.get(target)
    if profile is None:
        return None

    try:
        strong_provider = registry.get_provider(profile.strong.provider)
        strong_model = (
            strong_provider.resolve_model(profile.strong.model)
            if strong_provider is not None
            else None
        )
    except Exception:
        return None

    if strong_provider is None or strong_model is None:
        return None

    return {
        "kind": "profile",
        "profile_name": target,
        "provider_id": strong_provider.id,
        "provider_kind": strong_provider.kind,
        "model_name": strong_model.name,
        "input_price_per_1m_tokens": float(strong_model.input_price_per_1m_tokens),
        "output_price_per_1m_tokens": float(strong_model.output_price_per_1m_tokens),
    }


def _build_mock_provider_result(
    case: CuratedCase,
    target: str,
    resolution: dict[str, Any],
    *,
    trace_prefix: str = "mock",
) -> CaseRunResult:
    provider_id = str(resolution["provider_id"])
    model_name = str(resolution["model_name"])
    expected = case.expected
    provider_quality_bias = {
        "ollama": 0,
        "mistral": 2,
        "gracekelly": 4,
    }
    provider_latency_ms = {
        "ollama": 180,
        "mistral": 420,
        "gracekelly": 640,
    }
    provider_factuality_bias = {
        "ollama": 0,
        "mistral": 1,
        "gracekelly": 3,
    }

    answer_parts = list(expected.answer_contains or [])
    for alternatives in expected.answer_contains_any:
        if alternatives:
            answer_parts.append(alternatives[0])
    if not answer_parts:
        answer_parts.append(f"Mock provider response for {case.query}")
    answer = " ".join(answer_parts).strip()
    citations_count = max(1, int(expected.citations_min_count or 1))
    citations = [
        {
            "index": index,
            "doc_id": f"{provider_id}-doc-{index}",
            "title": f"{provider_id}:{model_name}",
            "excerpt": answer[:120],
        }
        for index in range(1, citations_count + 1)
    ]

    input_tokens = _estimate_mock_tokens(case.query)
    output_tokens = _estimate_mock_tokens(answer)
    cost_usd = round(
        (
            input_tokens * float(resolution["input_price_per_1m_tokens"])
            + output_tokens * float(resolution["output_price_per_1m_tokens"])
        )
        / 1_000_000,
        6,
    )

    return CaseRunResult(
        answer=answer,
        quality_score=min(100.0, max(float(expected.min_quality or 75), 75.0) + provider_quality_bias.get(provider_id, 0)),
        factuality_score=min(
            100.0,
            max(float(expected.min_factuality or 80), 80.0) + provider_factuality_bias.get(provider_id, 0),
        ),
        citations=citations,
        duration_ms=int(provider_latency_ms.get(provider_id, 500)),
        cost_usd=cost_usd,
        route=str(expected.route or "auto"),
        trace_id=f"{trace_prefix}-{_slug(target)}-{case.case_id}",
    )


def load_curated_cases(path: Path) -> list[CuratedCase]:
    cases: list[CuratedCase] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(CuratedCase.model_validate_json(line))
    return cases


def sample_cases(
    cases: Sequence[CuratedCase],
    *,
    max_cases: int | None = None,
    seed: int = 42,
) -> list[CuratedCase]:
    selected = list(cases)
    if max_cases is None or max_cases <= 0 or len(selected) <= max_cases:
        return selected
    rng = random.Random(seed)
    sampled = rng.sample(selected, max_cases)
    sampled.sort(key=lambda item: item.case_id)
    return sampled


def collect_dataset_slices(cases: Sequence[CuratedCase]) -> set[str]:
    """Union of ``slices`` (and legacy ``tags``) across cases."""
    found: set[str] = set()
    for case in cases:
        for item in case.slices or []:
            value = str(item).strip()
            if value:
                found.add(value)
        for item in case.tags or []:
            value = str(item).strip()
            if value:
                found.add(value)
    return found


def validate_dataset_slice_coverage(
    cases: Sequence[CuratedCase],
    *,
    required_slices: frozenset[str] | set[str] | None = None,
    min_cases_per_slice: int = 1,
) -> dict[str, Any]:
    """Plan §7.4: ensure versioned dataset covers required evaluation slices."""
    required = frozenset(required_slices or REQUIRED_DATASET_SLICES)
    if min_cases_per_slice < 1:
        raise ValueError("min_cases_per_slice must be >= 1")

    counts: dict[str, int] = {name: 0 for name in sorted(required)}
    for case in cases:
        labels = {str(x).strip() for x in (case.slices or []) if str(x).strip()}
        labels |= {str(x).strip() for x in (case.tags or []) if str(x).strip()}
        for name in required:
            if name in labels:
                counts[name] = counts.get(name, 0) + 1

    missing = sorted(name for name, count in counts.items() if count < min_cases_per_slice)
    reasons: list[str] = []
    if missing:
        reasons.append(
            "missing required slices (or below min_cases_per_slice="
            f"{min_cases_per_slice}): {missing}"
        )
    if "multi_tenant" in required and counts.get("multi_tenant", 0) >= min_cases_per_slice:
        multi_tenant_ids = {
            case.tenant_id
            for case in cases
            if "multi_tenant" in set(case.slices or []) or "multi_tenant" in set(case.tags or [])
        }
        if len(multi_tenant_ids) < 2:
            reasons.append(
                "multi_tenant slice requires >=2 distinct tenant_id values "
                f"among multi_tenant cases (got {sorted(multi_tenant_ids)!r})"
            )
    if "multi_turn" in required and counts.get("multi_turn", 0) >= min_cases_per_slice:
        # At least one session with 2+ turns among multi_turn cases.
        by_session: dict[str, list[int]] = {}
        for case in cases:
            labels = set(case.slices or []) | set(case.tags or [])
            if "multi_turn" not in labels or not case.session_id:
                continue
            by_session.setdefault(case.session_id, []).append(int(case.turn_index or 0))
        if not any(len(turns) >= 2 for turns in by_session.values()):
            reasons.append(
                "multi_turn slice requires a session_id with at least two turns"
            )

    return {
        "ok": not reasons,
        "required_slices": sorted(required),
        "slice_counts": counts,
        "missing_slices": missing,
        "total_cases": len(cases),
        "reasons": reasons,
    }


def _normalize_metric_threshold(value: float) -> float:
    """Accept 0..1 or 0..100 style thresholds; compare in 0..100 space when >1."""
    return float(value)


def _metric_meets_floor(actual: float | None, minimum: float) -> bool:
    if actual is None:
        return False
    # If both look like ratios (<=1.0), compare as ratios; else 0..100 scale.
    if minimum <= 1.0 and actual <= 1.0:
        return actual + 1e-9 >= minimum
    # Normalize ratio actual to percent when threshold is percent-like.
    actual_n = actual * 100.0 if actual <= 1.0 and minimum > 1.0 else actual
    minimum_n = minimum * 100.0 if minimum <= 1.0 and actual > 1.0 else minimum
    return actual_n + 1e-9 >= minimum_n


def _evaluate_case_output(result: CaseRunResult, expected: CaseExpectation) -> tuple[bool, list[str]]:
    failures: list[str] = []

    if expected.route is not None and result.route != expected.route:
        failures.append(f"route expected '{expected.route}' but got '{result.route}'")

    if expected.min_quality is not None and result.quality_score < expected.min_quality:
        failures.append(
            f"quality {result.quality_score:g} below minimum {expected.min_quality:g}"
        )

    if expected.min_factuality is not None and result.factuality_score < expected.min_factuality:
        failures.append(
            f"factuality {result.factuality_score:g} below minimum {expected.min_factuality:g}"
        )

    if expected.citations_min_count is not None and len(result.citations) < expected.citations_min_count:
        failures.append(
            f"citations {len(result.citations)} below minimum {expected.citations_min_count}"
        )

    if expected.min_context_recall is not None:
        floor = _normalize_metric_threshold(float(expected.min_context_recall))
        if not _metric_meets_floor(result.context_recall, floor):
            failures.append(
                f"context_recall {result.context_recall!r} below minimum {floor:g}"
            )

    answer_lower = (result.answer or "").lower()
    for needle in expected.answer_contains:
        if needle.lower() not in answer_lower:
            failures.append(f"answer missing '{needle}'")

    for alternatives in expected.answer_contains_any:
        options = [needle for needle in alternatives if needle]
        if options and not any(needle.lower() in answer_lower for needle in options):
            failures.append(f"answer missing one of {options!r}")

    for needle in expected.answer_not_contains:
        if needle.lower() in answer_lower:
            failures.append(f"answer contains forbidden '{needle}'")

    return not failures, failures


def _build_diff(baseline: CaseRunResult, candidate: CaseRunResult) -> dict[str, Any]:
    return {
        "answer_changed": baseline.answer != candidate.answer,
        "quality_delta": round(candidate.quality_score - baseline.quality_score, 4),
        "factuality_delta": round(candidate.factuality_score - baseline.factuality_score, 4),
        "route_changed": baseline.route != candidate.route,
        "citations_delta": len(candidate.citations) - len(baseline.citations),
        "cost_delta": round((candidate.cost_usd or 0.0) - (baseline.cost_usd or 0.0), 6),
    }


def run_regression_cases(
    cases: Sequence[CuratedCase],
    *,
    baseline: str,
    candidate: str,
    executor: Callable[[CuratedCase, str], CaseRunResult],
    max_regressions: int,
    min_pass_rate: float,
    dataset_path: Path | None = None,
    tenant: str = "all",
    run_id: str | None = None,
    now: datetime | None = None,
    baseline_case_results: dict[str, CaseRunResult] | None = None,
    baseline_artifact_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_time = now or _utc_now()
    report_run_id = run_id or _make_run_id(current_time)
    baseline_source = "artifact" if baseline_case_results is not None else "live_executor"

    comparisons: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    new_passes: list[dict[str, Any]] = []

    baseline_passes = 0
    candidate_passes = 0
    baseline_total_cost = 0.0
    candidate_total_cost = 0.0
    baseline_total_latency_ms = 0
    candidate_total_latency_ms = 0
    baseline_refusals = 0
    candidate_refusals = 0
    infrastructure_failures = 0
    skipped_cases = 0

    def _run_executor(case: CuratedCase, target: str) -> CaseRunResult:
        try:
            result = executor(case, target)
        except InfrastructureError as exc:
            return CaseRunResult(
                answer=f"[provider_unavailable] {exc}",
                route="error",
                infrastructure_error=True,
                skip_reason=str(exc) or "infrastructure_error",
            )
        except Exception as exc:
            # Import/pipeline/runtime crashes are infrastructure, not soft skips.
            return CaseRunResult(
                answer=f"[provider_unavailable] executor error: {exc}",
                route="error",
                infrastructure_error=True,
                skip_reason=f"executor_error:{type(exc).__name__}",
            )
        if not isinstance(result, CaseRunResult):
            return CaseRunResult(
                answer="[provider_unavailable] executor returned non-CaseRunResult",
                route="error",
                infrastructure_error=True,
                skip_reason="invalid_executor_result",
            )
        return result

    def _baseline_for(case: CuratedCase) -> CaseRunResult:
        if baseline_case_results is None:
            return _run_executor(case, baseline)
        stored = baseline_case_results.get(case.case_id)
        if stored is None:
            return CaseRunResult(
                answer=(
                    "[provider_unavailable] baseline artifact missing case "
                    f"{case.case_id}"
                ),
                route="error",
                infrastructure_error=True,
                skip_reason="baseline_artifact_missing_case",
            )
        return stored

    for case in cases:
        baseline_result = _baseline_for(case)
        candidate_result = _run_executor(case, candidate)

        baseline_skip = bool(baseline_result.skipped)
        candidate_skip = bool(candidate_result.skipped)
        baseline_infra = bool(baseline_result.infrastructure_error) or _is_infrastructure_failure(
            baseline_result.answer
        )
        candidate_infra = bool(
            candidate_result.infrastructure_error
        ) or _is_infrastructure_failure(candidate_result.answer)

        if baseline_skip or candidate_skip:
            skipped_cases += 1
            case_payload = {
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "query": case.query,
                "baseline": baseline_result.model_dump(mode="json"),
                "candidate": candidate_result.model_dump(mode="json"),
                "baseline_passed": False,
                "candidate_passed": False,
                "baseline_failures": (
                    [f"skipped: {baseline_result.skip_reason or 'unspecified'}"]
                    if baseline_skip
                    else []
                ),
                "candidate_failures": (
                    [f"skipped: {candidate_result.skip_reason or 'unspecified'}"]
                    if candidate_skip
                    else []
                ),
                "diff": _build_diff(baseline_result, candidate_result),
                "outcome": "skipped",
            }
            comparisons.append(case_payload)
            continue

        if baseline_infra or candidate_infra:
            infrastructure_failures += 1
            case_payload = {
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "query": case.query,
                "baseline": baseline_result.model_dump(mode="json"),
                "candidate": candidate_result.model_dump(mode="json"),
                "baseline_passed": False,
                "candidate_passed": False,
                "baseline_failures": ["infrastructure: provider unavailable"] if baseline_infra else [],
                "candidate_failures": ["infrastructure: provider unavailable"] if candidate_infra else [],
                "diff": _build_diff(baseline_result, candidate_result),
                "outcome": "infrastructure_failure",
            }
            comparisons.append(case_payload)
            continue

        baseline_passed, baseline_failures = _evaluate_case_output(baseline_result, case.expected)
        candidate_passed, candidate_failures = _evaluate_case_output(candidate_result, case.expected)

        baseline_passes += int(baseline_passed)
        candidate_passes += int(candidate_passed)
        baseline_total_cost += float(baseline_result.cost_usd or 0.0)
        candidate_total_cost += float(candidate_result.cost_usd or 0.0)
        baseline_total_latency_ms += int(baseline_result.duration_ms or 0)
        candidate_total_latency_ms += int(candidate_result.duration_ms or 0)
        baseline_refusals += int(_is_refusal_answer(baseline_result.answer))
        candidate_refusals += int(_is_refusal_answer(candidate_result.answer))

        outcome = "neutral"
        if baseline_passed and not candidate_passed:
            outcome = "regression"
        elif not baseline_passed and candidate_passed:
            outcome = "new_pass"

        case_payload = {
            "case_id": case.case_id,
            "tenant_id": case.tenant_id,
            "query": case.query,
            "baseline": baseline_result.model_dump(mode="json"),
            "candidate": candidate_result.model_dump(mode="json"),
            "baseline_passed": baseline_passed,
            "candidate_passed": candidate_passed,
            "baseline_failures": baseline_failures,
            "candidate_failures": candidate_failures,
            "diff": _build_diff(baseline_result, candidate_result),
            "outcome": outcome,
        }
        comparisons.append(case_payload)

        if outcome == "regression":
            regressions.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "baseline_answer": baseline_result.answer,
                    "candidate_answer": candidate_result.answer,
                    "why_failed": candidate_failures,
                }
            )
        elif outcome == "new_pass":
            new_passes.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "baseline_answer": baseline_result.answer,
                    "candidate_answer": candidate_result.answer,
                    "why_passed": ["candidate satisfies acceptance"] if candidate_passed else [],
                }
            )

    total_cases = len(comparisons)
    effective_total_cases = total_cases - infrastructure_failures - skipped_cases
    # Fail-closed rates: never invent 1.0 when nothing was effectively evaluated.
    if effective_total_cases > 0:
        baseline_pass_rate = baseline_passes / effective_total_cases
        candidate_pass_rate = candidate_passes / effective_total_cases
    else:
        baseline_pass_rate = 0.0
        candidate_pass_rate = 0.0
    neutral_count = (
        total_cases
        - len(regressions)
        - len(new_passes)
        - infrastructure_failures
        - skipped_cases
    )

    gate = decide_regression_gate(
        total_cases=total_cases,
        effective_cases=effective_total_cases,
        infrastructure_failures=infrastructure_failures,
        skipped_cases=skipped_cases,
        regressions=len(regressions),
        max_regressions=max_regressions,
        baseline_pass_rate=baseline_pass_rate,
        candidate_pass_rate=candidate_pass_rate,
        min_pass_rate=min_pass_rate,
    )
    gate_passed = bool(gate["passed"])
    exit_code = 0 if gate_passed else 1

    report: dict[str, Any] = {
        "run_id": report_run_id,
        "created_at": current_time.isoformat(),
        "baseline": baseline,
        "candidate": candidate,
        "dataset": str(dataset_path) if dataset_path is not None else None,
        "tenant": tenant,
        "baseline_source": baseline_source,
        "aggregate": {
            "total_cases": total_cases,
            "effective_cases": effective_total_cases,
            "infrastructure_failures": infrastructure_failures,
            "skipped_cases": skipped_cases,
            "baseline_pass_rate": round(baseline_pass_rate, 4),
            "candidate_pass_rate": round(candidate_pass_rate, 4),
            "regressions": len(regressions),
            "new_passes": len(new_passes),
            "neutral": neutral_count,
            "baseline_total_cost_usd": round(baseline_total_cost, 6),
            "candidate_total_cost_usd": round(candidate_total_cost, 6),
            "baseline_avg_latency_ms": round(baseline_total_latency_ms / effective_total_cases, 2) if effective_total_cases else 0.0,
            "candidate_avg_latency_ms": round(candidate_total_latency_ms / effective_total_cases, 2) if effective_total_cases else 0.0,
            "baseline_refusal_rate": round(baseline_refusals / effective_total_cases, 4) if effective_total_cases else 0.0,
            "candidate_refusal_rate": round(candidate_refusals / effective_total_cases, 4) if effective_total_cases else 0.0,
        },
        "gate": {
            "passed": gate_passed,
            "metrics_passed": gate_passed,
            "verdict": gate["verdict"],
            "max_regressions": max_regressions,
            "min_pass_rate": min_pass_rate,
            "reasons": list(gate["reasons"]),
            "graceful_skip_pass_forbidden": True,
        },
        "cases": comparisons,
        "regressions": regressions,
        "new_passes": new_passes,
        "exit_code": exit_code,
    }
    if baseline_artifact_meta is not None:
        report["baseline_artifact"] = baseline_artifact_meta
    return report


def _render_summary_table(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    gate = report["gate"]
    return "\n".join(
        [
            "| Metric | Value |",
            "| --- | --- |",
            f"| Baseline | `{report['baseline']}` |",
            f"| Candidate | `{report['candidate']}` |",
            f"| Baseline pass rate | {aggregate['baseline_pass_rate']:.2%} |",
            f"| Candidate pass rate | {aggregate['candidate_pass_rate']:.2%} |",
            f"| Regressions | {aggregate['regressions']} |",
            f"| New passes | {aggregate['new_passes']} |",
            f"| Neutral | {aggregate['neutral']} |",
            f"| Baseline avg latency | {aggregate['baseline_avg_latency_ms']} ms |",
            f"| Candidate avg latency | {aggregate['candidate_avg_latency_ms']} ms |",
            f"| Baseline total cost | ${aggregate['baseline_total_cost_usd']:.6f} |",
            f"| Candidate total cost | ${aggregate['candidate_total_cost_usd']:.6f} |",
            f"| Baseline refusal rate | {aggregate['baseline_refusal_rate']:.2%} |",
            f"| Candidate refusal rate | {aggregate['candidate_refusal_rate']:.2%} |",
            f"| Gate verdict | {gate.get('verdict') or ('PASS' if gate.get('passed') else 'FAIL')} |",
            f"| Metrics passed | {gate.get('metrics_passed', gate.get('passed'))} |",
            f"| Evidence valid | {gate.get('evidence_valid', True)} |",
            f"| Release passed | {gate.get('release_passed', gate.get('passed'))} |",
        ]
    )


def _render_case_list(title: str, entries: list[dict[str, Any]], failure_key: str) -> list[str]:
    lines = [f"## {title}", ""]
    if not entries:
        lines.append("None.")
        return lines

    for entry in entries:
        lines.extend(
            [
                f"### {entry['case_id']}",
                f"- Query: {entry['query']}",
                f"- Baseline answer: {entry['baseline_answer']}",
                f"- Candidate answer: {entry['candidate_answer']}",
                f"- Detail: {'; '.join(entry[failure_key]) if entry[failure_key] else 'n/a'}",
                "",
            ]
        )
    return lines


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Regression Eval — {report['baseline']} vs {report['candidate']}",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Created at: `{report['created_at']}`",
        f"- Dataset: `{report['dataset'] or 'n/a'}`",
        f"- Tenant: `{report['tenant']}`",
        f"- Mode: `{report.get('mode', 'experiment-regression')}`",
        "",
        "## Summary",
        "",
        _render_summary_table(report),
        "",
    ]

    if report["gate"]["reasons"]:
        lines.extend(
            [
                "## Gate Reasons",
                "",
                *[f"- {reason}" for reason in report["gate"]["reasons"]],
                "",
            ]
        )

    lines.extend(_render_case_list("Regressions", report["regressions"], "why_failed"))
    lines.append("")
    lines.extend(_render_case_list("New Passes", report["new_passes"], "why_passed"))
    lines.append("")
    lines.extend(
        [
            "## Aggregate Metrics",
            "",
            f"- Total cases: {report['aggregate']['total_cases']}",
            f"- Baseline pass rate: {report['aggregate']['baseline_pass_rate']:.2%}",
            f"- Candidate pass rate: {report['aggregate']['candidate_pass_rate']:.2%}",
            f"- Baseline avg latency: {report['aggregate']['baseline_avg_latency_ms']} ms",
            f"- Candidate avg latency: {report['aggregate']['candidate_avg_latency_ms']} ms",
            f"- Baseline total cost: ${report['aggregate']['baseline_total_cost_usd']:.6f}",
            f"- Candidate total cost: ${report['aggregate']['candidate_total_cost_usd']:.6f}",
            f"- Baseline refusal rate: {report['aggregate']['baseline_refusal_rate']:.2%}",
            f"- Candidate refusal rate: {report['aggregate']['candidate_refusal_rate']:.2%}",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_report_files(
    report: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path, Path]:
    created_at = datetime.fromisoformat(report["created_at"])
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{timestamp}-{_slug(report['baseline'])}-vs-{_slug(report['candidate'])}"
    target_dir = project_root / "reports" / "regression"
    target_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = target_dir / f"{base_name}.md"
    json_path = target_dir / f"{base_name}.json"

    markdown_path.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return markdown_path, json_path


async def persist_regression_result(
    *,
    session_factory: Any,
    report: dict[str, Any],
    report_path: Path,
) -> None:
    from db.models import EvalResult

    aggregate = report["aggregate"]
    async with session_factory() as session:
        session.add(
            EvalResult(
                metric_name="regression_candidate_pass_rate",
                value=float(aggregate["candidate_pass_rate"]),
                sample_size=int(aggregate["total_cases"]),
                drift_alert=not bool(report["gate"]["passed"]),
                kind="regression",
                run_id=str(report["run_id"]),
                baseline_experiment_id=str(report["baseline"]),
                candidate_experiment_id=str(report["candidate"]),
                report_path=report_path.as_posix(),
            )
        )
        await session.commit()


def _reset_settings_cache() -> None:
    import config.settings as settings_module

    settings_module._settings = None


@contextmanager
def _force_ollama_temperature_zero():
    patches: list[tuple[Any, str, Any]] = []

    def _patch_constructor(module: Any, attr: str) -> None:
        original = getattr(module, attr, None)
        if not isinstance(original, type):
            return

        class _DeterministicOllama(original):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                kwargs.setdefault("temperature", 0)
                super().__init__(*args, **kwargs)

        setattr(module, attr, _DeterministicOllama)
        patches.append((module, attr, original))

    try:
        import langchain_ollama as modern_ollama_module  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        _patch_constructor(modern_ollama_module, "OllamaLLM")

    try:
        import langchain_community.llms as llm_module
        from langchain_community.llms import ollama as ollama_module
    except ImportError:
        pass
    else:
        _patch_constructor(llm_module, "Ollama")
        _patch_constructor(ollama_module, "Ollama")

    try:
        yield
    finally:
        for module, attr, original in reversed(patches):
            setattr(module, attr, original)


@contextmanager
def _experiment_runtime(
    experiment_id: str,
    *,
    project_root: Path = PROJECT_ROOT,
):
    import yaml

    import agent.prompt_registry as prompt_registry
    import config.settings as settings_module

    original_env = os.getenv("EXPERIMENT_ID")
    original_settings_path = settings_module.EXPERIMENT_OVERRIDE_PATH
    original_prompt_path = prompt_registry.EXPERIMENT_OVERRIDE_PATH
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        if experiment_id == "current":
            os.environ.pop("EXPERIMENT_ID", None)
            _reset_settings_cache()
            yield None
            return

        experiment_path = project_root / "evaluation" / "experiments" / f"{experiment_id}.yaml"
        if not experiment_path.exists():
            raise FileNotFoundError(f"experiment not found: {experiment_id}")

        payload = yaml.safe_load(experiment_path.read_text(encoding="utf-8")) or {}
        override_payload = {
            "experiment_id": experiment_id,
            "prompt_overrides": payload.get("prompt_overrides") or {},
            "settings_overrides": payload.get("settings_overrides") or {},
        }

        temp_dir = tempfile.TemporaryDirectory()
        override_path = Path(temp_dir.name) / "experiment_override.yaml"
        override_path.write_text(
            yaml.safe_dump(override_payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
            newline="\n",
        )

        os.environ["EXPERIMENT_ID"] = experiment_id
        settings_module.EXPERIMENT_OVERRIDE_PATH = override_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = override_path
        _reset_settings_cache()
        yield payload
    finally:
        if original_env is None:
            os.environ.pop("EXPERIMENT_ID", None)
        else:
            os.environ["EXPERIMENT_ID"] = original_env
        settings_module.EXPERIMENT_OVERRIDE_PATH = original_settings_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = original_prompt_path
        _reset_settings_cache()
        if temp_dir is not None:
            temp_dir.cleanup()


@contextmanager
def _provider_target_runtime(
    target: str,
    *,
    project_root: Path = PROJECT_ROOT,
):
    import yaml

    import agent.prompt_registry as prompt_registry
    import config.settings as settings_module
    from config.provider_schema import load_provider_registry

    current_settings = settings_module.get_settings()
    registry_path = Path(getattr(current_settings, "provider_registry_path", PROJECT_ROOT / "config" / "providers.yml"))
    resolution = _resolve_provider_target(target, registry_path)
    if resolution is None:
        raise FileNotFoundError(f"provider target not found: {target}")

    registry = load_provider_registry(registry_path)
    payload = registry.model_dump(mode="python")
    if resolution.get("kind") == "profile":
        profile_name = resolution["profile_name"]
    else:
        profile_name = f"benchmark-{_slug(target)}"
        payload["routing_profiles"][profile_name] = {
            "description": f"Benchmark runtime profile for {target}",
            "fast": {"provider": resolution["provider_id"], "model": resolution["model_name"]},
            "strong": {"provider": resolution["provider_id"], "model": resolution["model_name"]},
        }

    original_env = os.getenv("EXPERIMENT_ID")
    original_settings_path = settings_module.EXPERIMENT_OVERRIDE_PATH
    original_prompt_path = prompt_registry.EXPERIMENT_OVERRIDE_PATH
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        temp_dir = tempfile.TemporaryDirectory()
        temp_registry_path = Path(temp_dir.name) / "providers.yml"
        temp_registry_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
            newline="\n",
        )
        override_path = Path(temp_dir.name) / "experiment_override.yaml"
        override_path.write_text(
            yaml.safe_dump(
                {
                    "experiment_id": profile_name,
                    "prompt_overrides": {},
                    "settings_overrides": {
                        "llm_provider_profile": profile_name,
                        "provider_registry_path": str(temp_registry_path),
                    },
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
            newline="\n",
        )
        os.environ["EXPERIMENT_ID"] = profile_name
        settings_module.EXPERIMENT_OVERRIDE_PATH = override_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = override_path
        _reset_settings_cache()
        yield resolution
    finally:
        if original_env is None:
            os.environ.pop("EXPERIMENT_ID", None)
        else:
            os.environ["EXPERIMENT_ID"] = original_env
        settings_module.EXPERIMENT_OVERRIDE_PATH = original_settings_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = original_prompt_path
        _reset_settings_cache()
        if temp_dir is not None:
            temp_dir.cleanup()


def _resolve_retriever(tenant_id: str) -> Any:
    import api.app as api_app

    api_app.initialize_vector_store()

    if api_app._vector_store is not None and api_app._get_retriever is not None:
        retriever_params = inspect.signature(api_app._get_retriever).parameters
        kwargs: dict[str, Any] = {"chunks": api_app._chunks or None}
        if "tenant_id" in retriever_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in retriever_params.values()
        ):
            kwargs["tenant_id"] = tenant_id
        return api_app._get_retriever(api_app._vector_store, **kwargs)

    if api_app._retriever is not None:
        return api_app._retriever

    raise InfrastructureError("vector store is not initialized")


def _read_trace_metrics(trace_id: str) -> dict[str, Any]:
    from config.settings import get_settings

    details = {
        "duration_ms": None,
        "cost_usd": None,
    }

    db_path = Path(getattr(get_settings(), "tracing_db_path", ""))
    if not db_path.exists():
        return details

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT state_json, cost_usd
            FROM trace_steps
            WHERE trace_id = ?
            ORDER BY step_order ASC, id ASC
            """,
            (trace_id,),
        )
        for state_json, cost_usd in cur.fetchall():
            state: dict[str, Any] = {}
            if state_json:
                try:
                    state = json.loads(state_json)
                except (TypeError, ValueError, json.JSONDecodeError):
                    state = {}
            raw_duration = state.get("duration_ms")
            try:
                duration_ms = int(float(raw_duration)) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current = details["duration_ms"]
                details["duration_ms"] = duration_ms if current is None else max(current, duration_ms)
            if cost_usd is not None:
                details["cost_usd"] = float(cost_usd)

    return details


def _normalize_result(payload: dict[str, Any]) -> CaseRunResult:
    trace_id = str(payload.get("trace_id") or "")
    trace_metrics = _read_trace_metrics(trace_id) if trace_id else {"duration_ms": None, "cost_usd": None}

    citations = payload.get("citations") or []
    if not citations:
        docs = payload.get("graded_docs") or payload.get("context_docs") or []
        citations = []
        for index, doc in enumerate(docs, start=1):
            if not isinstance(doc, dict):
                continue
            metadata = doc.get("metadata", {}) or {}
            citations.append(
                {
                    "index": index,
                    "doc_id": str(
                        metadata.get("doc_id")
                        or metadata.get("id")
                        or metadata.get("source")
                        or f"doc_{index}"
                    ),
                    "title": str(
                        metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("doc_id")
                        or f"doc_{index}"
                    ),
                    "excerpt": str(doc.get("page_content") or "")[:300],
                }
            )

    return CaseRunResult(
        answer=str(payload.get("answer") or ""),
        quality_score=float(payload.get("quality_score") or 0.0),
        factuality_score=float(payload.get("factuality_score") or 0.0),
        citations=[item for item in citations if isinstance(item, dict)],
        duration_ms=trace_metrics["duration_ms"],
        cost_usd=trace_metrics["cost_usd"],
        route=str(payload.get("route") or "unknown"),
        trace_id=trace_id,
    )


def _with_wall_clock_duration(result: CaseRunResult, started_at: float) -> CaseRunResult:
    if result.duration_ms is not None:
        return result
    elapsed_ms = int(max((time.perf_counter() - started_at) * 1000, 0))
    return result.model_copy(update={"duration_ms": elapsed_ms})


def execute_case_with_runtime(
    case: CuratedCase,
    experiment_id: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> CaseRunResult:
    from agent.graph import run_qa_pipeline
    from config.settings import get_settings

    with _experiment_runtime(experiment_id, project_root=project_root), _force_ollama_temperature_zero():
        started_at = time.perf_counter()
        retriever = _resolve_retriever(case.tenant_id)
        result = run_qa_pipeline(
            question=case.query,
            retriever=retriever,
            llm=None,
            max_iterations=int(getattr(get_settings(), "self_rag_max_iterations", 2)),
            trace_id=f"regression-{uuid.uuid4()}",
            tenant_id=case.tenant_id,
        )
    return _with_wall_clock_duration(_normalize_result(result), started_at)


def execute_case_with_provider_target(
    case: CuratedCase,
    target: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> CaseRunResult:
    from agent.graph import run_qa_pipeline
    from config.settings import get_settings

    with _provider_target_runtime(target, project_root=project_root), _force_ollama_temperature_zero():
        started_at = time.perf_counter()
        retriever = _resolve_retriever(case.tenant_id)
        result = run_qa_pipeline(
            question=case.query,
            retriever=retriever,
            llm=None,
            max_iterations=int(getattr(get_settings(), "self_rag_max_iterations", 2)),
            trace_id=f"provider-benchmark-{uuid.uuid4()}",
            tenant_id=case.tenant_id,
        )
    return _with_wall_clock_duration(_normalize_result(result), started_at)


def run_regression(
    *,
    baseline: str,
    candidate: str,
    dataset_path: Path,
    tenant: str = "all",
    max_cases: int | None = None,
    seed: int = 42,
    allow_paid_apis: bool | None = None,
    mock_experiment_runtime: bool = False,
    release_gate: bool = False,
    max_regressions: int | None = None,
    min_pass_rate: float | None = None,
    project_root: Path = PROJECT_ROOT,
    executor: Callable[[CuratedCase, str], CaseRunResult] | None = None,
    now: datetime | None = None,
    baseline_artifact: Path | str | None = None,
    require_baseline_artifact: bool = False,
) -> dict[str, Any]:
    from config.settings import get_settings

    settings = get_settings()
    gate_max_regressions = (
        int(max_regressions)
        if max_regressions is not None
        else int(getattr(settings, "regression_gate_max_regressions", 2))
    )
    gate_min_pass_rate = (
        float(min_pass_rate)
        if min_pass_rate is not None
        else float(getattr(settings, "regression_gate_min_pass_rate", 0.85))
    )
    benchmark_allow_paid_apis = (
        bool(allow_paid_apis)
        if allow_paid_apis is not None
        else bool(getattr(settings, "llm_benchmark_allow_paid_apis", False))
    )
    provider_registry_path = Path(getattr(settings, "provider_registry_path", PROJECT_ROOT / "config" / "providers.yml"))
    baseline_provider_target = _resolve_provider_target(baseline, provider_registry_path)
    candidate_provider_target = _resolve_provider_target(candidate, provider_registry_path)

    baseline_case_results: dict[str, CaseRunResult] | None = None
    baseline_artifact_meta: dict[str, Any] | None = None
    artifact_path = Path(baseline_artifact) if baseline_artifact else None

    if require_baseline_artifact and artifact_path is None:
        return _empty_baseline_required_report(
            baseline=baseline,
            candidate=candidate,
            dataset_path=dataset_path,
            release_gate=release_gate,
            reason=(
                "baseline artifact required but --baseline-artifact was not provided "
                "(plan §7.3 merge-base baseline)"
            ),
            now=now,
        )

    if artifact_path is not None:
        try:
            loaded = load_baseline_artifact(artifact_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if require_baseline_artifact or release_gate:
                return _empty_baseline_required_report(
                    baseline=baseline,
                    candidate=candidate,
                    dataset_path=dataset_path,
                    release_gate=release_gate,
                    reason=f"baseline artifact unusable: {exc}",
                    now=now,
                )
            raise
        baseline_case_results = loaded["case_map"]
        baseline_artifact_meta = {
            "path": loaded.get("path"),
            "git_sha": loaded.get("git_sha"),
            "merge_base": loaded.get("merge_base"),
            "baseline_label": loaded.get("baseline_label"),
            "schema_version": loaded.get("schema_version"),
            "case_count": len(baseline_case_results),
        }

    cases = load_curated_cases(dataset_path)
    if tenant != "all":
        cases = [case for case in cases if case.tenant_id == tenant]
    cases = sample_cases(cases, max_cases=max_cases, seed=seed)

    if executor is None:
        def _selected_executor(case: CuratedCase, target: str) -> CaseRunResult:
            provider_target = _resolve_provider_target(target, provider_registry_path)
            if provider_target is None:
                if mock_experiment_runtime:
                    return _build_mock_provider_result(
                        case,
                        target,
                        {
                            "provider_id": "experiment",
                            "model_name": target,
                            "input_price_per_1m_tokens": 0.0,
                            "output_price_per_1m_tokens": 0.0,
                        },
                        trace_prefix="mock-experiment",
                    )
                return execute_case_with_runtime(
                    case,
                    target,
                    project_root=project_root,
                )
            if not benchmark_allow_paid_apis:
                return _build_mock_provider_result(case, target, provider_target)
            return execute_case_with_provider_target(
                case,
                target,
                project_root=project_root,
            )

        selected_executor = _selected_executor
    else:
        selected_executor = executor

    report = run_regression_cases(
        cases,
        baseline=baseline,
        candidate=candidate,
        executor=selected_executor,
        max_regressions=gate_max_regressions,
        min_pass_rate=gate_min_pass_rate,
        dataset_path=dataset_path,
        tenant=tenant,
        now=now,
        baseline_case_results=baseline_case_results,
        baseline_artifact_meta=baseline_artifact_meta,
    )
    if baseline_provider_target or candidate_provider_target:
        report["mode"] = (
            "live-provider-benchmark" if benchmark_allow_paid_apis else "mock-provider-benchmark"
        )
    elif mock_experiment_runtime:
        report["mode"] = "mock-experiment-regression"
    else:
        report["mode"] = "experiment-regression"
    # Plan §7.1–7.2: mock is never release evidence; finalize verdict/exit.
    report["evidence_valid"] = report["mode"] not in MOCK_EVIDENCE_MODES
    report.setdefault("gate", {})
    report["gate"]["metrics_passed"] = bool(report["gate"].get("passed"))
    return apply_evidence_policy(report, release_gate=release_gate)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    baseline_group = parser.add_mutually_exclusive_group(required=True)
    baseline_group.add_argument("--baseline", help="Model name or alias for baseline.")
    baseline_group.add_argument(
        "--baseline-profile",
        help="Routing profile name from config/providers.yml (alternative to --baseline).",
    )

    candidate_group = parser.add_mutually_exclusive_group(required=True)
    candidate_group.add_argument("--candidate", help="Model name or alias for candidate.")
    candidate_group.add_argument(
        "--candidate-profile",
        help="Routing profile name from config/providers.yml (alternative to --candidate).",
    )

    parser.add_argument(
        "--dataset",
        default=str(PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"),
    )
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-paid-apis", action="store_true")
    parser.add_argument("--mock-experiment-runtime", action="store_true")
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help=(
            "Require release evidence: mock expected-copy cannot PASS. "
            "Exit non-zero when evidence_valid is false even if smoke metrics are green."
        ),
    )
    parser.add_argument(
        "--baseline-artifact",
        default=None,
        help=(
            "Path to merge-base baseline artifact JSON (plan §7.3). "
            "When set, baseline case answers are loaded from the artifact "
            "instead of re-executing the baseline target."
        ),
    )
    parser.add_argument(
        "--write-baseline-artifact",
        default=None,
        help=(
            "After a successful run, write a baseline artifact from this run's "
            "baseline-side case results (for later merge-base compare)."
        ),
    )
    parser.add_argument(
        "--require-baseline-artifact",
        action="store_true",
        help=(
            "Fail closed when --baseline-artifact is missing or unusable "
            "(release-honest merge-base compare)."
        ),
    )
    parser.add_argument("--no-persist", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    from monitoring.prometheus import (
        record_regression_run,
        set_regression_last_pass_rate,
    )

    args = parse_args(argv)
    baseline_target = args.baseline or args.baseline_profile
    candidate_target = args.candidate or args.candidate_profile
    started_at = _utc_now()
    try:
        report = run_regression(
            baseline=baseline_target,
            candidate=candidate_target,
            dataset_path=Path(args.dataset),
            tenant=args.tenant,
            max_cases=args.max_cases,
            seed=args.seed,
            allow_paid_apis=args.allow_paid_apis,
            mock_experiment_runtime=args.mock_experiment_runtime,
            release_gate=bool(getattr(args, "release_gate", False)),
            baseline_artifact=getattr(args, "baseline_artifact", None),
            require_baseline_artifact=bool(
                getattr(args, "require_baseline_artifact", False)
            ),
        )
        markdown_path, json_path = write_report_files(report)

        write_path = getattr(args, "write_baseline_artifact", None)
        if write_path and report.get("cases"):
            merge_base = resolve_git_merge_base(PROJECT_ROOT) or resolve_git_rev(
                PROJECT_ROOT, "HEAD"
            )
            head_sha = resolve_git_rev(PROJECT_ROOT, "HEAD")
            artifact = baseline_artifact_from_report(
                report,
                git_sha=head_sha,
                merge_base=merge_base,
            )
            written = write_baseline_artifact(artifact, Path(write_path))
            report["wrote_baseline_artifact"] = str(written)

        if not args.no_persist:
            from db.engine import async_session, engine

            # Dispose async engine pool before creating a new event loop to avoid
            # asyncpg "another operation is in progress" race when run_qa_pipeline
            # already used asyncio.run internally.
            engine.dispose(close=True)

            asyncio.run(
                persist_regression_result(
                    session_factory=async_session,
                    report=report,
                    report_path=json_path.relative_to(PROJECT_ROOT),
                )
            )

        duration_sec = max((_utc_now() - started_at).total_seconds(), 0.0)
        # Prometheus: smoke metrics vs release — label fail when not release-passed.
        metrics_ok = bool(report.get("gate", {}).get("metrics_passed", report["gate"].get("passed")))
        release_ok = bool(report.get("gate", {}).get("release_passed", False))
        if getattr(args, "release_gate", False):
            record_label = "pass" if release_ok else "fail"
        else:
            record_label = "pass" if metrics_ok else "fail"
        record_regression_run(record_label, duration_sec)
        set_regression_last_pass_rate(
            report["baseline"],
            report["candidate"],
            float(report["aggregate"]["candidate_pass_rate"]),
        )

        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "exit_code": report["exit_code"],
                    "report_markdown": str(markdown_path.relative_to(PROJECT_ROOT)),
                    "report_json": str(json_path.relative_to(PROJECT_ROOT)),
                    "aggregate": report["aggregate"],
                    "gate": report["gate"],
                },
                ensure_ascii=False,
            )
        )
        return int(report["exit_code"])
    except Exception as exc:
        duration_sec = max((_utc_now() - started_at).total_seconds(), 0.0)
        record_regression_run("fail", duration_sec)
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

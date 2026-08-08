"""Plan §7.4: versioned curated dataset slices + context_recall threshold."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.regression_eval import (
    REQUIRED_DATASET_SLICES,
    CaseExpectation,
    CaseRunResult,
    CuratedCase,
    _evaluate_case_output,
    load_curated_cases,
    validate_dataset_slice_coverage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
MANIFEST = PROJECT_ROOT / "evaluation" / "curated_cases.manifest.json"


def test_required_slices_constant_matches_plan() -> None:
    assert "multi_tenant" in REQUIRED_DATASET_SLICES
    assert "context_recall" in REQUIRED_DATASET_SLICES
    assert "durable_escalation" in REQUIRED_DATASET_SLICES
    assert len(REQUIRED_DATASET_SLICES) >= 10


def test_manifest_lists_required_slices() -> None:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert set(raw["required_slices"]) == set(REQUIRED_DATASET_SLICES)
    assert raw["dataset"] == "curated_cases.jsonl"
    assert raw["min_cases_per_slice"] >= 1


def test_curated_dataset_loads_and_covers_required_slices() -> None:
    cases = load_curated_cases(DATASET)
    assert len(cases) >= 45
    report = validate_dataset_slice_coverage(cases)
    assert report["ok"] is True, report["reasons"]
    assert report["missing_slices"] == []
    for name in REQUIRED_DATASET_SLICES:
        assert report["slice_counts"][name] >= 1


def test_multi_tenant_and_multi_turn_structure() -> None:
    cases = load_curated_cases(DATASET)
    mt = [c for c in cases if "multi_tenant" in c.slices]
    tenants = {c.tenant_id for c in mt}
    assert len(tenants) >= 2

    turns = [c for c in cases if "multi_turn" in c.slices]
    by_session: dict[str, list[CuratedCase]] = {}
    for case in turns:
        assert case.session_id
        by_session.setdefault(case.session_id, []).append(case)
    assert any(len(group) >= 2 for group in by_session.values())


def test_validate_dataset_reports_missing_slice() -> None:
    cases = [
        CuratedCase(
            case_id="only-pii",
            tenant_id="default",
            query="q",
            slices=["pii"],
            expected=CaseExpectation(),
        )
    ]
    report = validate_dataset_slice_coverage(cases)
    assert report["ok"] is False
    assert "multi_tenant" in report["missing_slices"]


def test_context_recall_threshold_in_evaluate() -> None:
    expected = CaseExpectation(min_context_recall=0.5, answer_contains=["ok"])
    ok, failures = _evaluate_case_output(
        CaseRunResult(answer="ok", context_recall=0.9, quality_score=80, route="auto"),
        expected,
    )
    assert ok is True
    assert failures == []

    bad, failures_bad = _evaluate_case_output(
        CaseRunResult(answer="ok", context_recall=0.1, quality_score=80, route="auto"),
        expected,
    )
    assert bad is False
    assert any("context_recall" in item for item in failures_bad)

    missing, failures_missing = _evaluate_case_output(
        CaseRunResult(answer="ok", context_recall=None, quality_score=80, route="auto"),
        expected,
    )
    assert missing is False
    assert any("context_recall" in item for item in failures_missing)


def test_case_schema_accepts_slices_session_and_recall() -> None:
    case = CuratedCase.model_validate(
        {
            "case_id": "x",
            "tenant_id": "acme",
            "query": "q",
            "slices": ["multi_tenant"],
            "session_id": "s1",
            "turn_index": 1,
            "expected": {"min_context_recall": 0.6, "citations_min_count": 1},
        }
    )
    assert case.slices == ["multi_tenant"]
    assert case.session_id == "s1"
    assert case.expected.min_context_recall == 0.6

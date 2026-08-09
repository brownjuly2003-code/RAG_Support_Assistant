"""Plan §5.7: release-honest canonical quality metrics in regression sidecars."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import regression_eval
from scripts.live_quality_metrics_gate import _extract_validated_run_metrics


def _case(case_id: str, expected_term: str = "alpha") -> regression_eval.CuratedCase:
    return regression_eval.CuratedCase(
        case_id=case_id,
        tenant_id="tenant-a",
        query=f"How does {expected_term} work?",
        expected=regression_eval.CaseExpectation(
            answer_contains=[expected_term],
            min_quality=0,
        ),
    )


def _measured_result(
    *,
    precision: float,
    recall: float,
    faithfulness: float,
    relevancy: float,
    coverage: str,
    grounding_status: str = "verified",
) -> regression_eval.CaseRunResult:
    return regression_eval.CaseRunResult(
        answer="alpha works",
        quality_score=99,
        factuality_score=98,
        route="auto",
        grounding_status=grounding_status,
        context_precision=precision,
        context_recall=recall,
        faithfulness=faithfulness,
        answer_relevancy=relevancy,
        keyword_coverage_status=coverage,
    )


def test_normalize_result_measures_context_metrics_without_score_substitution() -> None:
    case = regression_eval.CuratedCase(
        case_id="router-reset",
        tenant_id="tenant-a",
        query="How do I reset the router?",
        expected=regression_eval.CaseExpectation(
            answer_contains=["reset", "button"],
        ),
    )

    result = regression_eval._normalize_result(
        {
            "answer": "Reset the router with the button.",
            "quality_score": 17,
            "factuality_score": 23,
            "route": "auto",
            "grounding_status": "verified",
            "graded_docs": [
                {"page_content": "Use the reset button on the router."},
                {"page_content": "Unrelated shipping note."},
            ],
        },
        case=case,
    )

    assert result.context_precision == pytest.approx(0.5333)
    assert result.context_recall == pytest.approx(1.0)
    assert result.faithfulness == pytest.approx(1.0)
    assert result.answer_relevancy == pytest.approx(0.75)
    assert result.keyword_coverage_status == "FULL"
    assert result.grounding_status == "verified"
    assert result.context_precision != pytest.approx(result.quality_score / 100)
    assert result.faithfulness != pytest.approx(result.factuality_score / 100)


def test_normalize_result_does_not_restore_rejected_context_for_metrics() -> None:
    case = _case("all-rejected", expected_term="alpha")

    result = regression_eval._normalize_result(
        {
            "answer": "alpha works",
            "route": "human",
            "grounding_status": "not_verified",
            "graded_docs": [],
            "doc_grade_reason": "Kept 0/1, filtered 1, all_docs_rejected",
            "doc_grade_outcome": "all_rejected",
            "context_docs": [{"page_content": "alpha is present only before grading"}],
        },
        case=case,
    )

    assert result.context_precision == 0.0
    assert result.context_recall == 0.0
    assert result.faithfulness == 0.0
    assert result.keyword_coverage_status == "MISS"


def test_normalize_result_uses_context_when_simple_path_skips_grader() -> None:
    case = _case("simple-path", expected_term="alpha")

    result = regression_eval._normalize_result(
        {
            "answer": "alpha works",
            "route": "human",
            "grounding_status": "not_verified",
            "graded_docs": [],
            "doc_grade_reason": None,
            "context_docs": [{"page_content": "alpha works from this context"}],
        },
        case=case,
    )

    assert result.context_recall == 1.0
    assert result.faithfulness == 1.0
    assert result.keyword_coverage_status == "FULL"


def test_run_regression_cases_emits_all_seven_candidate_metrics() -> None:
    cases = [_case("full"), _case("miss")]

    candidate_results = {
        "full": _measured_result(
            precision=0.8,
            recall=1.0,
            faithfulness=0.95,
            relevancy=0.9,
            coverage="FULL",
        ),
        "miss": _measured_result(
            precision=0.4,
            recall=0.0,
            faithfulness=0.7,
            relevancy=0.8,
            coverage="MISS",
            grounding_status="not_verified",
        ),
    }

    def executor(
        case: regression_eval.CuratedCase,
        target: str,
    ) -> regression_eval.CaseRunResult:
        if target == "candidate":
            return candidate_results[case.case_id]
        return _measured_result(
            precision=0.5,
            recall=1.0,
            faithfulness=0.9,
            relevancy=0.9,
            coverage="FULL",
        )

    report = regression_eval.run_regression_cases(
        cases,
        baseline="baseline",
        candidate="candidate",
        executor=executor,
        max_regressions=0,
        min_pass_rate=0.0,
    )

    assert report["quality_metrics"] == {
        "context_precision": 0.6,
        "context_recall": 0.5,
        "full_rate": 0.5,
        "miss_count": 1,
        "faithfulness": 0.825,
        "answer_relevancy": 0.85,
        "unverified_auto_rate": 0.5,
    }
    provenance = report["quality_metrics_provenance"]
    assert provenance["complete"] is True
    assert provenance["eligible_cases"] == 2
    assert provenance["measured_cases"] == 2
    assert provenance["coverage_counts"] == {"FULL": 1, "PART": 0, "MISS": 1}
    assert provenance["auto_cases"] == 2
    assert provenance["unverified_auto_cases"] == 1
    assert report["aggregate"]["candidate_pass_rate"] == 1.0
    assert report["quality_metrics"]["context_precision"] != 1.0


def test_real_release_sidecar_is_accepted_by_live_quality_consumer(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","tenant_id":"t","query":"alpha",'
        '"expected":{"answer_contains":["alpha"],"min_quality":0}}\n',
        encoding="utf-8",
    )

    def executor(
        case: regression_eval.CuratedCase,
        target: str,
    ) -> regression_eval.CaseRunResult:
        _ = case, target
        return _measured_result(
            precision=0.7,
            recall=0.98,
            faithfulness=0.95,
            relevancy=0.94,
            coverage="FULL",
        )

    report = regression_eval.run_regression(
        baseline="baseline",
        candidate="candidate",
        dataset_path=dataset,
        executor=executor,
        release_gate=True,
        max_regressions=0,
        min_pass_rate=0.0,
    )

    assert report["evidence_valid"] is True
    assert report["release_passed"] is True
    assert report["gate"]["release_passed"] is True
    assert report["quality_metrics_provenance"]["complete"] is True
    assert _extract_validated_run_metrics(report) == report["quality_metrics"]


def test_real_release_fails_closed_when_candidate_metrics_are_unmeasured(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","tenant_id":"t","query":"alpha",'
        '"expected":{"answer_contains":["alpha"],"min_quality":0}}\n',
        encoding="utf-8",
    )

    def executor(
        case: regression_eval.CuratedCase,
        target: str,
    ) -> regression_eval.CaseRunResult:
        _ = case, target
        return regression_eval.CaseRunResult(
            answer="alpha works",
            quality_score=99,
            factuality_score=99,
            route="auto",
            grounding_status="verified",
        )

    report = regression_eval.run_regression(
        baseline="baseline",
        candidate="candidate",
        dataset_path=dataset,
        executor=executor,
        release_gate=True,
        max_regressions=0,
        min_pass_rate=0.0,
    )

    assert report["quality_metrics_provenance"]["complete"] is False
    assert report["release_passed"] is False
    assert report["gate"]["release_passed"] is False
    assert report["exit_code"] == 1
    assert any(
        "section 5 metric producer incomplete" in reason.lower()
        for reason in report["gate"]["reasons"]
    )

"""Plan §7.1: regression gate fail-closed on skip / infrastructure errors."""

from __future__ import annotations

from scripts.regression_eval import (
    CaseExpectation,
    CaseRunResult,
    CuratedCase,
    decide_regression_gate,
    run_regression_cases,
)


def test_decide_gate_fails_on_infrastructure_even_if_rates_look_fine() -> None:
    gate = decide_regression_gate(
        total_cases=4,
        effective_cases=3,
        infrastructure_failures=1,
        skipped_cases=0,
        regressions=0,
        max_regressions=2,
        baseline_pass_rate=1.0,
        candidate_pass_rate=1.0,
        min_pass_rate=0.5,
    )
    assert gate["passed"] is False
    assert gate["verdict"] == "FAIL"
    assert any("infrastructure" in r for r in gate["reasons"])
    assert "PASSED (graceful skip)" not in gate["verdict"]


def test_decide_gate_fails_on_skipped_cases() -> None:
    gate = decide_regression_gate(
        total_cases=2,
        effective_cases=1,
        infrastructure_failures=0,
        skipped_cases=1,
        regressions=0,
        max_regressions=2,
        baseline_pass_rate=1.0,
        candidate_pass_rate=1.0,
        min_pass_rate=0.5,
    )
    assert gate["passed"] is False
    assert any("skipped" in r for r in gate["reasons"])


def test_decide_gate_fails_when_all_cases_skipped_not_fake_1_0() -> None:
    gate = decide_regression_gate(
        total_cases=3,
        effective_cases=0,
        infrastructure_failures=0,
        skipped_cases=3,
        regressions=0,
        max_regressions=0,
        baseline_pass_rate=0.0,
        candidate_pass_rate=0.0,
        min_pass_rate=0.0,
    )
    assert gate["passed"] is False
    assert gate["verdict"] == "FAIL"
    assert any("no effective cases" in r or "skipped" in r for r in gate["reasons"])


def test_decide_gate_fails_on_empty_run() -> None:
    gate = decide_regression_gate(
        total_cases=0,
        effective_cases=0,
        infrastructure_failures=0,
        skipped_cases=0,
        regressions=0,
        max_regressions=0,
        baseline_pass_rate=1.0,  # must not be trusted
        candidate_pass_rate=1.0,
        min_pass_rate=0.0,
    )
    assert gate["passed"] is False
    assert any("no cases" in r for r in gate["reasons"])


def test_run_regression_infra_failure_exit_nonzero() -> None:
    cases = [
        CuratedCase(
            case_id="ok",
            query="q1",
            expected=CaseExpectation(answer_contains=["hello"], min_quality=50),
        ),
        CuratedCase(
            case_id="infra",
            query="q2",
            expected=CaseExpectation(answer_contains=["x"], min_quality=50),
        ),
    ]

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        if case.case_id == "infra":
            return CaseRunResult(
                answer="[provider_unavailable] down",
                quality_score=100,
                route="auto",
            )
        return CaseRunResult(
            answer="hello world",
            quality_score=90,
            factuality_score=90,
            route="auto",
            citations=[{"doc_id": "d1"}],
        )

    report = run_regression_cases(
        cases,
        baseline="b",
        candidate="c",
        executor=executor,
        max_regressions=5,
        min_pass_rate=0.0,
    )
    assert report["aggregate"]["infrastructure_failures"] == 1
    assert report["aggregate"]["candidate_pass_rate"] != 1.0 or report["exit_code"] == 1
    assert report["gate"]["passed"] is False
    assert report["exit_code"] == 1
    assert report["gate"]["verdict"] == "FAIL"
    assert any("infrastructure" in r for r in report["gate"]["reasons"])


def test_run_regression_skipped_case_exit_nonzero() -> None:
    cases = [
        CuratedCase(
            case_id="skip-me",
            query="q",
            expected=CaseExpectation(answer_contains=["anything"]),
        ),
    ]

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        _ = case, target
        return CaseRunResult(
            answer="",
            skipped=True,
            skip_reason="evaluator import failed",
            quality_score=1.0,  # must not unlock pass
        )

    report = run_regression_cases(
        cases,
        baseline="b",
        candidate="c",
        executor=executor,
        max_regressions=10,
        min_pass_rate=0.0,
    )
    assert report["aggregate"]["skipped_cases"] == 1
    assert report["aggregate"]["effective_cases"] == 0
    assert report["aggregate"]["candidate_pass_rate"] == 0.0
    assert report["gate"]["passed"] is False
    assert report["exit_code"] == 1
    assert report["gate"]["verdict"] != "PASSED (graceful skip)"


def test_run_regression_executor_exception_is_infrastructure() -> None:
    cases = [
        CuratedCase(case_id="boom", query="q", expected=CaseExpectation()),
    ]

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        _ = case, target
        raise RuntimeError("import failed: ragas")

    report = run_regression_cases(
        cases,
        baseline="b",
        candidate="c",
        executor=executor,
        max_regressions=10,
        min_pass_rate=0.0,
    )
    assert report["aggregate"]["infrastructure_failures"] == 1
    assert report["exit_code"] == 1
    assert report["gate"]["passed"] is False

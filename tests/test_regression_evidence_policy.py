"""Plan §7.2: mock expected-copy must not claim release PASS."""

from __future__ import annotations

from pathlib import Path

from scripts.regression_eval import (
    CaseRunResult,
    CuratedCase,
    apply_evidence_policy,
    parse_args,
    run_regression,
)


def test_apply_evidence_policy_mock_metrics_green_is_smoke_not_pass() -> None:
    report = {
        "mode": "mock-experiment-regression",
        "evidence_valid": False,
        "exit_code": 0,
        "gate": {
            "passed": True,
            "metrics_passed": True,
            "verdict": "PASS",
            "reasons": [],
        },
    }
    out = apply_evidence_policy(report, release_gate=False)
    assert out["gate"]["verdict"] == "SMOKE_PASS"
    assert out["gate"]["passed"] is False
    assert out["gate"]["metrics_passed"] is True
    assert out["gate"]["release_passed"] is False
    assert out["gate"]["evidence_valid"] is False
    assert out["exit_code"] == 0  # smoke path keeps metrics exit
    assert out["gate"]["verdict"] != "PASS"


def test_apply_evidence_policy_release_gate_fails_mock_even_when_metrics_green() -> None:
    report = {
        "mode": "mock-experiment-regression",
        "evidence_valid": False,
        "exit_code": 0,
        "gate": {
            "passed": True,
            "metrics_passed": True,
            "verdict": "PASS",
            "reasons": [],
        },
    }
    out = apply_evidence_policy(report, release_gate=True)
    assert out["gate"]["verdict"] == "SMOKE_PASS"
    assert out["gate"]["passed"] is False
    assert out["gate"]["release_passed"] is False
    assert out["exit_code"] == 1


def test_apply_evidence_policy_real_mode_can_pass_release() -> None:
    report = {
        "mode": "experiment-regression",
        "evidence_valid": True,
        "exit_code": 0,
        "gate": {
            "passed": True,
            "metrics_passed": True,
            "verdict": "PASS",
            "reasons": [],
        },
    }
    out = apply_evidence_policy(report, release_gate=True)
    assert out["gate"]["verdict"] == "PASS"
    assert out["gate"]["passed"] is True
    assert out["gate"]["release_passed"] is True
    assert out["exit_code"] == 0


def test_run_regression_mock_never_release_pass(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","tenant_id":"t","query":"reset router",'
        '"expected":{"answer_contains":["reset"],"min_quality":50}}\n',
        encoding="utf-8",
    )

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        _ = target
        return CaseRunResult(
            answer="Please reset the router.",
            quality_score=90,
            factuality_score=90,
            route="auto",
            citations=[{"doc_id": "d1"}],
        )

    report = run_regression(
        baseline="current",
        candidate="current",
        dataset_path=dataset,
        mock_experiment_runtime=True,
        release_gate=False,
        executor=executor,
        max_regressions=5,
        min_pass_rate=0.0,
    )
    assert report["mode"] == "mock-experiment-regression"
    assert report["evidence_valid"] is False
    assert report["gate"]["metrics_passed"] is True
    assert report["gate"]["verdict"] == "SMOKE_PASS"
    assert report["gate"]["passed"] is False
    assert report["gate"]["release_passed"] is False
    assert report["exit_code"] == 0

    release = run_regression(
        baseline="current",
        candidate="current",
        dataset_path=dataset,
        mock_experiment_runtime=True,
        release_gate=True,
        executor=executor,
        max_regressions=5,
        min_pass_rate=0.0,
    )
    assert release["gate"]["verdict"] == "SMOKE_PASS"
    assert release["gate"]["passed"] is False
    assert release["exit_code"] == 1


def test_parse_args_release_gate_flag() -> None:
    args = parse_args(
        [
            "--baseline",
            "current",
            "--candidate",
            "current",
            "--mock-experiment-runtime",
            "--release-gate",
            "--no-persist",
        ]
    )
    assert args.release_gate is True
    assert args.mock_experiment_runtime is True

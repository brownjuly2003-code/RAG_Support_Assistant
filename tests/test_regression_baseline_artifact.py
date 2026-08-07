"""Plan §7.3: merge-base baseline artifact for honest regression compare."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.regression_eval import (
    CaseRunResult,
    CuratedCase,
    baseline_artifact_from_report,
    build_baseline_artifact,
    load_baseline_artifact,
    parse_args,
    run_regression,
    run_regression_cases,
    write_baseline_artifact,
)


def _case(case_id: str, query: str = "q") -> CuratedCase:
    return CuratedCase(
        case_id=case_id,
        tenant_id="t1",
        query=query,
        expected={"answer_contains": ["ok"], "min_quality": 50},
    )


def test_build_load_write_baseline_artifact_roundtrip(tmp_path: Path) -> None:
    cases = {
        "c1": CaseRunResult(
            answer="ok answer",
            quality_score=90,
            factuality_score=88,
            route="auto",
            citations=[{"doc_id": "d1"}],
            duration_ms=12,
            cost_usd=0.01,
        )
    }
    artifact = build_baseline_artifact(
        case_results=cases,
        git_sha="abc123",
        merge_base="abc123",
        dataset_path="evaluation/curated_cases.jsonl",
        baseline_label="merge-base",
        mode="experiment-regression",
    )
    assert artifact["schema_version"] == 1
    assert artifact["kind"] == "regression-baseline"
    assert artifact["git_sha"] == "abc123"
    assert artifact["merge_base"] == "abc123"
    assert "c1" in artifact["cases"]

    path = write_baseline_artifact(artifact, tmp_path / "baseline.json")
    loaded = load_baseline_artifact(path)
    assert loaded["git_sha"] == "abc123"
    mapped = loaded["case_map"]
    assert isinstance(mapped["c1"], CaseRunResult)
    assert mapped["c1"].answer == "ok answer"
    assert mapped["c1"].quality_score == 90


def test_load_baseline_artifact_rejects_bad_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"kind": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="regression-baseline"):
        load_baseline_artifact(path)


def test_load_baseline_artifact_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_baseline_artifact(tmp_path / "missing.json")


def test_run_regression_cases_uses_artifact_baseline_without_reexec() -> None:
    calls: list[tuple[str, str]] = []

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        calls.append((case.case_id, target))
        return CaseRunResult(
            answer="ok candidate",
            quality_score=90,
            factuality_score=90,
            route="auto",
            citations=[{"doc_id": "d1"}],
        )

    baseline_map = {
        "c1": CaseRunResult(
            answer="ok baseline",
            quality_score=90,
            factuality_score=90,
            route="auto",
            citations=[{"doc_id": "d1"}],
        )
    }
    report = run_regression_cases(
        [_case("c1")],
        baseline="artifact:abc",
        candidate="current",
        executor=executor,
        max_regressions=0,
        min_pass_rate=0.0,
        baseline_case_results=baseline_map,
    )
    assert report["baseline_source"] == "artifact"
    assert calls == [("c1", "current")]  # baseline not re-executed
    assert report["cases"][0]["baseline"]["answer"] == "ok baseline"
    assert report["cases"][0]["candidate"]["answer"] == "ok candidate"
    assert report["aggregate"]["effective_cases"] == 1


def test_missing_artifact_case_is_infrastructure_failure() -> None:
    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        return CaseRunResult(
            answer="ok candidate",
            quality_score=90,
            factuality_score=90,
            route="auto",
        )

    report = run_regression_cases(
        [_case("c1"), _case("c2")],
        baseline="artifact",
        candidate="current",
        executor=executor,
        max_regressions=5,
        min_pass_rate=0.0,
        baseline_case_results={
            "c1": CaseRunResult(answer="ok", quality_score=90, route="auto"),
            # c2 missing
        },
    )
    assert report["aggregate"]["infrastructure_failures"] == 1
    assert report["gate"]["passed"] is False
    assert report["gate"]["verdict"] == "FAIL"
    c2 = next(item for item in report["cases"] if item["case_id"] == "c2")
    assert c2["outcome"] == "infrastructure_failure"
    assert "baseline_artifact_missing_case" in c2["baseline"]["skip_reason"]


def test_require_baseline_artifact_fail_closed_without_path(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","tenant_id":"t","query":"q",'
        '"expected":{"answer_contains":["ok"],"min_quality":50}}\n',
        encoding="utf-8",
    )

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        raise AssertionError("executor must not run when artifact required missing")

    report = run_regression(
        baseline="current",
        candidate="current",
        dataset_path=dataset,
        executor=executor,
        require_baseline_artifact=True,
        baseline_artifact=None,
        max_regressions=5,
        min_pass_rate=0.0,
        release_gate=True,
    )
    assert report["gate"]["verdict"] == "FAIL"
    assert report["gate"]["passed"] is False
    assert report["exit_code"] == 1
    reasons = " ".join(report["gate"]["reasons"])
    assert "baseline artifact" in reasons.lower()
    assert report["aggregate"]["total_cases"] == 0


def test_run_regression_with_baseline_artifact_file(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"c1","tenant_id":"t","query":"q",'
        '"expected":{"answer_contains":["ok"],"min_quality":50}}\n',
        encoding="utf-8",
    )
    artifact = build_baseline_artifact(
        case_results={
            "c1": CaseRunResult(
                answer="ok from artifact",
                quality_score=95,
                factuality_score=95,
                route="auto",
                citations=[{"doc_id": "d1"}],
            )
        },
        git_sha="deadbeef",
        merge_base="deadbeef",
        baseline_label="merge-base",
    )
    art_path = write_baseline_artifact(artifact, tmp_path / "mb.json")
    calls: list[str] = []

    def executor(case: CuratedCase, target: str) -> CaseRunResult:
        calls.append(target)
        return CaseRunResult(
            answer="ok from candidate",
            quality_score=90,
            factuality_score=90,
            route="auto",
            citations=[{"doc_id": "d1"}],
        )

    report = run_regression(
        baseline="merge-base",
        candidate="current",
        dataset_path=dataset,
        executor=executor,
        baseline_artifact=art_path,
        max_regressions=5,
        min_pass_rate=0.0,
        release_gate=False,
    )
    assert calls == ["current"]
    assert report["baseline_source"] == "artifact"
    assert report["baseline_artifact"]["git_sha"] == "deadbeef"
    assert report["cases"][0]["baseline"]["answer"] == "ok from artifact"
    assert report["gate"]["metrics_passed"] is True


def test_baseline_artifact_from_report_and_write(tmp_path: Path) -> None:
    report = {
        "baseline": "old",
        "candidate": "new",
        "mode": "experiment-regression",
        "dataset": "evaluation/curated_cases.jsonl",
        "cases": [
            {
                "case_id": "c1",
                "baseline": {
                    "answer": "base ans",
                    "quality_score": 80,
                    "factuality_score": 80,
                    "citations": [],
                    "route": "auto",
                    "duration_ms": 1,
                    "cost_usd": 0.0,
                    "trace_id": "",
                    "skipped": False,
                    "skip_reason": "",
                    "infrastructure_error": False,
                },
            }
        ],
    }
    artifact = baseline_artifact_from_report(
        report,
        git_sha="111",
        merge_base="111",
    )
    path = write_baseline_artifact(artifact, tmp_path / "from-report.json")
    loaded = load_baseline_artifact(path)
    assert loaded["case_map"]["c1"].answer == "base ans"


def test_parse_args_baseline_artifact_flags() -> None:
    args = parse_args(
        [
            "--baseline",
            "current",
            "--candidate",
            "current",
            "--baseline-artifact",
            "reports/baseline.json",
            "--write-baseline-artifact",
            "reports/out-baseline.json",
            "--require-baseline-artifact",
            "--no-persist",
        ]
    )
    assert args.baseline_artifact == "reports/baseline.json"
    assert args.write_baseline_artifact == "reports/out-baseline.json"
    assert args.require_baseline_artifact is True

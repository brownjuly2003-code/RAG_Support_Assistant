from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _write_dataset(path: Path) -> None:
    rows = [
        {
            "case_id": "case-router-reset",
            "tenant_id": "acme",
            "query": "How do I reset the router?",
            "expected": {
                "answer_contains": ["reset"],
                "route": "auto",
                "min_quality": 80,
                "min_factuality": 90,
                "citations_min_count": 1,
            },
        }
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_run_regression_supports_provider_targets_in_mock_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from scripts import regression_eval

    dataset_path = tmp_path / "curated_cases.jsonl"
    _write_dataset(dataset_path)

    def _fail_if_runtime_used(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("provider benchmark mock mode should not call live runtime")

    monkeypatch.setattr(regression_eval, "execute_case_with_runtime", _fail_if_runtime_used)

    report = regression_eval.run_regression(
        baseline="ollama-small",
        candidate="mistral-small-latest",
        dataset_path=dataset_path,
        now=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
    )

    assert report["mode"] == "mock-provider-benchmark"
    assert report["baseline"] == "ollama-small"
    assert report["candidate"] == "mistral-small-latest"
    assert report["aggregate"]["total_cases"] == 1
    assert report["aggregate"]["candidate_total_cost_usd"] > report["aggregate"]["baseline_total_cost_usd"]
    assert report["aggregate"]["candidate_avg_latency_ms"] > report["aggregate"]["baseline_avg_latency_ms"]
    assert report["aggregate"]["baseline_refusal_rate"] == 0.0
    assert report["aggregate"]["candidate_refusal_rate"] == 0.0
    assert report["cases"][0]["baseline"]["answer"]
    assert len(report["cases"][0]["candidate"]["citations"]) == 1


def test_run_regression_supports_experiment_targets_in_mock_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from scripts import regression_eval

    dataset_path = tmp_path / "curated_cases.jsonl"
    _write_dataset(dataset_path)

    def _fail_if_runtime_used(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("experiment mock mode should not call live runtime")

    monkeypatch.setattr(regression_eval, "execute_case_with_runtime", _fail_if_runtime_used)

    report = regression_eval.run_regression(
        baseline="current",
        candidate="2026-05-01-candidate",
        dataset_path=dataset_path,
        mock_experiment_runtime=True,
        now=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert report["mode"] == "mock-experiment-regression"
    assert report["baseline"] == "current"
    assert report["candidate"] == "2026-05-01-candidate"
    assert report["aggregate"]["total_cases"] == 1
    assert report["aggregate"]["candidate_pass_rate"] == 1.0
    assert report["cases"][0]["candidate"]["answer"]
    assert report["cases"][0]["candidate"]["trace_id"] == "mock-experiment-2026-05-01-candidate-case-router-reset"


def test_parse_args_accepts_allow_paid_apis_flag() -> None:
    from scripts import regression_eval

    args = regression_eval.parse_args(
        [
            "--baseline",
            "ollama-small",
            "--candidate",
            "mistral-small-latest",
            "--allow-paid-apis",
        ]
    )

    assert args.allow_paid_apis is True


def test_parse_args_accepts_mock_experiment_runtime_and_no_persist_flags() -> None:
    from scripts import regression_eval

    args = regression_eval.parse_args(
        [
            "--baseline",
            "current",
            "--candidate",
            "current",
            "--mock-experiment-runtime",
            "--no-persist",
        ]
    )

    assert args.mock_experiment_runtime is True
    assert args.no_persist is True


def test_main_no_persist_skips_database_write(monkeypatch, capsys) -> None:
    from scripts import regression_eval

    report = {
        "run_id": "mock-run",
        "exit_code": 0,
        "baseline": "current",
        "candidate": "current",
        "aggregate": {"candidate_pass_rate": 1.0},
        "gate": {"passed": True},
    }
    calls = {"persist": 0}

    def _fake_run_regression(**kwargs):
        assert kwargs["mock_experiment_runtime"] is True
        return report

    async def _fake_persist_regression_result(**kwargs):
        _ = kwargs
        calls["persist"] += 1

    monkeypatch.setattr(regression_eval, "run_regression", _fake_run_regression)
    monkeypatch.setattr(
        regression_eval,
        "write_report_files",
        lambda report: (
            regression_eval.PROJECT_ROOT / "reports" / "regression" / "mock.md",
            regression_eval.PROJECT_ROOT / "reports" / "regression" / "mock.json",
        ),
    )
    monkeypatch.setattr(regression_eval, "persist_regression_result", _fake_persist_regression_result)

    exit_code = regression_eval.main(
        [
            "--baseline",
            "current",
            "--candidate",
            "current",
            "--mock-experiment-runtime",
            "--no-persist",
        ]
    )

    assert exit_code == 0
    assert calls["persist"] == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "mock-run"


def test_main_without_allow_paid_apis_forces_safe_mode(monkeypatch, capsys) -> None:
    from scripts import regression_eval

    report = {
        "run_id": "mock-run",
        "exit_code": 0,
        "baseline": "ollama-small",
        "candidate": "mistral-small-latest",
        "aggregate": {"candidate_pass_rate": 1.0},
        "gate": {"passed": True},
    }
    captured = {}

    def _fake_run_regression(**kwargs):
        captured["allow_paid_apis"] = kwargs["allow_paid_apis"]
        return report

    monkeypatch.setattr(regression_eval, "run_regression", _fake_run_regression)
    monkeypatch.setattr(
        regression_eval,
        "write_report_files",
        lambda report: (
            regression_eval.PROJECT_ROOT / "reports" / "regression" / "mock.md",
            regression_eval.PROJECT_ROOT / "reports" / "regression" / "mock.json",
        ),
    )

    exit_code = regression_eval.main(
        [
            "--baseline",
            "ollama-small",
            "--candidate",
            "mistral-small-latest",
            "--no-persist",
        ]
    )

    assert exit_code == 0
    assert captured["allow_paid_apis"] is False
    assert json.loads(capsys.readouterr().out)["run_id"] == "mock-run"

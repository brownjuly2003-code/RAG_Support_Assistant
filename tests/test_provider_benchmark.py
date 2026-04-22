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

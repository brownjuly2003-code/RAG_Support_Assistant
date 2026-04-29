from __future__ import annotations

import json
import sys
from pathlib import Path

from evaluation import benchmark_runner


def test_load_test_cases_maps_optional_fields(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "question": "reset password",
                    "expected_keywords": ["password"],
                    "expected_answer": "reset password",
                    "category": "auth",
                },
                {"question": "billing"},
            ]
        ),
        encoding="utf-8",
    )

    cases = benchmark_runner.load_test_cases(str(cases_path))

    assert cases[0].question == "reset password"
    assert cases[0].expected_keywords == ["password"]
    assert cases[0].expected_answer == "reset password"
    assert cases[0].category == "auth"
    assert cases[1].expected_keywords == []
    assert cases[1].expected_answer is None
    assert cases[1].category is None


def test_main_writes_output_and_reports_low_relevancy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cases_path = tmp_path / "cases.json"
    output_path = tmp_path / "out" / "benchmark.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "question": "reset password",
                    "expected_keywords": ["password"],
                    "expected_answer": "reset password",
                    "category": "auth",
                },
                {
                    "question": "billing invoice",
                    "expected_keywords": ["invoice"],
                    "category": "billing",
                },
            ]
        ),
        encoding="utf-8",
    )
    printed: list[str] = []

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_runner",
            "--cases",
            str(cases_path),
            "--output",
            str(output_path),
        ],
    )
    monkeypatch.setattr(benchmark_runner, "_print_safe", printed.append)

    benchmark_runner.main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["num_cases"] == 2
    assert any("Low relevancy" in line for line in printed)
    assert any(str(output_path) in line for line in printed)

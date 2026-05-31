from __future__ import annotations

import json
from pathlib import Path

from scripts import aircargo_ragas_eval
from scripts.regression_eval import CaseExpectation, CuratedCase


def _case(case_id: str = "case-1") -> CuratedCase:
    return CuratedCase(
        case_id=case_id,
        tenant_id="aircargo",
        query="Какие документы нужны для командировки?",
        expected=CaseExpectation(
            answer_contains=["командиров"],
            answer_contains_any=[["приказ", "заявка"]],
        ),
    )


def test_expected_keywords_uses_required_and_any_representative() -> None:
    assert aircargo_ragas_eval.expected_keywords_for_case(_case()) == [
        "командиров",
        "приказ",
    ]


def test_mock_aircargo_ragas_writes_json_and_markdown(tmp_path: Path) -> None:
    cases = [_case("case-1"), _case("case-2")]
    answers, contexts, runtime = aircargo_ragas_eval._mock_pipeline_outputs(cases)
    report = aircargo_ragas_eval.run_aircargo_ragas(
        cases,
        answers=answers,
        contexts=contexts,
        runtime=runtime,
        mode="mock-ragas",
        provider_target="ministral-3b-latest",
    )
    report["run_id"] = "run-1"
    report["created_at"] = "2026-06-01T00:00:00+00:00"
    report["dataset"] = "evaluation/curated_cases_aircargo.jsonl"
    report["tenant"] = "aircargo"

    markdown_path, json_path = aircargo_ragas_eval.write_report_files(
        report,
        results_dir=tmp_path,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert markdown_path.exists()
    assert payload["num_cases"] == 2
    assert payload["per_question"][0]["case_id"] == "case-1"
    assert payload["aggregate"]["context_recall"] == 1.0


def test_main_rejects_live_without_paid_opt_in(capsys) -> None:
    exit_code = aircargo_ragas_eval.main(
        [
            "--dataset",
            "evaluation/curated_cases_aircargo.jsonl",
            "--tenant",
            "aircargo",
            "--max-cases",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--allow-paid-apis" in captured.out

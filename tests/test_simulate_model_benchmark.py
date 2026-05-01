from __future__ import annotations

import json

from evaluation import simulate_model_benchmark as benchmark
from evaluation.ragas_eval import TestCase as RagTestCase


def _fake_results() -> dict[str, dict]:
    return {
        "model-a": {
            "profile": {
                "mera_industrial": 0.5,
                "ram_gb": "4",
                "note": "first",
            },
            "aggregate": {
                "answer_relevancy": 0.9,
                "faithfulness": 0.8,
                "context_recall": 0.7,
            },
            "per_question": [
                {"category": "returns", "scores": {"answer_relevancy": 0.8}},
                {"category": None, "scores": {"answer_relevancy": 1.0}},
            ],
        },
        "model-b": {
            "profile": {
                "mera_industrial": 0.4,
                "ram_gb": "8",
                "note": "second",
            },
            "aggregate": {
                "answer_relevancy": 0.6,
                "faithfulness": 0.5,
                "context_recall": 0.4,
            },
            "per_question": [
                {"category": "returns", "scores": {"answer_relevancy": 0.6}},
            ],
        },
    }


def test_text_helpers_normalise_and_select_terms() -> None:
    assert benchmark._normalise(" Hello,   WORLD! ") == "hello world"
    assert benchmark._question_terms("Reset reset warranty?") == ["reset", "warranty"]
    assert benchmark._question_terms("a?") == ["вопрос"]


def test_build_context_and_generated_answer_are_deterministic() -> None:
    case = RagTestCase(
        question="How do I return an item?",
        expected_keywords=["receipt", "14 days", "support"],
        category="returns",
    )

    context = benchmark._build_context(case)
    first = benchmark._generate_answer(case, benchmark.MODEL_PROFILES["mistral:7b"], seed=3)
    second = benchmark._generate_answer(case, benchmark.MODEL_PROFILES["mistral:7b"], seed=3)

    assert context == [
        {
            "page_content": (
                "Вопрос клиента: How do I return an item?. "
                "Ключевые сведения для ответа: receipt, 14 days, support. "
                "Ответ должен быть кратким и по существу."
            )
        }
    ]
    assert first == second
    assert "14 days" in first
    assert "локальными политиками браузера" in first


def test_load_test_cases_reads_optional_fields(tmp_path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "question": "How to reset?",
                    "expected_keywords": ["reset"],
                    "expected_answer": "Press reset",
                    "category": "errors",
                },
                {"question": "Fallback?"},
            ]
        ),
        encoding="utf-8",
    )

    cases = benchmark.load_test_cases(str(cases_path))

    assert [case.question for case in cases] == ["How to reset?", "Fallback?"]
    assert cases[0].expected_keywords == ["reset"]
    assert cases[0].expected_answer == "Press reset"
    assert cases[0].category == "errors"
    assert cases[1].expected_keywords == []


def test_run_simulation_uses_all_model_profiles(monkeypatch) -> None:
    class FakeEvaluator:
        def evaluate_batch(self, test_cases, answers, context_docs_list, use_embeddings):
            assert len(answers) == len(test_cases)
            assert len(context_docs_list) == len(test_cases)
            assert use_embeddings is False
            return {
                "aggregate": {"answer_relevancy": len(answers), "faithfulness": 1.0},
                "per_question": [{"category": test_cases[0].category, "scores": {}}],
            }

    monkeypatch.setattr(benchmark, "RAGEvaluator", FakeEvaluator)

    results = benchmark.run_simulation(
        [
            RagTestCase(
                question="How to reset?",
                expected_keywords=["reset"],
                category="errors",
            )
        ]
    )

    assert set(results) == set(benchmark.MODEL_PROFILES)
    assert results["qwen2.5:7b"]["aggregate"]["answer_relevancy"] == 1


def test_render_markdown_ranks_models_and_lists_categories() -> None:
    report = benchmark.render_markdown(_fake_results())

    assert "Winner of the simulated benchmark: **`model-a`**." in report
    assert "| `model-a` | 0.500 | 0.900 | 0.800 | 0.700 | Recommended |" in report
    assert "| other | 1.000 |" in report
    assert "| returns | 0.800 |" in report


def test_main_writes_markdown_and_json_outputs(tmp_path, monkeypatch, capsys) -> None:
    cases_path = tmp_path / "cases.json"
    report_path = tmp_path / "report.md"
    json_path = tmp_path / "result.json"
    cases_path.write_text(
        json.dumps([{"question": "Q?", "expected_keywords": ["answer"]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark, "run_simulation", lambda test_cases: _fake_results())
    monkeypatch.setattr(
        benchmark.sys,
        "argv",
        [
            "simulate_model_benchmark.py",
            "--cases",
            str(cases_path),
            "--output",
            str(report_path),
            "--json-output",
            str(json_path),
        ],
    )

    benchmark.main()

    output = capsys.readouterr().out
    assert "Loading" in output
    assert "Recommendation: ollama pull model-a" in output
    assert "Winner of the simulated benchmark: **`model-a`**." in report_path.read_text(
        encoding="utf-8"
    )
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["model-a"]["aggregate"]["answer_relevancy"] == 0.9

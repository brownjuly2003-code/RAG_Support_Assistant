from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.ragas_eval import (
    RAGEvaluator,
    TestCase as RAGTestCase,
    answer_relevancy,
    answer_relevancy_embedding,
    context_precision,
    context_recall,
    faithfulness,
)


class _LLM:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> object:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_metric_helpers_score_edge_cases() -> None:
    docs = [
        SimpleNamespace(page_content="Warranty lasts one year. Password reset is supported."),
        {"page_content": "Returns are accepted for 14 days."},
    ]

    assert faithfulness("", docs) == 0.0
    assert faithfulness("OK.", docs) == 1.0
    assert faithfulness("Warranty lasts one year. Unsupported claim.", docs) == 0.5
    assert answer_relevancy("", "answer") == 0.0
    assert answer_relevancy("hi", "short question") == 1.0
    assert answer_relevancy("reset password", "Password reset is supported.") == 1.0
    assert round(context_precision("reset password", docs, ["warranty"]), 4) == 0.6667
    assert context_recall(docs, ["password", "missing"]) == 0.5
    assert context_recall(docs, []) == 1.0


def test_answer_relevancy_embedding_falls_back_when_sentence_transformers_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentence_transformers":
            raise ImportError("missing sentence_transformers")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    assert answer_relevancy_embedding("reset password", "reset password") == 1.0


def test_evaluate_single_uses_eval_llm_scores_and_keyword_context(tmp_path: Path) -> None:
    eval_llm = _LLM(["0.7", "Score: 0.25"])
    evaluator = RAGEvaluator(eval_llm=eval_llm, results_dir=str(tmp_path))

    scores = evaluator.evaluate_single(
        question="How do I reset password?",
        answer="Reset password in settings.",
        context_docs=[{"page_content": "Reset password in settings."}],
        expected_keywords=["settings"],
    )

    assert scores == {
        "faithfulness": 0.7,
        "answer_relevancy": 0.25,
        "context_precision": 0.75,
        "context_recall": 1.0,
    }
    assert len(eval_llm.prompts) == 2


def test_evaluate_single_falls_back_when_eval_llm_raises(tmp_path: Path) -> None:
    class _BrokenLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            raise RuntimeError("eval failed")

    evaluator = RAGEvaluator(eval_llm=_BrokenLLM(), results_dir=str(tmp_path))

    scores = evaluator.evaluate_single(
        question="reset password",
        answer="Reset password",
        context_docs=[{"page_content": "Reset password"}],
        expected_keywords=["password"],
    )

    assert scores == {
        "faithfulness": 1.0,
        "answer_relevancy": 1.0,
        "context_precision": 1.0,
        "context_recall": 1.0,
    }


def test_evaluate_batch_uses_expected_answers_and_handles_empty_batch(tmp_path: Path) -> None:
    evaluator = RAGEvaluator(results_dir=str(tmp_path))
    cases = [
        RAGTestCase(
            question="reset password",
            expected_keywords=["password"],
            expected_answer="reset password",
            category="auth",
        ),
        RAGTestCase(
            question="return policy",
            expected_keywords=["return"],
            expected_answer="return policy",
            category="orders",
        ),
    ]

    result = evaluator.evaluate_batch(
        cases,
        context_docs_list=[
            [{"page_content": "reset password"}],
            [{"page_content": "return policy"}],
        ],
    )

    assert result["num_cases"] == 2
    assert result["aggregate"] == {
        "faithfulness": 1.0,
        "answer_relevancy": 1.0,
        "context_precision": 1.0,
        "context_recall": 1.0,
    }
    assert result["per_question"][0]["category"] == "auth"
    assert evaluator.evaluate_batch([])["aggregate"] == {
        "faithfulness": 0.0,
        "answer_relevancy": 0.0,
        "context_precision": 0.0,
        "context_recall": 0.0,
    }


def test_run_benchmark_retrieves_generates_saves_and_normalises_docs(tmp_path: Path) -> None:
    class _Retriever:
        def get_relevant_documents(self, query: str) -> list[object]:
            _ = query
            return [
                SimpleNamespace(
                    page_content="reset password policy",
                    metadata={"source": "kb.md"},
                ),
                "plain context",
            ]

    evaluator = RAGEvaluator(results_dir=str(tmp_path))
    result = evaluator.run_benchmark(
        retriever=_Retriever(),
        llm=_LLM(["reset password policy"]),
        test_cases=[RAGTestCase(question="reset password", expected_keywords=["password"])],
    )

    assert result["num_cases"] == 1
    assert result["per_question"][0]["answer"] == "reset password policy"
    assert result["per_question"][0]["context_docs_count"] == 2
    saved = json.loads((tmp_path / "benchmark_results.json").read_text(encoding="utf-8"))
    assert saved["per_question"][0]["context_docs_count"] == 2


def test_run_benchmark_uses_invoke_fallback_and_handles_pipeline_errors(tmp_path: Path) -> None:
    class _InvokeRetriever:
        def invoke(self, query: str) -> list[dict[str, str]]:
            _ = query
            return [{"page_content": "return policy"}]

    class _FailingRetriever:
        def get_relevant_documents(self, query: str) -> list[object]:
            _ = query
            raise RuntimeError("retrieval failed")

    class _FailingLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            raise RuntimeError("generation failed")

    evaluator = RAGEvaluator(results_dir=str(tmp_path))

    invoke_result = evaluator.run_benchmark(
        retriever=_InvokeRetriever(),
        llm=_LLM([123]),
        test_cases=[RAGTestCase(question="return policy", expected_keywords=["return"])],
        save=False,
    )
    assert invoke_result["per_question"][0]["answer"] == "123"
    assert invoke_result["per_question"][0]["context_docs_count"] == 1

    failed_result = evaluator.run_benchmark(
        retriever=_FailingRetriever(),
        llm=_FailingLLM(),
        test_cases=[RAGTestCase(question="return policy", expected_keywords=["return"])],
        save=False,
    )
    assert failed_result["per_question"][0]["answer"] == ""
    assert failed_result["per_question"][0]["context_docs_count"] == 0
    assert failed_result["aggregate"]["faithfulness"] == 0.0

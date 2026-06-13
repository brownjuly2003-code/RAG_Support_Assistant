#!/usr/bin/env python3
"""
evaluation/benchmark_runner.py

Offline benchmark: загружает тест-кейсы, прогоняет через RAGEvaluator,
сохраняет результаты в data/evaluation/benchmark_results.json.

Использование:
    python evaluation/benchmark_runner.py
    python evaluation/benchmark_runner.py --use-embeddings
    python evaluation/benchmark_runner.py --cases evaluation/test_cases.json

RAGEvaluator работает без запущенного сервера:
- без retriever/llm — оценивает только если передан answer
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ragas_eval import RAGEvaluator, TestCase


def load_test_cases(path: str) -> list[TestCase]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [
        TestCase(
            question=item["question"],
            expected_keywords=item.get("expected_keywords", []),
            expected_answer=item.get("expected_answer"),
            category=item.get("category"),
        )
        for item in raw
    ]


def _print_safe(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG offline benchmark runner")
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).parent / "test_cases.json"),
        help="Path to test cases JSON file",
    )
    parser.add_argument(
        "--use-embeddings",
        action="store_true",
        help="Use embedding-based answer_relevancy (requires sentence-transformers)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file (default: data/evaluation/benchmark_results.json)",
    )
    args = parser.parse_args()

    _print_safe(f"Loading test cases from: {args.cases}")
    test_cases = load_test_cases(args.cases)
    _print_safe(f"  {len(test_cases)} cases loaded")

    evaluator = RAGEvaluator(
        results_dir=args.output and str(Path(args.output).parent) or None
    )

    answers = [tc.expected_answer or "" for tc in test_cases]
    context_docs_list: list[list[str]] = [[] for _ in test_cases]

    _print_safe(f"Running evaluation (use_embeddings={args.use_embeddings})...")
    results = evaluator.evaluate_batch(
        test_cases,
        answers=answers,
        context_docs_list=context_docs_list,
        use_embeddings=args.use_embeddings,
    )

    _print_safe("\n--- Aggregate scores ---")
    for metric, score in results["aggregate"].items():
        _print_safe(f"  {metric}: {score:.4f}")

    low_quality = [
        pq for pq in results["per_question"]
        if pq["scores"].get("answer_relevancy", 1.0) < 0.5
    ]
    if low_quality:
        _print_safe(f"\n--- Low relevancy cases ({len(low_quality)}) ---")
        for pq in low_quality:
            _print_safe(f"  [{pq['category']}] {pq['question'][:60]}...")
            _print_safe(f"    answer_relevancy={pq['scores']['answer_relevancy']}")

    out_path = args.output or str(
        Path(__file__).resolve().parent.parent
        / "data"
        / "evaluation"
        / "benchmark_results.json"
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    _print_safe(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()

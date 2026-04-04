# Task 19 — Offline evaluation benchmark runner

## Goal
Создать скрипт и тест-кейсы для периодической оценки качества системы.
Запускается вручную или по расписанию, сохраняет результаты в JSON.
Не зависит от запущенного сервера — работает напрямую с pipeline.

## Background (из eval-metrics-2025.md)
Рекомендация: дорогой LLM-as-judge — только для offline batch eval.
Cheap online: keyword + embedding proxies (уже сделано в task-12).
Offline benchmark — раз в неделю / после значимых изменений.

## Files to create
- `evaluation/benchmark_runner.py` — скрипт запуска
- `evaluation/test_cases.json` — 10+ поддержка-специфичных тест-кейсов

---

## 1. evaluation/test_cases.json

Создать файл с тест-кейсами для типичных support-сценариев.
Структура каждого кейса:
```json
{
  "question": "...",
  "expected_keywords": ["...", "..."],
  "expected_answer": null,
  "category": "..."
}
```

Заполнить 12 кейсов по категориям (придумай реалистичные для support):
- `error_codes` (3 кейса): «Что означает ошибка E401?», «Почему появляется код 503?», «Как исправить E20?»
- `reset_password` (2 кейса): «Как сбросить пароль?», «Восстановление доступа к аккаунту»
- `warranty` (2 кейса): «Сколько длится гарантия?», «Условия гарантийного обслуживания»
- `installation` (2 кейса): «Как установить приложение?», «Инструкция по установке на Windows»
- `billing` (2 кейса): «Как отменить подписку?», «Изменить способ оплаты»
- `general` (1 кейс): «Как связаться с поддержкой?»

В `expected_keywords` укажи 2-4 ключевых слова, которые ДОЛЖНЫ быть в правильном ответе.
`expected_answer` оставь `null` — у нас нет ground truth.

---

## 2. evaluation/benchmark_runner.py

```python
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
- с --mock-answers — генерирует синтетические ответы для теста метрик
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
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

    print(f"Loading test cases from: {args.cases}")
    test_cases = load_test_cases(args.cases)
    print(f"  {len(test_cases)} cases loaded")

    evaluator = RAGEvaluator(
        results_dir=args.output
        and str(Path(args.output).parent)
        or None
    )

    # Для offline benchmark без реального pipeline используем expected_answer как answer
    # (оценивает метрики на ground-truth ответах — это baseline)
    answers = [tc.expected_answer or "" for tc in test_cases]
    context_docs_list = [[] for _ in test_cases]  # нет реальных docs — оцениваем только relevancy

    print(f"Running evaluation (use_embeddings={args.use_embeddings})...")
    results = evaluator.evaluate_batch(
        test_cases,
        answers=answers,
        context_docs_list=context_docs_list,
        use_embeddings=args.use_embeddings,
    )

    # Вывести агрегированные метрики
    print("\n--- Aggregate scores ---")
    for metric, score in results["aggregate"].items():
        print(f"  {metric}: {score:.4f}")

    # Вывести проблемные кейсы (answer_relevancy < 0.5)
    low_quality = [
        pq for pq in results["per_question"]
        if pq["scores"].get("answer_relevancy", 1.0) < 0.5
    ]
    if low_quality:
        print(f"\n--- Low relevancy cases ({len(low_quality)}) ---")
        for pq in low_quality:
            print(f"  [{pq['category']}] {pq['question'][:60]}...")
            print(f"    answer_relevancy={pq['scores']['answer_relevancy']}")

    # Сохранить результаты
    out_path = args.output or str(
        Path(__file__).resolve().parent.parent / "data" / "evaluation" / "benchmark_results.json"
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
```

---

## CONSTRAINTS
- Создать только `evaluation/benchmark_runner.py` и `evaluation/test_cases.json`
- Никакие существующие файлы не трогать
- Скрипт должен запускаться: `python evaluation/benchmark_runner.py` из корня проекта
- `pytest tests/ -v` — проходит (скрипт не является тестом, не конфликтует)
- test_cases.json — валидный JSON, 12 кейсов, нет русских плейсхолдеров

## DONE WHEN
- [ ] `evaluation/test_cases.json` содержит 12 кейсов по 5 категориям
- [ ] `python evaluation/benchmark_runner.py` запускается без ошибок
- [ ] Выводит aggregate scores в stdout
- [ ] Сохраняет результат в `data/evaluation/benchmark_results.json`
- [ ] `pytest tests/ -v` — 19 passed

# Task 26 — Simulate model benchmark (без запуска Ollama)

## Goal
Смоделировать сравнение четырёх Ollama-моделей на 12 support-кейсах из
`evaluation/test_cases.json` — без реального запуска LLM.

Симуляция основана на MERA-бенчмарках из `docs/research/llm-model-selection-2025.md`:
каждая модель получает синтетические ответы, качество которых пропорционально её MERA-баллу.
Результаты прогоняются через `RAGEvaluator` и сохраняются как документ и JSON.

## Files to create
- `evaluation/simulate_model_benchmark.py`

## Model profiles (из R1-рисерча)

| Модель | MERA Industrial | IFEval proxy | RAM |
|--------|----------------|-------------|-----|
| `qwen2.5:7b` | 0.555 | высокий | 8-10 GB |
| `gemma3:4b` | 0.477 | 90.2 (лучший) | 6-8 GB |
| `llama3.1:8b` | 0.437 | 80.4 | 8-10 GB |
| `mistral:7b` | 0.213 | слабый | 8-10 GB |

---

## evaluation/simulate_model_benchmark.py

```python
#!/usr/bin/env python3
"""
evaluation/simulate_model_benchmark.py

Симуляция сравнения LLM-моделей на русскоязычных support-кейсах.

Не требует запущенного Ollama. Генерирует синтетические ответы на основе
MERA-профилей моделей (docs/research/llm-model-selection-2025.md),
прогоняет через RAGEvaluator и сохраняет результаты.

Использование:
    python evaluation/simulate_model_benchmark.py
    python evaluation/simulate_model_benchmark.py --output docs/research/simulated_model_comparison.md
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ragas_eval import RAGEvaluator, TestCase

# ---------------------------------------------------------------------------
# Профили моделей — на основе MERA Industrial scores из R1-рисерча
# quality_rate: доля expected_keywords, которые модель обычно включает в ответ
# extra_words:  типичные "шумовые" слова добавляемые к ответу (реалистичность)
# ---------------------------------------------------------------------------
MODEL_PROFILES = {
    "qwen2.5:7b": {
        "mera_industrial": 0.555,
        "quality_rate": 0.92,   # включает ~92% ожидаемых ключевых слов
        "style": "Для решения данной проблемы необходимо {keywords}. "
                 "Пожалуйста, убедитесь что {extra}. При необходимости обратитесь в поддержку.",
        "ram_gb": "8-10",
        "note": "Best overall Russian quality. Recommended default.",
    },
    "gemma3:4b": {
        "mera_industrial": 0.477,
        "quality_rate": 0.80,
        "style": "Чтобы решить вопрос: {keywords}. {extra}.",
        "ram_gb": "6-8",
        "note": "Best instruction following (IFEval 90.2). Lightest option.",
    },
    "llama3.1:8b": {
        "mera_industrial": 0.437,
        "quality_rate": 0.72,
        "style": "Для этого требуется {keywords}. Дополнительно: {extra}.",
        "ram_gb": "8-10",
        "note": "Decent Russian. Good English. Solid backup choice.",
    },
    "mistral:7b": {
        "mera_industrial": 0.213,
        "quality_rate": 0.48,   # текущая модель — включает лишь ~48% ключей
        "style": "{keywords}. {extra}.",
        "ram_gb": "8-10",
        "note": "Current default. Weakest Russian per MERA benchmarks.",
    },
}

# Дополнительные «шумовые» фразы для реалистичности
EXTRA_PHRASES = [
    "следуйте инструкциям",
    "проверьте настройки",
    "перезагрузите приложение",
    "свяжитесь с администратором",
    "обновите программу",
    "проверьте подключение к сети",
    "сохраните изменения",
]


def _generate_answer(keywords: list[str], profile: dict, seed: int) -> str:
    """Генерирует синтетический ответ на основе профиля модели."""
    rng = random.Random(seed)
    rate = profile["quality_rate"]

    # Включаем keywords согласно quality_rate
    included = [kw for kw in keywords if rng.random() < rate]
    if not included:
        included = keywords[:1]  # хотя бы одно

    extra = rng.choice(EXTRA_PHRASES)
    kw_str = ", ".join(included)
    return profile["style"].format(keywords=kw_str, extra=extra)


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


def run_simulation(test_cases: list[TestCase]) -> dict:
    """Прогоняет все модели через RAGEvaluator, возвращает результаты."""
    evaluator = RAGEvaluator()
    results: dict[str, dict] = {}

    for model_name, profile in MODEL_PROFILES.items():
        answers = [
            _generate_answer(tc.expected_keywords, profile, seed=i)
            for i, tc in enumerate(test_cases)
        ]
        batch = evaluator.evaluate_batch(
            test_cases,
            answers=answers,
            context_docs_list=[[] for _ in test_cases],
            use_embeddings=False,
        )
        results[model_name] = {
            "profile": profile,
            "aggregate": batch["aggregate"],
            "per_question": batch["per_question"],
        }

    return results


def render_markdown(results: dict, test_cases: list[TestCase]) -> str:
    """Рендерит Markdown-отчёт с таблицей сравнения."""
    lines = [
        "# Simulated Model Benchmark — RAG Support Assistant",
        "",
        "> Симуляция основана на MERA-профилях из `docs/research/llm-model-selection-2025.md`.",
        "> Ответы синтетические; качество пропорционально реальным MERA Industrial scores.",
        "",
        "## Aggregate scores",
        "",
        "| Модель | MERA Industrial | answer_relevancy | faithfulness | context_recall | Рекомендация |",
        "|--------|:--------------:|:----------------:|:------------:|:--------------:|-------------|",
    ]

    # Сортируем по answer_relevancy desc
    ranked = sorted(
        results.items(),
        key=lambda x: x[1]["aggregate"].get("answer_relevancy", 0),
        reverse=True,
    )

    for rank, (model, data) in enumerate(ranked):
        agg = data["aggregate"]
        profile = data["profile"]
        rec = "✅ **Рекомендуется**" if rank == 0 else ("⚠️ Альтернатива" if rank == 1 else "")
        lines.append(
            f"| `{model}` "
            f"| {profile['mera_industrial']:.3f} "
            f"| {agg.get('answer_relevancy', 0):.3f} "
            f"| {agg.get('faithfulness', 0):.3f} "
            f"| {agg.get('context_recall', 0):.3f} "
            f"| {rec} |"
        )

    lines += [
        "",
        "## Notes per model",
        "",
    ]
    for model, data in ranked:
        lines.append(f"**`{model}`** — RAM: {data['profile']['ram_gb']} GB. "
                     f"{data['profile']['note']}")
        lines.append("")

    lines += [
        "## Recommendation",
        "",
        f"На основе симуляции и MERA-бенчмарков победитель: **`{ranked[0][0]}`**.",
        "",
        "```bash",
        f"ollama pull {ranked[0][0]}",
        "```",
        "",
        "```dotenv",
        f"OLLAMA_MODEL_NAME={ranked[0][0]}",
        "```",
        "",
        "## Per-category breakdown",
        "",
    ]

    # Группируем per_question по категориям для топ-модели
    top_model = ranked[0][0]
    cats: dict[str, list[float]] = {}
    for pq in results[top_model]["per_question"]:
        cat = pq.get("category") or "other"
        cats.setdefault(cat, []).append(pq["scores"].get("answer_relevancy", 0))

    lines.append("| Категория | avg answer_relevancy (top model) |")
    lines.append("|-----------|:--------------------------------:|")
    for cat, scores in sorted(cats.items()):
        avg = sum(scores) / len(scores)
        lines.append(f"| {cat} | {avg:.3f} |")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).parent / "test_cases.json"),
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "research" / "simulated_model_comparison.md"),
    )
    parser.add_argument(
        "--json-output",
        default=str(Path(__file__).resolve().parent.parent / "data" / "evaluation" / "simulated_benchmark.json"),
    )
    args = parser.parse_args()

    print(f"Loading {args.cases}...")
    test_cases = load_test_cases(args.cases)
    print(f"  {len(test_cases)} cases, {len(MODEL_PROFILES)} models")

    print("Running simulation...")
    results = run_simulation(test_cases)

    # Markdown report
    md = render_markdown(results, test_cases)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(md, encoding="utf-8")
    print(f"Report: {args.output}")

    # JSON results
    Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
    serialisable = {
        m: {
            "mera_industrial": d["profile"]["mera_industrial"],
            "ram_gb": d["profile"]["ram_gb"],
            "note": d["profile"]["note"],
            "aggregate": d["aggregate"],
        }
        for m, d in results.items()
    }
    Path(args.json_output).write_text(
        json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"JSON:   {args.json_output}")

    # Print summary table to stdout
    print("\n--- Results ---")
    ranked = sorted(results.items(), key=lambda x: x[1]["aggregate"].get("answer_relevancy", 0), reverse=True)
    for rank, (model, data) in enumerate(ranked):
        agg = data["aggregate"]
        marker = "★" if rank == 0 else " "
        print(f"  {marker} {model:<18} relevancy={agg['answer_relevancy']:.3f}  "
              f"faithfulness={agg['faithfulness']:.3f}  "
              f"mera={data['profile']['mera_industrial']:.3f}")

    winner = ranked[0][0]
    print(f"\nRecommendation: ollama pull {winner}")
    print(f"               OLLAMA_MODEL_NAME={winner}")


if __name__ == "__main__":
    main()
```

---

## CONSTRAINTS
- Создать только `evaluation/simulate_model_benchmark.py`
- Никаких изменений в существующих файлах
- Скрипт запускается без Ollama: `python evaluation/simulate_model_benchmark.py`
- Выходной файл: `docs/research/simulated_model_comparison.md`
- `pytest tests/ -v` — проходит (скрипт не конфликтует с тестами)

## DONE WHEN
- [ ] `evaluation/simulate_model_benchmark.py` создан
- [ ] `python evaluation/simulate_model_benchmark.py` запускается без ошибок
- [ ] `docs/research/simulated_model_comparison.md` создан
- [ ] В stdout виден ranking с qwen2.5:7b на первом месте (ожидаемо по MERA)
- [ ] `pytest tests/ -v` — все тесты проходят

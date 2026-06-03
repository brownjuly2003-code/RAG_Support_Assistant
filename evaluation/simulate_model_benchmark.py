#!/usr/bin/env python3
"""
Simulate a benchmark for several Ollama models on support test cases.

The script does not call Ollama. It generates deterministic synthetic answers
based on model quality profiles, runs them through RAGEvaluator, and writes
both Markdown and JSON reports.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ragas_eval import RAGEvaluator, TestCase

MODEL_PROFILES = {
    "qwen2.5:7b": {
        "mera_industrial": 0.555,
        "quality_rate": 0.92,
        "question_rate": 0.9,
        "unsupported_sentences": 0,
        "style": (
            "По вопросу {question_terms}: рекомендуемые действия — {keywords}. "
            "Пожалуйста, убедитесь, что {extra}."
        ),
        "ram_gb": "8-10",
        "note": "Best overall Russian quality. Recommended default.",
        "seed_offset": 11,
    },
    "gemma3:4b": {
        "mera_industrial": 0.477,
        "quality_rate": 0.8,
        "question_rate": 0.78,
        "unsupported_sentences": 0,
        "style": "По теме {question_terms}: важно {keywords}. Также {extra}.",
        "ram_gb": "6-8",
        "note": "Best instruction following (IFEval 90.2). Lightest option.",
        "seed_offset": 23,
    },
    "llama3.1:8b": {
        "mera_industrial": 0.437,
        "quality_rate": 0.72,
        "question_rate": 0.66,
        "unsupported_sentences": 1,
        "style": "Для запроса {question_terms} требуется {keywords}. Дополнительно {extra}.",
        "ram_gb": "8-10",
        "note": "Decent Russian. Good English. Solid backup choice.",
        "seed_offset": 37,
    },
    "mistral:7b": {
        "mera_industrial": 0.213,
        "quality_rate": 0.48,
        "question_rate": 0.42,
        "unsupported_sentences": 2,
        "style": "По запросу {question_terms}: {keywords}. {extra}.",
        "ram_gb": "8-10",
        "note": "Current default. Weakest Russian per MERA benchmarks.",
        "seed_offset": 53,
    },
}

EXTRA_PHRASES = [
    "проверьте настройки доступа",
    "перезапустите приложение",
    "убедитесь, что данные сохранены",
    "при необходимости обратитесь в поддержку",
    "обновите программу до актуальной версии",
    "проверьте подключение к сети",
]

UNSUPPORTED_SENTENCES = [
    "Иногда проблема связана с локальными политиками браузера.",
    "В отдельных случаях влияет история фоновых обновлений.",
    "Также помогает повторная синхронизация внутренних модулей.",
]


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pick_terms(items: list[str], rate: float, rng: random.Random) -> list[str]:
    if not items:
        return []
    count = max(1, round(len(items) * rate))
    count = min(count, len(items))
    pool = items[:]
    rng.shuffle(pool)
    return pool[:count]


def _question_terms(question: str) -> list[str]:
    words = [word for word in _normalise(question).split() if len(word) >= 3]
    if not words:
        return ["вопрос"]
    return list(dict.fromkeys(words))


def _build_context(tc: TestCase) -> list[dict[str, str]]:
    keyword_text = ", ".join(tc.expected_keywords) if tc.expected_keywords else "поддержка"
    context = (
        f"Вопрос клиента: {tc.question}. "
        f"Ключевые сведения для ответа: {keyword_text}. "
        "Ответ должен быть кратким и по существу."
    )
    return [{"page_content": context}]


def _generate_answer(test_case: TestCase, profile: dict[str, object], seed: int) -> str:
    rng = random.Random(seed + int(profile["seed_offset"]))

    included_keywords = _pick_terms(
        list(test_case.expected_keywords),
        float(profile["quality_rate"]),
        rng,
    )
    if not included_keywords:
        included_keywords = ["поддержка"]

    included_question_terms = _pick_terms(
        _question_terms(test_case.question),
        float(profile["question_rate"]),
        rng,
    )

    answer = str(profile["style"]).format(
        question_terms=", ".join(included_question_terms),
        keywords=", ".join(included_keywords),
        extra=rng.choice(EXTRA_PHRASES),
    )

    extra_sentences = int(profile["unsupported_sentences"])
    for sentence in UNSUPPORTED_SENTENCES[:extra_sentences]:
        answer = f"{answer} {sentence}"

    return answer


def load_test_cases(path: str) -> list[TestCase]:
    with open(path, encoding="utf-8") as file:
        raw_cases = json.load(file)

    return [
        TestCase(
            question=item["question"],
            expected_keywords=item.get("expected_keywords", []),
            expected_answer=item.get("expected_answer"),
            category=item.get("category"),
        )
        for item in raw_cases
    ]


def run_simulation(test_cases: list[TestCase]) -> dict[str, dict]:
    evaluator = RAGEvaluator()
    results: dict[str, dict] = {}

    for model_name, profile in MODEL_PROFILES.items():
        answers = [
            _generate_answer(test_case, profile, seed=index)
            for index, test_case in enumerate(test_cases)
        ]
        contexts = [_build_context(test_case) for test_case in test_cases]
        batch = evaluator.evaluate_batch(
            test_cases,
            answers=answers,
            context_docs_list=contexts,
            use_embeddings=False,
        )
        results[model_name] = {
            "profile": profile,
            "aggregate": batch["aggregate"],
            "per_question": batch["per_question"],
        }

    return results


def render_markdown(results: dict[str, dict]) -> str:
    ranked = sorted(
        results.items(),
        key=lambda item: item[1]["aggregate"].get("answer_relevancy", 0),
        reverse=True,
    )

    lines = [
        "# Simulated Model Benchmark - RAG Support Assistant",
        "",
        "> Benchmark is simulated from MERA-derived model profiles in `docs/research/llm-model-selection-2025.md`.",
        "> Answers are synthetic and deterministic; ranking reflects relative answer quality, not live Ollama inference.",
        "",
        "## Aggregate scores",
        "",
        "| Model | MERA Industrial | answer_relevancy | faithfulness | context_recall | Recommendation |",
        "|-------|:---------------:|:----------------:|:------------:|:--------------:|----------------|",
    ]

    for rank, (model_name, data) in enumerate(ranked):
        aggregate = data["aggregate"]
        profile = data["profile"]
        recommendation = ""
        if rank == 0:
            recommendation = "Recommended"
        elif rank == 1:
            recommendation = "Alternative"

        lines.append(
            f"| `{model_name}` | "
            f"{profile['mera_industrial']:.3f} | "
            f"{aggregate.get('answer_relevancy', 0):.3f} | "
            f"{aggregate.get('faithfulness', 0):.3f} | "
            f"{aggregate.get('context_recall', 0):.3f} | "
            f"{recommendation} |"
        )

    lines.extend(
        [
            "",
            "## Notes per model",
            "",
        ]
    )

    for model_name, data in ranked:
        lines.append(
            f"- `{model_name}` - RAM: {data['profile']['ram_gb']} GB. {data['profile']['note']}"
        )

    winner = ranked[0][0]
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"Winner of the simulated benchmark: **`{winner}`**.",
            "",
            "```bash",
            f"ollama pull {winner}",
            "```",
            "",
            "```dotenv",
            f"OLLAMA_MODEL_NAME={winner}",
            "```",
            "",
            "## Per-category breakdown",
            "",
            "| Category | avg answer_relevancy (winner) |",
            "|----------|:-----------------------------:|",
        ]
    )

    category_scores: dict[str, list[float]] = {}
    for item in results[winner]["per_question"]:
        category = item.get("category") or "other"
        category_scores.setdefault(category, []).append(
            item["scores"].get("answer_relevancy", 0)
        )

    for category, scores in sorted(category_scores.items()):
        average = sum(scores) / len(scores)
        lines.append(f"| {category} | {average:.3f} |")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).parent / "test_cases.json"),
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).resolve().parent.parent
            / "docs"
            / "research"
            / "simulated_model_comparison.md"
        ),
    )
    parser.add_argument(
        "--json-output",
        default=str(
            Path(__file__).resolve().parent.parent
            / "data"
            / "evaluation"
            / "simulated_benchmark.json"
        ),
    )
    args = parser.parse_args()

    print(f"Loading {args.cases}...")
    test_cases = load_test_cases(args.cases)
    print(f"  {len(test_cases)} cases, {len(MODEL_PROFILES)} models")

    print("Running simulation...")
    results = run_simulation(test_cases)

    report = render_markdown(results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report: {output_path}")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    serialisable = {
        model_name: {
            "mera_industrial": data["profile"]["mera_industrial"],
            "ram_gb": data["profile"]["ram_gb"],
            "note": data["profile"]["note"],
            "aggregate": data["aggregate"],
        }
        for model_name, data in results.items()
    }
    json_path.write_text(
        json.dumps(serialisable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"JSON:   {json_path}")

    print("\n--- Results ---")
    ranked = sorted(
        results.items(),
        key=lambda item: item[1]["aggregate"].get("answer_relevancy", 0),
        reverse=True,
    )
    for rank, (model_name, data) in enumerate(ranked):
        aggregate = data["aggregate"]
        marker = "*" if rank == 0 else " "
        print(
            f"  {marker} {model_name:<18} "
            f"relevancy={aggregate['answer_relevancy']:.3f}  "
            f"faithfulness={aggregate['faithfulness']:.3f}  "
            f"mera={data['profile']['mera_industrial']:.3f}"
        )

    winner = ranked[0][0]
    print(f"\nRecommendation: ollama pull {winner}")
    print(f"               OLLAMA_MODEL_NAME={winner}")


if __name__ == "__main__":
    main()

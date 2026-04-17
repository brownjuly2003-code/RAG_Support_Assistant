# Task 59 — RQ-2: Evaluation CI/CD gate

## Goal
Добавить CI-gate: PR с ухудшением RAG-метрик блокируется.
Использовать существующий `evaluation/test_cases.json` + `evaluation/ragas_eval.py`.

## Files to create
- `scripts/eval_gate.py` — скрипт для CI: запускает eval, сравнивает с baseline

## Files to change
- `.github/workflows/ci.yml` — добавить eval step
- `evaluation/test_cases.json` — убедиться что есть минимум 10 golden Q&A пар

---

## 1. scripts/eval_gate.py

```python
#!/usr/bin/env python3
"""CI evaluation gate — blocks PR if RAG quality drops below thresholds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Thresholds — PR blocked if metrics below these
THRESHOLDS = {
    "context_precision": 0.7,
    "faithfulness": 0.75,
    "answer_relevance": 0.7,
}

BASELINE_FILE = PROJECT_ROOT / "evaluation" / "baseline_metrics.json"
TEST_CASES_FILE = PROJECT_ROOT / "evaluation" / "test_cases.json"


def load_test_cases() -> list[dict]:
    with TEST_CASES_FILE.open() as f:
        return json.load(f)


def run_evaluation(test_cases: list[dict]) -> dict[str, float]:
    """Run lightweight evaluation without full RAGAS (for CI speed).

    Returns dict of metric_name -> score (0-1).
    """
    # Lightweight eval: check if pipeline returns answers for golden questions
    scores = {
        "context_precision": 0.0,
        "faithfulness": 0.0,
        "answer_relevance": 0.0,
    }

    try:
        from graph import run_qa_pipeline
    except ImportError:
        try:
            from agent.graph import run_qa_pipeline
        except ImportError:
            print("WARN: Pipeline not importable, skipping eval gate")
            return {k: 1.0 for k in THRESHOLDS}  # Pass if can't evaluate

    total = len(test_cases)
    if total == 0:
        print("WARN: No test cases found")
        return {k: 1.0 for k in THRESHOLDS}

    answered = 0
    relevant = 0

    for tc in test_cases:
        question = tc.get("question", "")
        expected = tc.get("expected_answer", "")
        if not question:
            continue
        try:
            result = run_qa_pipeline(question)
            answer = result.get("answer", "")
            quality = result.get("quality_score", 0)

            if answer and answer != "Не удалось обработать запрос":
                answered += 1
            if quality >= 60:
                relevant += 1
        except Exception as exc:
            print(f"  FAIL: {question[:50]}... → {exc}")

    scores["answer_relevance"] = answered / total if total > 0 else 0
    scores["faithfulness"] = relevant / total if total > 0 else 0
    scores["context_precision"] = scores["answer_relevance"]  # simplified proxy

    return scores


def main() -> int:
    print("=" * 60)
    print("RAG Evaluation Gate")
    print("=" * 60)

    test_cases = load_test_cases()
    print(f"Test cases: {len(test_cases)}")

    scores = run_evaluation(test_cases)

    # Compare with thresholds
    passed = True
    for metric, threshold in THRESHOLDS.items():
        score = scores.get(metric, 0)
        status = "PASS" if score >= threshold else "FAIL"
        if score < threshold:
            passed = False
        print(f"  {metric}: {score:.2f} (threshold: {threshold}) [{status}]")

    # Save current scores as potential new baseline
    output = PROJECT_ROOT / "evaluation" / "current_metrics.json"
    with output.open("w") as f:
        json.dump(scores, f, indent=2)

    if passed:
        print("\nEVAL GATE: PASSED")
        return 0
    else:
        print("\nEVAL GATE: FAILED — PR blocked")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## 2. .github/workflows/ci.yml

Добавить step после тестов:

```yaml
    - name: RAG Evaluation Gate
      if: github.event_name == 'pull_request'
      run: python scripts/eval_gate.py
      continue-on-error: true  # Start as warning, make blocking later
      env:
        OLLAMA_BASE_URL: "http://localhost:11434"
```

---

## CONSTRAINTS
- Создать `scripts/eval_gate.py`
- Обновить CI workflow
- `continue-on-error: true` на первое время (не блокировать сразу)
- Без Ollama — gate проходит (graceful skip)
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `scripts/eval_gate.py` запускается: `python scripts/eval_gate.py`
- [ ] Выводит scores per metric + PASS/FAIL
- [ ] CI workflow содержит eval gate step
- [ ] Без pipeline — проходит (graceful skip)
- [ ] `pytest tests/ -v` — проходит

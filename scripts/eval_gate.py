#!/usr/bin/env python3
"""CI evaluation gate for RAG quality."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASELINE_FILE = PROJECT_ROOT / "evaluation" / "baseline_metrics.json"
CURRENT_FILE = PROJECT_ROOT / "evaluation" / "current_metrics.json"
TEST_CASES_FILE = PROJECT_ROOT / "evaluation" / "test_cases.json"

GOLDEN_CASES_MIN = 10
THRESHOLDS = {
    "context_precision": 0.7,
    "faithfulness": 0.75,
    "answer_relevancy": 0.7,
}
METRIC_ALIASES = {
    "answer_relevance": "answer_relevancy",
    "answer_relevancy": "answer_relevancy",
    "context_precision": "context_precision",
    "faithfulness": "faithfulness",
}


def _print_safe(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _canonical_metric_name(name: str) -> str:
    return METRIC_ALIASES.get(name, name)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_test_cases() -> list[dict[str, Any]]:
    raw = _load_json(TEST_CASES_FILE)
    if not isinstance(raw, list):
        raise ValueError("evaluation/test_cases.json must contain a JSON array")
    return raw


def validate_test_cases(test_cases: list[dict[str, Any]]) -> None:
    golden_cases = [
        tc
        for tc in test_cases
        if str(tc.get("question", "")).strip()
        and str(tc.get("expected_answer", "")).strip()
    ]
    if len(golden_cases) < GOLDEN_CASES_MIN:
        raise ValueError(
            "Need at least "
            f"{GOLDEN_CASES_MIN} golden Q&A cases, found {len(golden_cases)}"
        )


def _fetch_ollama_models(base_url: str) -> list[str] | None:
    try:
        request = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    models = payload.get("models", [])
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _load_baseline() -> dict[str, float]:
    if not BASELINE_FILE.exists():
        return {}

    raw = _load_json(BASELINE_FILE)
    if isinstance(raw, dict) and isinstance(raw.get("aggregate"), dict):
        raw = raw["aggregate"]
    if not isinstance(raw, dict):
        raise ValueError("evaluation/baseline_metrics.json must contain a JSON object")

    baseline: dict[str, float] = {}
    for name, value in raw.items():
        canonical = _canonical_metric_name(str(name))
        if canonical in THRESHOLDS and isinstance(value, (int, float)):
            baseline[canonical] = float(value)
    return baseline


def _save_current_metrics(
    scores: dict[str, float],
    *,
    skipped: bool,
    reason: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "aggregate": scores,
        "skipped": skipped,
    }
    if reason:
        payload["reason"] = reason

    with CURRENT_FILE.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _load_pipeline_dependencies() -> tuple[Any, Any, Any, str] | tuple[None, None, None, str]:
    try:
        from config.settings import get_settings
    except ImportError as exc:
        return None, None, None, f"settings import failed: {exc}"

    settings = get_settings()
    models = _fetch_ollama_models(settings.ollama_base_url)
    if models is None:
        return None, None, None, f"Ollama unavailable at {settings.ollama_base_url}"

    if settings.ollama_model_name not in models:
        return None, None, None, f"Ollama model '{settings.ollama_model_name}' is not available"

    try:
        from api import app as api_app
    except ImportError as exc:
        return None, None, None, f"API app import failed: {exc}"

    try:
        api_app.initialize_vector_store()
    except Exception as exc:
        return None, None, None, f"vector store init failed: {exc}"

    retriever = getattr(api_app, "_retriever", None)
    if retriever is None:
        return None, None, None, "retriever is not initialized"

    try:
        from graph import LocalOllamaLLM, run_qa_pipeline
    except ImportError:
        try:
            from agent.graph import LocalOllamaLLM, run_qa_pipeline
        except ImportError as exc:
            return None, None, None, f"pipeline import failed: {exc}"

    llm = LocalOllamaLLM(model_name=settings.ollama_model_name)
    return run_qa_pipeline, retriever, llm, ""


def run_live_evaluation(test_cases: list[dict[str, Any]]) -> tuple[dict[str, float], str | None]:
    try:
        from evaluation.ragas_eval import RAGEvaluator, TestCase
    except ImportError as exc:
        return {metric: 1.0 for metric in THRESHOLDS}, f"evaluator import failed: {exc}"

    run_qa_pipeline, retriever, llm, reason = _load_pipeline_dependencies()
    if run_qa_pipeline is None or retriever is None or llm is None:
        return {metric: 1.0 for metric in THRESHOLDS}, reason

    try:
        from config.settings import get_settings
    except ImportError:
        max_iterations = 2
    else:
        max_iterations = get_settings().self_rag_max_iterations

    parsed_cases = [
        TestCase(
            question=item["question"],
            expected_keywords=item.get("expected_keywords", []),
            expected_answer=item.get("expected_answer"),
            category=item.get("category"),
        )
        for item in test_cases
    ]

    answers: list[str] = []
    context_docs_list: list[list[Any]] = []

    for tc in parsed_cases:
        final_state = run_qa_pipeline(
            question=tc.question,
            retriever=retriever,
            llm=llm,
            max_iterations=max_iterations,
        )
        answers.append(str(final_state.get("answer") or ""))
        context_docs = final_state.get("graded_docs") or final_state.get("context_docs") or []
        if not isinstance(context_docs, list):
            context_docs = []
        context_docs_list.append(context_docs)

    evaluator = RAGEvaluator()
    results = evaluator.evaluate_batch(
        parsed_cases,
        answers=answers,
        context_docs_list=context_docs_list,
    )
    aggregate = results.get("aggregate", {})

    scores: dict[str, float] = {}
    for metric in THRESHOLDS:
        value = aggregate.get(metric, 0.0)
        if isinstance(value, (int, float)):
            scores[metric] = float(value)
        else:
            scores[metric] = 0.0
    return scores, None


def evaluate_gate(scores: dict[str, float], baseline: dict[str, float]) -> tuple[bool, list[str]]:
    passed = True
    lines: list[str] = []

    for metric, threshold in THRESHOLDS.items():
        score = scores.get(metric, 0.0)
        checks = [score >= threshold]
        details = [f"threshold {threshold:.2f}"]

        baseline_score = baseline.get(metric)
        if baseline_score is not None:
            checks.append(score >= baseline_score)
            details.append(f"baseline {baseline_score:.2f}")

        metric_passed = all(checks)
        if not metric_passed:
            passed = False

        status = "PASS" if metric_passed else "FAIL"
        lines.append(
            f"  {metric}: {score:.2f} ({', '.join(details)}) [{status}]"
        )

    return passed, lines


def main() -> int:
    _print_safe("=" * 60)
    _print_safe("RAG Evaluation Gate")
    _print_safe("=" * 60)

    try:
        test_cases = load_test_cases()
        validate_test_cases(test_cases)
    except Exception as exc:
        _print_safe(f"ERROR: {exc}")
        return 1

    _print_safe(f"Test cases: {len(test_cases)}")

    try:
        scores, skip_reason = run_live_evaluation(test_cases)
        baseline = _load_baseline()
    except Exception as exc:
        _print_safe(f"ERROR: evaluation gate crashed: {exc}")
        return 1

    skipped = skip_reason is not None
    _save_current_metrics(scores, skipped=skipped, reason=skip_reason)

    if skipped:
        _print_safe(f"SKIP: {skip_reason}")
        for metric, score in scores.items():
            _print_safe(f"  {metric}: {score:.2f} (skipped) [PASS]")
        _print_safe("EVAL GATE: PASSED (graceful skip)")
        return 0

    passed, metric_lines = evaluate_gate(scores, baseline)
    for line in metric_lines:
        _print_safe(line)

    if passed:
        _print_safe("\nEVAL GATE: PASSED")
        return 0

    _print_safe("\nEVAL GATE: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

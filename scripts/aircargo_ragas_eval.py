# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.ragas_eval import RAGEvaluator, TestCase as RAGTestCase
from scripts.regression_eval import CuratedCase, load_curated_cases, sample_cases


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def expected_keywords_for_case(case: CuratedCase) -> list[str]:
    """Return the keyword set used by the RAGAS-style fallback metrics."""
    keywords = list(case.expected.answer_contains or [])
    for alternatives in case.expected.answer_contains_any or []:
        representative = next((item for item in alternatives if item), "")
        if representative:
            keywords.append(representative)
    return [item for item in keywords if item]


def _normalise_context_docs(raw_docs: Any) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if not raw_docs:
        return docs
    for doc in raw_docs:
        if hasattr(doc, "page_content"):
            docs.append(
                {
                    "page_content": doc.page_content,
                    "metadata": getattr(doc, "metadata", {}) or {},
                }
            )
        elif isinstance(doc, dict):
            page_content = doc.get("page_content")
            docs.append(
                {
                    "page_content": str(page_content if page_content is not None else doc),
                    "metadata": doc.get("metadata", {}) or {},
                }
            )
        else:
            docs.append({"page_content": str(doc), "metadata": {}})
    return docs


def _mock_pipeline_outputs(
    cases: Sequence[CuratedCase],
) -> tuple[list[str], list[list[dict[str, Any]]], list[dict[str, Any]]]:
    answers: list[str] = []
    contexts: list[list[dict[str, Any]]] = []
    runtime: list[dict[str, Any]] = []

    for case in cases:
        keywords = expected_keywords_for_case(case)
        answer = " ".join(keywords) if keywords else case.query
        context_text = f"{case.query}\n{answer}".strip()
        answers.append(answer)
        contexts.append(
            [
                {
                    "page_content": context_text,
                    "metadata": {"case_id": case.case_id, "tenant_id": case.tenant_id},
                }
            ]
        )
        runtime.append(
            {
                "case_id": case.case_id,
                "duration_ms": 0,
                "trace_id": f"mock-ragas-{case.case_id}",
            }
        )

    return answers, contexts, runtime


def _live_pipeline_outputs(
    cases: Sequence[CuratedCase],
    *,
    provider_target: str,
    project_root: Path,
) -> tuple[list[str], list[list[dict[str, Any]]], list[dict[str, Any]]]:
    from agent.graph import run_qa_pipeline
    from config.settings import get_settings
    from scripts.regression_eval import (
        _force_ollama_temperature_zero,
        _provider_target_runtime,
        _resolve_retriever,
    )

    answers: list[str] = []
    contexts: list[list[dict[str, Any]]] = []
    runtime: list[dict[str, Any]] = []
    retrievers: dict[str, Any] = {}

    with _provider_target_runtime(provider_target, project_root=project_root):
        settings = get_settings()
        max_iterations = int(getattr(settings, "self_rag_max_iterations", 2))
        with _force_ollama_temperature_zero():
            for case in cases:
                started_at = time.perf_counter()
                retriever = retrievers.get(case.tenant_id)
                if retriever is None:
                    retriever = _resolve_retriever(case.tenant_id)
                    retrievers[case.tenant_id] = retriever
                trace_id = f"ragas-aircargo-{uuid.uuid4()}"
                result = run_qa_pipeline(
                    question=case.query,
                    retriever=retriever,
                    llm=None,
                    max_iterations=max_iterations,
                    trace_id=trace_id,
                    tenant_id=case.tenant_id,
                )
                elapsed_ms = int(max((time.perf_counter() - started_at) * 1000, 0))
                answer = str(result.get("answer") or "")
                context_docs = _normalise_context_docs(
                    result.get("graded_docs") or result.get("context_docs") or []
                )
                answers.append(answer)
                contexts.append(context_docs)
                runtime.append(
                    {
                        "case_id": case.case_id,
                        "duration_ms": elapsed_ms,
                        "trace_id": str(result.get("trace_id") or trace_id),
                    }
                )

    return answers, contexts, runtime


def run_aircargo_ragas(
    cases: Sequence[CuratedCase],
    *,
    answers: Sequence[str],
    contexts: Sequence[Any],
    runtime: Sequence[dict[str, Any]],
    mode: str,
    provider_target: str,
    use_embeddings: bool = False,
) -> dict[str, Any]:
    evaluator = RAGEvaluator()
    rag_cases = [
        RAGTestCase(
            question=case.query,
            expected_keywords=expected_keywords_for_case(case),
            category=case.tenant_id,
        )
        for case in cases
    ]
    result = evaluator.evaluate_batch(
        rag_cases,
        answers=list(answers),
        context_docs_list=list(contexts),
        use_embeddings=use_embeddings,
    )

    runtime_by_case = {item.get("case_id"): item for item in runtime}
    for index, item in enumerate(result["per_question"]):
        case = cases[index]
        runtime_item = runtime_by_case.get(case.case_id, {})
        item["case_id"] = case.case_id
        item["tenant_id"] = case.tenant_id
        item["answer"] = answers[index] if index < len(answers) else ""
        docs = contexts[index] if index < len(contexts) else []
        item["context_docs_count"] = len(docs or [])
        item["duration_ms"] = runtime_item.get("duration_ms")
        item["trace_id"] = runtime_item.get("trace_id", "")

    result["mode"] = mode
    result["provider_target"] = provider_target
    return result


def render_markdown_report(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        f"# Aircargo RAGAS-style Eval - {report['run_id']}",
        "",
        f"- Created at: `{report['created_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Provider target: `{report['provider_target']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Tenant: `{report['tenant']}`",
        f"- Cases: `{report['num_cases']}`",
        "",
        "## Aggregate",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
    ]
    for metric_name in (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ):
        lines.append(f"| {metric_name} | {aggregate.get(metric_name, 0.0):.4f} |")

    lines.extend(["", "## Cases", ""])
    for item in report["per_question"]:
        scores = item["scores"]
        lines.extend(
            [
                f"### {item['case_id']}",
                f"- Question: {item['question']}",
                f"- Context docs: `{item['context_docs_count']}`",
                f"- Duration: `{item.get('duration_ms')}` ms",
                f"- Trace: `{item.get('trace_id') or 'n/a'}`",
                "- Scores: "
                f"faithfulness={scores['faithfulness']:.4f}, "
                f"answer_relevancy={scores['answer_relevancy']:.4f}, "
                f"context_precision={scores['context_precision']:.4f}, "
                f"context_recall={scores['context_recall']:.4f}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report_files(
    report: dict[str, Any],
    *,
    results_dir: Path,
) -> tuple[Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report['run_id']}-aircargo-ragas"
    json_path = results_dir / f"{stem}.json"
    markdown_path = results_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")
    return markdown_path, json_path


def _select_cases(args: argparse.Namespace) -> list[CuratedCase]:
    dataset_path = Path(args.dataset)
    cases = load_curated_cases(dataset_path)
    if args.tenant != "all":
        cases = [case for case in cases if case.tenant_id == args.tenant]
    return sample_cases(cases, max_cases=args.max_cases, seed=args.seed)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(PROJECT_ROOT / "evaluation" / "curated_cases_aircargo.jsonl"),
    )
    parser.add_argument("--tenant", default="aircargo")
    parser.add_argument("--max-cases", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--provider-target", default="ministral-3b-latest")
    parser.add_argument("--allow-paid-apis", action="store_true")
    parser.add_argument("--mock-runtime", action="store_true")
    parser.add_argument("--use-embedding-metric", action="store_true")
    parser.add_argument(
        "--results-dir",
        default=str(PROJECT_ROOT / "reports" / "ragas"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = _utc_now()

    try:
        cases = _select_cases(args)
        if not args.mock_runtime and not args.allow_paid_apis:
            raise RuntimeError(
                "live aircargo RAGAS requires --allow-paid-apis; "
                "use --mock-runtime for a no-provider smoke"
            )

        if args.mock_runtime:
            mode = "mock-ragas"
            answers, contexts, runtime = _mock_pipeline_outputs(cases)
        else:
            mode = "live-ragas"
            answers, contexts, runtime = _live_pipeline_outputs(
                cases,
                provider_target=args.provider_target,
                project_root=PROJECT_ROOT,
            )

        report = run_aircargo_ragas(
            cases,
            answers=answers,
            contexts=contexts,
            runtime=runtime,
            mode=mode,
            provider_target=args.provider_target,
            use_embeddings=args.use_embedding_metric,
        )
        report["run_id"] = _make_run_id(started_at)
        report["created_at"] = started_at.isoformat()
        report["dataset"] = str(Path(args.dataset))
        report["tenant"] = args.tenant

        markdown_path, json_path = write_report_files(
            report,
            results_dir=Path(args.results_dir),
        )
        payload = {
            "status": "ok",
            "run_id": report["run_id"],
            "mode": mode,
            "report_markdown": str(markdown_path),
            "report_json": str(json_path),
            "aggregate": report["aggregate"],
            "num_cases": report["num_cases"],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

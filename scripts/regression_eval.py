# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import random
import sqlite3
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class InfrastructureError(RuntimeError):
    pass


class CaseExpectation(BaseModel):
    model_config = ConfigDict(extra="allow")

    answer_contains: list[str] = Field(default_factory=list)
    answer_not_contains: list[str] = Field(default_factory=list)
    route: str | None = None
    min_quality: float | None = None
    min_factuality: float | None = None
    citations_min_count: int | None = None


class CuratedCase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    case_id: str
    tenant_id: str = Field(default="default", validation_alias=AliasChoices("tenant_id", "tenant"))
    query: str = Field(validation_alias=AliasChoices("query", "question"))
    expected: CaseExpectation = Field(default_factory=CaseExpectation)


class CaseRunResult(BaseModel):
    answer: str = ""
    quality_score: float = 0.0
    factuality_score: float = 0.0
    citations: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None
    cost_usd: float | None = None
    route: str = "unknown"
    trace_id: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "current"


def load_curated_cases(path: Path) -> list[CuratedCase]:
    cases: list[CuratedCase] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(CuratedCase.model_validate_json(line))
    return cases


def sample_cases(
    cases: Sequence[CuratedCase],
    *,
    max_cases: int | None = None,
    seed: int = 42,
) -> list[CuratedCase]:
    selected = list(cases)
    if max_cases is None or max_cases <= 0 or len(selected) <= max_cases:
        return selected
    rng = random.Random(seed)
    sampled = rng.sample(selected, max_cases)
    sampled.sort(key=lambda item: item.case_id)
    return sampled


def _evaluate_case_output(result: CaseRunResult, expected: CaseExpectation) -> tuple[bool, list[str]]:
    failures: list[str] = []

    if expected.route is not None and result.route != expected.route:
        failures.append(f"route expected '{expected.route}' but got '{result.route}'")

    if expected.min_quality is not None and result.quality_score < expected.min_quality:
        failures.append(
            f"quality {result.quality_score:g} below minimum {expected.min_quality:g}"
        )

    if expected.min_factuality is not None and result.factuality_score < expected.min_factuality:
        failures.append(
            f"factuality {result.factuality_score:g} below minimum {expected.min_factuality:g}"
        )

    if expected.citations_min_count is not None and len(result.citations) < expected.citations_min_count:
        failures.append(
            f"citations {len(result.citations)} below minimum {expected.citations_min_count}"
        )

    for needle in expected.answer_contains:
        if needle not in result.answer:
            failures.append(f"answer missing '{needle}'")

    for needle in expected.answer_not_contains:
        if needle in result.answer:
            failures.append(f"answer contains forbidden '{needle}'")

    return not failures, failures


def _build_diff(baseline: CaseRunResult, candidate: CaseRunResult) -> dict[str, Any]:
    return {
        "answer_changed": baseline.answer != candidate.answer,
        "quality_delta": round(candidate.quality_score - baseline.quality_score, 4),
        "factuality_delta": round(candidate.factuality_score - baseline.factuality_score, 4),
        "route_changed": baseline.route != candidate.route,
        "citations_delta": len(candidate.citations) - len(baseline.citations),
        "cost_delta": round((candidate.cost_usd or 0.0) - (baseline.cost_usd or 0.0), 6),
    }


def run_regression_cases(
    cases: Sequence[CuratedCase],
    *,
    baseline: str,
    candidate: str,
    executor: Callable[[CuratedCase, str], CaseRunResult],
    max_regressions: int,
    min_pass_rate: float,
    dataset_path: Path | None = None,
    tenant: str = "all",
    run_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _utc_now()
    report_run_id = run_id or _make_run_id(current_time)

    comparisons: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    new_passes: list[dict[str, Any]] = []

    baseline_passes = 0
    candidate_passes = 0

    for case in cases:
        baseline_result = executor(case, baseline)
        candidate_result = executor(case, candidate)

        baseline_passed, baseline_failures = _evaluate_case_output(baseline_result, case.expected)
        candidate_passed, candidate_failures = _evaluate_case_output(candidate_result, case.expected)

        baseline_passes += int(baseline_passed)
        candidate_passes += int(candidate_passed)

        outcome = "neutral"
        if baseline_passed and not candidate_passed:
            outcome = "regression"
        elif not baseline_passed and candidate_passed:
            outcome = "new_pass"

        case_payload = {
            "case_id": case.case_id,
            "tenant_id": case.tenant_id,
            "query": case.query,
            "baseline": baseline_result.model_dump(mode="json"),
            "candidate": candidate_result.model_dump(mode="json"),
            "baseline_passed": baseline_passed,
            "candidate_passed": candidate_passed,
            "baseline_failures": baseline_failures,
            "candidate_failures": candidate_failures,
            "diff": _build_diff(baseline_result, candidate_result),
            "outcome": outcome,
        }
        comparisons.append(case_payload)

        if outcome == "regression":
            regressions.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "baseline_answer": baseline_result.answer,
                    "candidate_answer": candidate_result.answer,
                    "why_failed": candidate_failures,
                }
            )
        elif outcome == "new_pass":
            new_passes.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "baseline_answer": baseline_result.answer,
                    "candidate_answer": candidate_result.answer,
                    "why_passed": ["candidate satisfies acceptance"] if candidate_passed else [],
                }
            )

    total_cases = len(comparisons)
    baseline_pass_rate = baseline_passes / total_cases if total_cases else 0.0
    candidate_pass_rate = candidate_passes / total_cases if total_cases else 0.0
    neutral_count = total_cases - len(regressions) - len(new_passes)

    gate_reasons: list[str] = []
    if len(regressions) > max_regressions:
        gate_reasons.append(
            f"max regressions exceeded: {len(regressions)} > {max_regressions}"
        )
    if candidate_pass_rate < min_pass_rate:
        gate_reasons.append(
            f"candidate pass rate {candidate_pass_rate:.2%} below minimum {min_pass_rate:.2%}"
        )
    if candidate_pass_rate + 1e-9 < baseline_pass_rate:
        gate_reasons.append(
            f"candidate pass rate {candidate_pass_rate:.2%} below baseline {baseline_pass_rate:.2%}"
        )

    gate_passed = not gate_reasons
    exit_code = 0 if gate_passed else 1

    return {
        "run_id": report_run_id,
        "created_at": current_time.isoformat(),
        "baseline": baseline,
        "candidate": candidate,
        "dataset": str(dataset_path) if dataset_path is not None else None,
        "tenant": tenant,
        "aggregate": {
            "total_cases": total_cases,
            "baseline_pass_rate": round(baseline_pass_rate, 4),
            "candidate_pass_rate": round(candidate_pass_rate, 4),
            "regressions": len(regressions),
            "new_passes": len(new_passes),
            "neutral": neutral_count,
        },
        "gate": {
            "passed": gate_passed,
            "max_regressions": max_regressions,
            "min_pass_rate": min_pass_rate,
            "reasons": gate_reasons,
        },
        "cases": comparisons,
        "regressions": regressions,
        "new_passes": new_passes,
        "exit_code": exit_code,
    }


def _render_summary_table(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    gate = report["gate"]
    return "\n".join(
        [
            "| Metric | Value |",
            "| --- | --- |",
            f"| Baseline | `{report['baseline']}` |",
            f"| Candidate | `{report['candidate']}` |",
            f"| Baseline pass rate | {aggregate['baseline_pass_rate']:.2%} |",
            f"| Candidate pass rate | {aggregate['candidate_pass_rate']:.2%} |",
            f"| Regressions | {aggregate['regressions']} |",
            f"| New passes | {aggregate['new_passes']} |",
            f"| Neutral | {aggregate['neutral']} |",
            f"| Gate | {'pass' if gate['passed'] else 'fail'} |",
        ]
    )


def _render_case_list(title: str, entries: list[dict[str, Any]], failure_key: str) -> list[str]:
    lines = [f"## {title}", ""]
    if not entries:
        lines.append("None.")
        return lines

    for entry in entries:
        lines.extend(
            [
                f"### {entry['case_id']}",
                f"- Query: {entry['query']}",
                f"- Baseline answer: {entry['baseline_answer']}",
                f"- Candidate answer: {entry['candidate_answer']}",
                f"- Detail: {'; '.join(entry[failure_key]) if entry[failure_key] else 'n/a'}",
                "",
            ]
        )
    return lines


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Regression Eval — {report['baseline']} vs {report['candidate']}",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Created at: `{report['created_at']}`",
        f"- Dataset: `{report['dataset'] or 'n/a'}`",
        f"- Tenant: `{report['tenant']}`",
        "",
        "## Summary",
        "",
        _render_summary_table(report),
        "",
    ]

    if report["gate"]["reasons"]:
        lines.extend(
            [
                "## Gate Reasons",
                "",
                *[f"- {reason}" for reason in report["gate"]["reasons"]],
                "",
            ]
        )

    lines.extend(_render_case_list("Regressions", report["regressions"], "why_failed"))
    lines.append("")
    lines.extend(_render_case_list("New Passes", report["new_passes"], "why_passed"))
    lines.append("")
    lines.extend(
        [
            "## Aggregate Metrics",
            "",
            f"- Total cases: {report['aggregate']['total_cases']}",
            f"- Baseline pass rate: {report['aggregate']['baseline_pass_rate']:.2%}",
            f"- Candidate pass rate: {report['aggregate']['candidate_pass_rate']:.2%}",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_report_files(
    report: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path, Path]:
    created_at = datetime.fromisoformat(report["created_at"])
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{timestamp}-{_slug(report['baseline'])}-vs-{_slug(report['candidate'])}"
    target_dir = project_root / "reports" / "regression"
    target_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = target_dir / f"{base_name}.md"
    json_path = target_dir / f"{base_name}.json"

    markdown_path.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return markdown_path, json_path


async def persist_regression_result(
    *,
    session_factory: Any,
    report: dict[str, Any],
    report_path: Path,
) -> None:
    from db.models import EvalResult

    aggregate = report["aggregate"]
    async with session_factory() as session:
        session.add(
            EvalResult(
                metric_name="regression_candidate_pass_rate",
                value=float(aggregate["candidate_pass_rate"]),
                sample_size=int(aggregate["total_cases"]),
                drift_alert=not bool(report["gate"]["passed"]),
                kind="regression",
                run_id=str(report["run_id"]),
                baseline_experiment_id=str(report["baseline"]),
                candidate_experiment_id=str(report["candidate"]),
                report_path=report_path.as_posix(),
            )
        )
        await session.commit()


def _reset_settings_cache() -> None:
    import config.settings as settings_module

    settings_module._settings = None


@contextmanager
def _force_ollama_temperature_zero():
    try:
        import langchain_community.llms as llm_module
        from langchain_community.llms import ollama as ollama_module
    except ImportError:
        yield
        return

    original_package_ollama = getattr(llm_module, "Ollama", None)
    original_module_ollama = getattr(ollama_module, "Ollama", None)
    if original_package_ollama is None or original_module_ollama is None:
        yield
        return

    class _DeterministicOllama(original_module_ollama):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("temperature", 0)
            super().__init__(*args, **kwargs)

    llm_module.Ollama = _DeterministicOllama
    ollama_module.Ollama = _DeterministicOllama
    try:
        yield
    finally:
        llm_module.Ollama = original_package_ollama
        ollama_module.Ollama = original_module_ollama


@contextmanager
def _experiment_runtime(
    experiment_id: str,
    *,
    project_root: Path = PROJECT_ROOT,
):
    import yaml

    import agent.prompt_registry as prompt_registry
    import config.settings as settings_module

    original_env = os.getenv("EXPERIMENT_ID")
    original_settings_path = settings_module.EXPERIMENT_OVERRIDE_PATH
    original_prompt_path = prompt_registry.EXPERIMENT_OVERRIDE_PATH
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        if experiment_id == "current":
            os.environ.pop("EXPERIMENT_ID", None)
            _reset_settings_cache()
            yield None
            return

        experiment_path = project_root / "evaluation" / "experiments" / f"{experiment_id}.yaml"
        if not experiment_path.exists():
            raise FileNotFoundError(f"experiment not found: {experiment_id}")

        payload = yaml.safe_load(experiment_path.read_text(encoding="utf-8")) or {}
        override_payload = {
            "experiment_id": experiment_id,
            "prompt_overrides": payload.get("prompt_overrides") or {},
            "settings_overrides": payload.get("settings_overrides") or {},
        }

        temp_dir = tempfile.TemporaryDirectory()
        override_path = Path(temp_dir.name) / "experiment_override.yaml"
        override_path.write_text(
            yaml.safe_dump(override_payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
            newline="\n",
        )

        os.environ["EXPERIMENT_ID"] = experiment_id
        settings_module.EXPERIMENT_OVERRIDE_PATH = override_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = override_path
        _reset_settings_cache()
        yield payload
    finally:
        if original_env is None:
            os.environ.pop("EXPERIMENT_ID", None)
        else:
            os.environ["EXPERIMENT_ID"] = original_env
        settings_module.EXPERIMENT_OVERRIDE_PATH = original_settings_path
        prompt_registry.EXPERIMENT_OVERRIDE_PATH = original_prompt_path
        _reset_settings_cache()
        if temp_dir is not None:
            temp_dir.cleanup()


def _resolve_retriever(tenant_id: str) -> Any:
    import api.app as api_app

    api_app.initialize_vector_store()

    if api_app._vector_store is not None and api_app._get_retriever is not None:
        retriever_params = inspect.signature(api_app._get_retriever).parameters
        kwargs: dict[str, Any] = {"chunks": api_app._chunks or None}
        if "tenant_id" in retriever_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in retriever_params.values()
        ):
            kwargs["tenant_id"] = tenant_id
        return api_app._get_retriever(api_app._vector_store, **kwargs)

    if api_app._retriever is not None:
        return api_app._retriever

    raise InfrastructureError("vector store is not initialized")


def _read_trace_metrics(trace_id: str) -> dict[str, Any]:
    from config.settings import get_settings

    details = {
        "duration_ms": None,
        "cost_usd": None,
    }

    db_path = Path(getattr(get_settings(), "tracing_db_path", ""))
    if not db_path.exists():
        return details

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT state_json, cost_usd
            FROM trace_steps
            WHERE trace_id = ?
            ORDER BY step_order ASC, id ASC
            """,
            (trace_id,),
        )
        for state_json, cost_usd in cur.fetchall():
            state: dict[str, Any] = {}
            if state_json:
                try:
                    state = json.loads(state_json)
                except (TypeError, ValueError, json.JSONDecodeError):
                    state = {}
            raw_duration = state.get("duration_ms")
            try:
                duration_ms = int(float(raw_duration)) if raw_duration is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            if duration_ms is not None:
                current = details["duration_ms"]
                details["duration_ms"] = duration_ms if current is None else max(current, duration_ms)
            if cost_usd is not None:
                details["cost_usd"] = float(cost_usd)

    return details


def _normalize_result(payload: dict[str, Any]) -> CaseRunResult:
    trace_id = str(payload.get("trace_id") or "")
    trace_metrics = _read_trace_metrics(trace_id) if trace_id else {"duration_ms": None, "cost_usd": None}

    citations = payload.get("citations") or []
    if not citations:
        docs = payload.get("graded_docs") or payload.get("context_docs") or []
        citations = []
        for index, doc in enumerate(docs, start=1):
            if not isinstance(doc, dict):
                continue
            metadata = doc.get("metadata", {}) or {}
            citations.append(
                {
                    "index": index,
                    "doc_id": str(
                        metadata.get("doc_id")
                        or metadata.get("id")
                        or metadata.get("source")
                        or f"doc_{index}"
                    ),
                    "title": str(
                        metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("doc_id")
                        or f"doc_{index}"
                    ),
                    "excerpt": str(doc.get("page_content") or "")[:300],
                }
            )

    return CaseRunResult(
        answer=str(payload.get("answer") or ""),
        quality_score=float(payload.get("quality_score") or 0.0),
        factuality_score=float(payload.get("factuality_score") or 0.0),
        citations=[item for item in citations if isinstance(item, dict)],
        duration_ms=trace_metrics["duration_ms"],
        cost_usd=trace_metrics["cost_usd"],
        route=str(payload.get("route") or "unknown"),
        trace_id=trace_id,
    )


def execute_case_with_runtime(
    case: CuratedCase,
    experiment_id: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> CaseRunResult:
    from agent.graph import run_qa_pipeline
    from config.settings import get_settings

    with _experiment_runtime(experiment_id, project_root=project_root), _force_ollama_temperature_zero():
        retriever = _resolve_retriever(case.tenant_id)
        result = run_qa_pipeline(
            question=case.query,
            retriever=retriever,
            llm=None,
            max_iterations=int(getattr(get_settings(), "self_rag_max_iterations", 2)),
            trace_id=f"regression-{uuid.uuid4()}",
            tenant_id=case.tenant_id,
        )
    return _normalize_result(result)


def run_regression(
    *,
    baseline: str,
    candidate: str,
    dataset_path: Path,
    tenant: str = "all",
    max_cases: int | None = None,
    seed: int = 42,
    max_regressions: int | None = None,
    min_pass_rate: float | None = None,
    project_root: Path = PROJECT_ROOT,
    executor: Callable[[CuratedCase, str], CaseRunResult] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    from config.settings import get_settings

    settings = get_settings()
    gate_max_regressions = (
        int(max_regressions)
        if max_regressions is not None
        else int(getattr(settings, "regression_gate_max_regressions", 2))
    )
    gate_min_pass_rate = (
        float(min_pass_rate)
        if min_pass_rate is not None
        else float(getattr(settings, "regression_gate_min_pass_rate", 0.85))
    )

    cases = load_curated_cases(dataset_path)
    if tenant != "all":
        cases = [case for case in cases if case.tenant_id == tenant]
    cases = sample_cases(cases, max_cases=max_cases, seed=seed)

    selected_executor = executor or (
        lambda case, experiment_id: execute_case_with_runtime(
            case,
            experiment_id,
            project_root=project_root,
        )
    )
    return run_regression_cases(
        cases,
        baseline=baseline,
        candidate=candidate,
        executor=selected_executor,
        max_regressions=gate_max_regressions,
        min_pass_rate=gate_min_pass_rate,
        dataset_path=dataset_path,
        tenant=tenant,
        now=now,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--dataset",
        default=str(PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"),
    )
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    from db.engine import async_session
    from monitoring.prometheus import (
        record_regression_run,
        set_regression_last_pass_rate,
    )

    args = parse_args(argv)
    started_at = _utc_now()
    try:
        report = run_regression(
            baseline=args.baseline,
            candidate=args.candidate,
            dataset_path=Path(args.dataset),
            tenant=args.tenant,
            max_cases=args.max_cases,
            seed=args.seed,
        )
        markdown_path, json_path = write_report_files(report)
        asyncio.run(
            persist_regression_result(
                session_factory=async_session,
                report=report,
                report_path=json_path.relative_to(PROJECT_ROOT),
            )
        )

        duration_sec = max((_utc_now() - started_at).total_seconds(), 0.0)
        record_regression_run("pass" if report["gate"]["passed"] else "fail", duration_sec)
        set_regression_last_pass_rate(
            report["baseline"],
            report["candidate"],
            float(report["aggregate"]["candidate_pass_rate"]),
        )

        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "exit_code": report["exit_code"],
                    "report_markdown": str(markdown_path.relative_to(PROJECT_ROOT)),
                    "report_json": str(json_path.relative_to(PROJECT_ROOT)),
                    "aggregate": report["aggregate"],
                    "gate": report["gate"],
                },
                ensure_ascii=False,
            )
        )
        return int(report["exit_code"])
    except Exception as exc:
        duration_sec = max((_utc_now() - started_at).total_seconds(), 0.0)
        record_regression_run("fail", duration_sec)
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

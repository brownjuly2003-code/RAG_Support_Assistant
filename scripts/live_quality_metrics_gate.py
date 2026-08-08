#!/usr/bin/env python3
"""Plan §5.5: live quality metrics gate scaffold (×3 DoD thresholds).

Plan §5 verification requires repeated runs with confidence intervals:

- context precision ≥ 0.63
- context recall ≥ 0.97
- FULL ≥ 97% (full_rate ≥ 0.97)
- MISS ≤ 1
- faithfulness ≥ 0.90
- answer relevancy ≥ 0.92
- unverified auto-rate = 0
- **minimum three** repeated runs

This module is a **scaffold** (mirrors §7.6 live provider gate):

- ``readiness`` / ``command`` — no live calls; never claim release PASS
- ``live`` — requires ``RAG_LIVE_QUALITY_METRICS_GATE`` / ``--live`` + provider
  secrets; optional ``--execute`` runs multi-seed regression_eval without mock

Default modes never place paid provider calls and never set ``release_passed``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "regression"
OPT_IN_ENV = "RAG_LIVE_QUALITY_METRICS_GATE"

PROVIDER_SECRET_ENVS = (
    "MISTRAL_API_KEY",
    "GRACEKELLY_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

FORBIDDEN_LIVE_FLAGS = frozenset({"--mock-experiment-runtime"})
REQUIRED_LIVE_FLAGS = (
    "--release-gate",
    "--allow-paid-apis",
    "--no-persist",
)

# Plan §5 DoD floors (behavioral evidence; local scaffold enforces structure).
MIN_RUNS = 3
PLAN_THRESHOLDS: dict[str, float] = {
    "context_precision": 0.63,
    "context_recall": 0.97,
    "full_rate": 0.97,  # FULL ≥ 97%
    "miss_count_max": 1.0,  # MISS ≤ 1 (max allowed)
    "faithfulness": 0.90,
    "answer_relevancy": 0.92,
    "unverified_auto_rate": 0.0,
}

# Metrics aggregated as means (higher is better except miss/unverified).
_MEAN_HIGHER_IS_BETTER = (
    "context_precision",
    "context_recall",
    "full_rate",
    "faithfulness",
    "answer_relevancy",
)
_MEAN_LOWER_IS_BETTER = (
    "miss_count",
    "unverified_auto_rate",
)
_ALL_METRIC_KEYS = _MEAN_HIGHER_IS_BETTER + _MEAN_LOWER_IS_BETTER


@dataclass
class LiveQualityMetricsReadiness:
    """Structured readiness / policy result (never a silent release PASS)."""

    mode: str
    opt_in: bool
    live_requested: bool
    dataset_present: bool
    dataset_path: str
    min_runs: int = MIN_RUNS
    runs: int = MIN_RUNS
    provider_secrets_present: list[str] = field(default_factory=list)
    provider_secrets_missing_all: bool = True
    commands: list[list[str]] = field(default_factory=list)
    policy_ok: bool = False
    release_eligible_to_attempt: bool = False
    verdict: str = "NOT_RUN"
    release_passed: bool = False
    evidence_valid: bool = False
    reasons: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""
    thresholds: dict[str, float] = field(default_factory=lambda: dict(PLAN_THRESHOLDS))
    aggregate: dict[str, Any] | None = None
    dod_result: dict[str, Any] | None = None

    def to_report(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = "live-quality-metrics-gate"
        payload["schema_version"] = 1
        payload["gate"] = {
            "verdict": self.verdict,
            "passed": False,  # scaffold never claims release PASS by itself
            "release_passed": self.release_passed,
            "evidence_valid": self.evidence_valid,
            "reasons": list(self.reasons),
        }
        if self.dod_result is not None and self.evidence_valid:
            # Only when real multi-run evidence was evaluated.
            payload["gate"]["passed"] = bool(self.dod_result.get("passed"))
            payload["gate"]["dod_reasons"] = list(self.dod_result.get("reasons") or [])
        return payload


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def is_live_opt_in(
    *,
    env: dict[str, str] | None = None,
    cli_live: bool = False,
) -> bool:
    source = env if env is not None else os.environ
    raw = str(source.get(OPT_IN_ENV, "") or "").strip().lower()
    env_on = raw in {"1", "true", "yes", "on"}
    return bool(cli_live or env_on)


def detect_provider_secrets(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    present: list[str] = []
    for name in PROVIDER_SECRET_ENVS:
        value = str(source.get(name, "") or "").strip()
        if value and value.lower() not in {"changeme", "change-me", "change_me"}:
            present.append(name)
    return present


def build_live_metrics_commands(
    *,
    runs: int = MIN_RUNS,
    baseline: str = "current",
    candidate: str = "current",
    dataset: Path | str = DEFAULT_DATASET,
    max_cases: int = 20,
    base_seed: int = 42,
    baseline_artifact: Path | str | None = None,
    require_baseline_artifact: bool = False,
    tenant: str = "all",
) -> list[list[str]]:
    """Build N release-honest live regression argv lists (distinct seeds)."""
    n = max(1, int(runs))
    commands: list[list[str]] = []
    for i in range(n):
        seed = int(base_seed) + i
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "regression_eval.py"),
            "--baseline",
            baseline,
            "--candidate",
            candidate,
            "--dataset",
            str(dataset),
            "--tenant",
            tenant,
            "--max-cases",
            str(int(max_cases)),
            "--seed",
            str(seed),
            *REQUIRED_LIVE_FLAGS,
        ]
        if baseline_artifact is not None and str(baseline_artifact).strip():
            cmd.extend(["--baseline-artifact", str(baseline_artifact)])
            if require_baseline_artifact:
                cmd.append("--require-baseline-artifact")
        assert "--mock-experiment-runtime" not in cmd
        commands.append(cmd)
    return commands


def validate_live_command(cmd: Sequence[str]) -> list[str]:
    reasons: list[str] = []
    joined = list(cmd)
    for bad in FORBIDDEN_LIVE_FLAGS:
        if bad in joined:
            reasons.append(f"forbidden flag for live gate: {bad}")
    for required in REQUIRED_LIVE_FLAGS:
        if required not in joined:
            reasons.append(f"missing required live flag: {required}")
    return reasons


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _normalize_run_metrics(raw: Mapping[str, Any]) -> dict[str, float | None]:
    """Map a single run dict to canonical metric keys."""
    # Accept common aliases from offline reports.
    aliases = {
        "context_precision": ("context_precision", "precision"),
        "context_recall": ("context_recall", "recall"),
        "full_rate": ("full_rate", "full", "FULL"),
        "miss_count": ("miss_count", "miss", "MISS"),
        "faithfulness": ("faithfulness",),
        "answer_relevancy": ("answer_relevancy", "answer_relevance", "relevancy"),
        "unverified_auto_rate": (
            "unverified_auto_rate",
            "unverified_auto",
            "auto_unverified_rate",
        ),
    }
    out: dict[str, float | None] = {}
    for canonical, keys in aliases.items():
        found: float | None = None
        for key in keys:
            if key in raw:
                found = _to_float(raw.get(key))
                break
        # FULL may be percent (97) rather than rate (0.97).
        if canonical == "full_rate" and found is not None and found > 1.0:
            found = found / 100.0
        out[canonical] = found
    return out


def aggregate_metric_runs(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate multi-run metrics: means + simple 95% CI half-width (t≈1.96)."""
    normalized = [_normalize_run_metrics(r) for r in runs]
    n = len(normalized)
    means: dict[str, float | None] = {}
    stdevs: dict[str, float | None] = {}
    ci_half: dict[str, float | None] = {}
    series: dict[str, list[float]] = {k: [] for k in _ALL_METRIC_KEYS}

    for row in normalized:
        for key in _ALL_METRIC_KEYS:
            value = row.get(key)
            if value is not None:
                series[key].append(float(value))

    for key in _ALL_METRIC_KEYS:
        values = series[key]
        if not values:
            means[key] = None
            stdevs[key] = None
            ci_half[key] = None
            continue
        mean = sum(values) / len(values)
        means[key] = round(mean, 6)
        if len(values) >= 2:
            var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            sd = math.sqrt(var)
            stdevs[key] = round(sd, 6)
            # Normal approx; honest for scaffold reporting (n small → wide CI).
            half = 1.96 * sd / math.sqrt(len(values))
            ci_half[key] = round(half, 6)
        else:
            stdevs[key] = 0.0
            ci_half[key] = None

    return {
        "n_runs": n,
        "min_runs": MIN_RUNS,
        "min_runs_met": n >= MIN_RUNS,
        "means": means,
        "stdevs": stdevs,
        "ci95_half_width": ci_half,
        "per_run": normalized,
    }


def evaluate_aggregate_against_dod(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed DoD check against plan §5 thresholds."""
    reasons: list[str] = []
    n = int(aggregate.get("n_runs") or 0)
    if n < MIN_RUNS:
        reasons.append(f"min_runs not met: n_runs={n} < {MIN_RUNS}")

    means = aggregate.get("means") if isinstance(aggregate.get("means"), Mapping) else {}
    thr = PLAN_THRESHOLDS

    def _mean(key: str) -> float | None:
        return _to_float(means.get(key)) if isinstance(means, Mapping) else None

    higher_better = (
        ("context_precision", thr["context_precision"]),
        ("context_recall", thr["context_recall"]),
        ("full_rate", thr["full_rate"]),
        ("faithfulness", thr["faithfulness"]),
        ("answer_relevancy", thr["answer_relevancy"]),
    )
    for name, floor in higher_better:
        value = _mean(name)
        if value is None:
            reasons.append(f"{name} missing from aggregate means")
            continue
        if value < float(floor):
            reasons.append(f"{name} {value} below floor {floor}")

    miss = _mean("miss_count")
    if miss is None:
        reasons.append("miss_count missing from aggregate means")
    elif miss > thr["miss_count_max"]:
        reasons.append(
            f"miss_count {miss} exceeds max {thr['miss_count_max']}"
        )

    uar = _mean("unverified_auto_rate")
    if uar is None:
        reasons.append("unverified_auto_rate missing from aggregate means")
    elif uar > thr["unverified_auto_rate"] + 1e-12:
        reasons.append(
            f"unverified_auto_rate {uar} must be == {thr['unverified_auto_rate']}"
        )

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "thresholds": dict(thr),
        "n_runs": n,
        "min_runs": MIN_RUNS,
    }


def assess_readiness(
    *,
    mode: str = "readiness",
    live_requested: bool = False,
    env: dict[str, str] | None = None,
    dataset: Path | str = DEFAULT_DATASET,
    max_cases: int = 20,
    runs: int = MIN_RUNS,
    base_seed: int = 42,
    baseline_artifact: Path | str | None = None,
    require_baseline_artifact: bool = False,
    baseline: str = "current",
    candidate: str = "current",
) -> LiveQualityMetricsReadiness:
    """Assess whether a live multi-run quality metrics gate may be attempted."""
    dataset_path = Path(dataset)
    opt_in = is_live_opt_in(env=env, cli_live=live_requested)
    secrets = detect_provider_secrets(env)
    n_runs = max(1, int(runs))
    commands = build_live_metrics_commands(
        runs=n_runs,
        baseline=baseline,
        candidate=candidate,
        dataset=dataset_path,
        max_cases=max_cases,
        base_seed=base_seed,
        baseline_artifact=baseline_artifact,
        require_baseline_artifact=require_baseline_artifact,
    )
    policy_reasons: list[str] = []
    for cmd in commands:
        policy_reasons.extend(validate_live_command(cmd))
    # de-dupe while preserving order
    seen: set[str] = set()
    deduped_policy: list[str] = []
    for reason in policy_reasons:
        if reason not in seen:
            seen.add(reason)
            deduped_policy.append(reason)

    reasons: list[str] = list(deduped_policy)
    dataset_ok = dataset_path.is_file()
    if not dataset_ok:
        reasons.append(f"dataset missing: {dataset_path}")
    if n_runs < MIN_RUNS:
        reasons.append(f"configured runs={n_runs} < plan min_runs={MIN_RUNS}")

    if not opt_in:
        reasons.append(
            f"live opt-in off ({OPT_IN_ENV} not set / --live not passed); "
            "no live quality metric runs"
        )

    if opt_in and not secrets:
        reasons.append(
            "live opt-in set but no provider API keys present "
            f"(checked: {', '.join(PROVIDER_SECRET_ENVS)})"
        )

    policy_ok = not deduped_policy and dataset_ok and n_runs >= MIN_RUNS
    can_attempt = bool(opt_in and secrets and policy_ok)

    if not opt_in:
        verdict = "SKIPPED_NO_OPT_IN"
    elif not secrets:
        verdict = "FAIL_NO_CREDENTIALS"
    elif not dataset_ok:
        verdict = "FAIL_MISSING_DATASET"
    elif n_runs < MIN_RUNS:
        verdict = "FAIL_MIN_RUNS"
    elif deduped_policy:
        verdict = "FAIL_POLICY"
    elif mode in {"readiness", "command"}:
        verdict = "READY_NOT_EXECUTED"
    else:
        verdict = "READY"

    return LiveQualityMetricsReadiness(
        mode=mode,
        opt_in=opt_in,
        live_requested=live_requested,
        dataset_present=dataset_ok,
        dataset_path=str(dataset_path),
        min_runs=MIN_RUNS,
        runs=n_runs,
        provider_secrets_present=secrets,
        provider_secrets_missing_all=not bool(secrets),
        commands=commands,
        policy_ok=policy_ok,
        release_eligible_to_attempt=can_attempt,
        verdict=verdict,
        release_passed=False,
        evidence_valid=False,
        reasons=reasons,
        notes=(
            "Scaffold only: readiness/command never claim release PASS. "
            f"Plan §5 DoD needs ≥{MIN_RUNS} live runs with CI thresholds; "
            "execute path runs multi-seed regression_eval without mock."
        ),
        created_at=_utc_now_iso(),
        thresholds=dict(PLAN_THRESHOLDS),
    )


def write_report(report: dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def run_live_subprocess(cmd: Sequence[str], *, cwd: Path = PROJECT_ROOT) -> int:
    completed = subprocess.run(list(cmd), cwd=str(cwd), check=False)
    return int(completed.returncode)


def load_run_metrics_file(path: Path) -> dict[str, Any]:
    """Load a single-run metrics JSON (aggregate or flat)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("aggregate"), dict):
        return dict(raw["aggregate"])
    if isinstance(raw, dict):
        return dict(raw)
    raise ValueError(f"metrics file must be a JSON object: {path}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan §5.5 live quality metrics gate scaffold "
            "(opt-in live multi-run; default readiness)."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("readiness", "command", "live", "evaluate-report"),
        default="readiness",
        help=(
            "readiness=check only; command=print argv; live=opt-in execute; "
            "evaluate-report=score existing multi-run JSONL/JSON without live calls"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=f"Request live execution (also set by {OPT_IN_ENV}=1)",
    )
    parser.add_argument("--baseline", default="current")
    parser.add_argument("--candidate", default="current")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--max-cases", type=int, default=20)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument(
        "--runs",
        type=int,
        default=MIN_RUNS,
        help=f"Number of repeated runs (plan min={MIN_RUNS})",
    )
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--baseline-artifact", default=None)
    parser.add_argument(
        "--require-baseline-artifact",
        action="store_true",
    )
    parser.add_argument(
        "--write-report",
        default=None,
        help="Write JSON readiness/result report path",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="With --mode live, actually subprocess multi-run regression_eval",
    )
    parser.add_argument(
        "--metrics-runs",
        default=None,
        help=(
            "For evaluate-report: path to JSON list of per-run metric objects, "
            "or a directory of *.json run files"
        ),
    )
    return parser.parse_args(argv)


def _load_metrics_runs_arg(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.json"))
        return [load_run_metrics_file(f) for f in files]
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("runs"), list):
        return [dict(item) for item in raw["runs"] if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    raise ValueError(f"unsupported metrics payload: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    live_requested = bool(args.live or args.mode == "live")

    # Offline DoD evaluation of operator-supplied multi-run metrics.
    if args.mode == "evaluate-report":
        if not args.metrics_runs:
            print(
                "evaluate-report requires --metrics-runs path",
                file=sys.stderr,
            )
            return 2
        try:
            run_rows = _load_metrics_runs_arg(Path(args.metrics_runs))
        except Exception as exc:  # noqa: BLE001
            print(f"failed to load metrics runs: {exc}", file=sys.stderr)
            return 2
        aggregate = aggregate_metric_runs(run_rows)
        dod = evaluate_aggregate_against_dod(aggregate)
        readiness = LiveQualityMetricsReadiness(
            mode="evaluate-report",
            opt_in=False,
            live_requested=False,
            dataset_present=True,
            dataset_path=str(args.dataset),
            min_runs=MIN_RUNS,
            runs=int(aggregate["n_runs"]),
            commands=[],
            policy_ok=True,
            release_eligible_to_attempt=False,
            verdict="DOD_PASS" if dod["passed"] else "DOD_FAIL",
            release_passed=bool(dod["passed"]),
            evidence_valid=True,
            reasons=list(dod["reasons"]),
            notes=(
                "Offline multi-run DoD evaluation only — not a live provider "
                "execution. release_passed reflects §5 floors on supplied runs."
            ),
            created_at=_utc_now_iso(),
            thresholds=dict(PLAN_THRESHOLDS),
            aggregate=aggregate,
            dod_result=dod,
        )
        report = readiness.to_report()
        # evaluate-report *does* surface DoD pass in gate.passed when evidence valid.
        report["gate"]["passed"] = bool(dod["passed"])
        report["gate"]["release_passed"] = bool(dod["passed"])
        report["release_passed"] = bool(dod["passed"])
        if args.write_report:
            write_report(report, Path(args.write_report))
        print(json.dumps(report["gate"], ensure_ascii=False, indent=2))
        return 0 if dod["passed"] else 1

    readiness = assess_readiness(
        mode=args.mode,
        live_requested=live_requested,
        dataset=args.dataset,
        max_cases=args.max_cases,
        runs=args.runs,
        base_seed=args.base_seed,
        baseline_artifact=args.baseline_artifact,
        require_baseline_artifact=args.require_baseline_artifact,
        baseline=args.baseline,
        candidate=args.candidate,
    )

    if args.mode == "command":
        for i, cmd in enumerate(readiness.commands):
            print(f"# run {i + 1}/{len(readiness.commands)}")
            print(" ".join(cmd))

    exit_code = 0
    if args.mode == "live":
        if not readiness.release_eligible_to_attempt:
            exit_code = 1
        elif args.execute:
            # Execute multi-run; DoD aggregation of live outputs is residual
            # (regression_eval report parse) — scaffold records exit codes only.
            run_exits: list[int] = []
            for cmd in readiness.commands:
                run_exits.append(run_live_subprocess(cmd))
            readiness.notes += f" executed_exit_codes={run_exits}"
            if any(code != 0 for code in run_exits):
                readiness.verdict = "LIVE_EXECUTED_FAIL"
                readiness.reasons.append(f"one or more runs failed: {run_exits}")
                exit_code = 1
            else:
                readiness.verdict = "LIVE_EXECUTED_NO_DOD_PARSE"
                readiness.reasons.append(
                    "all subprocesses exited 0; multi-run metric parse/DoD "
                    "still requires evaluate-report with per-run metric files"
                )
                # Not release_passed: no parsed metrics evidence.
                exit_code = 0
        else:
            readiness.verdict = "READY_NOT_EXECUTED"
            readiness.reasons.append(
                "live eligible but --execute not set; no provider calls made"
            )

    report = readiness.to_report()
    if args.write_report:
        write_report(report, Path(args.write_report))
    else:
        # Always emit a compact gate summary on stdout for CI logs.
        print(
            json.dumps(
                {
                    "kind": report["kind"],
                    "verdict": report["gate"]["verdict"],
                    "release_passed": report["release_passed"],
                    "min_runs": report["min_runs"],
                    "runs": report["runs"],
                    "reasons": report["reasons"][:5],
                },
                ensure_ascii=False,
            )
        )

    if args.mode == "readiness":
        return 0
    if args.mode == "command":
        return 0
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan §7.6: scheduled live provider / independent-judge gate scaffold.

PR CI keeps mock smoke (not release evidence). This module defines the *separate*
live path: explicit opt-in, no ``--mock-experiment-runtime``, ``--release-gate``
required, paid/live APIs allowed only when credentials exist.

Default modes never place live provider calls:

- ``readiness`` — check paths, policy, opt-in flags; write a report that is
  explicitly **not** release evidence.
- ``command`` — print the argv that would run (still no subprocess).
- ``live`` — only with ``RAG_LIVE_PROVIDER_GATE=1`` / ``--live``; fail-closed if
  credentials missing; optionally executes regression_eval (still requires opt-in).

Live execution of real providers remains operator opt-in and is never the default
for schedule without secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "regression"
OPT_IN_ENV = "RAG_LIVE_PROVIDER_GATE"
# Env vars commonly used for paid/live providers (presence only; never log values).
PROVIDER_SECRET_ENVS = (
    "MISTRAL_API_KEY",
    "GRACEKELLY_API_KEY",
    "OPENCODE_ZEN_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

FORBIDDEN_LIVE_FLAGS = frozenset(
    {
        "--mock-experiment-runtime",
    }
)
REQUIRED_LIVE_FLAGS = (
    "--release-gate",
    "--allow-paid-apis",
    "--no-persist",
)


@dataclass
class LiveGateReadiness:
    """Structured readiness / policy result (never a silent release PASS)."""

    mode: str
    opt_in: bool
    live_requested: bool
    dataset_present: bool
    dataset_path: str
    provider_secrets_present: list[str] = field(default_factory=list)
    provider_secrets_missing_all: bool = True
    command: list[str] = field(default_factory=list)
    policy_ok: bool = False
    release_eligible_to_attempt: bool = False
    verdict: str = "NOT_RUN"
    release_passed: bool = False
    evidence_valid: bool = False
    reasons: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""

    def to_report(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = "live-provider-gate"
        payload["schema_version"] = 1
        payload["gate"] = {
            "verdict": self.verdict,
            "passed": False,  # scaffold never claims release PASS by itself
            "release_passed": self.release_passed,
            "evidence_valid": self.evidence_valid,
            "reasons": list(self.reasons),
        }
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


def build_live_regression_command(
    *,
    baseline: str = "current",
    candidate: str = "current",
    dataset: Path | str = DEFAULT_DATASET,
    max_cases: int = 20,
    seed: int = 42,
    baseline_artifact: Path | str | None = None,
    require_baseline_artifact: bool = False,
    tenant: str = "all",
) -> list[str]:
    """Build argv for a release-honest live regression (no mock flag)."""
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
        str(int(seed)),
        *REQUIRED_LIVE_FLAGS,
    ]
    if baseline_artifact is not None and str(baseline_artifact).strip():
        cmd.extend(["--baseline-artifact", str(baseline_artifact)])
        if require_baseline_artifact:
            cmd.append("--require-baseline-artifact")
    # Policy guard: never inject mock.
    assert "--mock-experiment-runtime" not in cmd
    return cmd


def validate_live_command(cmd: Sequence[str]) -> list[str]:
    """Return policy violation reasons (empty if command is live-legal)."""
    reasons: list[str] = []
    joined = list(cmd)
    for bad in FORBIDDEN_LIVE_FLAGS:
        if bad in joined:
            reasons.append(f"forbidden flag for live gate: {bad}")
    for required in REQUIRED_LIVE_FLAGS:
        if required not in joined:
            reasons.append(f"missing required live flag: {required}")
    return reasons


def assess_readiness(
    *,
    mode: str = "readiness",
    live_requested: bool = False,
    env: dict[str, str] | None = None,
    dataset: Path | str = DEFAULT_DATASET,
    max_cases: int = 20,
    baseline_artifact: Path | str | None = None,
    require_baseline_artifact: bool = False,
    baseline: str = "current",
    candidate: str = "current",
) -> LiveGateReadiness:
    """Assess whether a live release gate may be attempted."""
    dataset_path = Path(dataset)
    opt_in = is_live_opt_in(env=env, cli_live=live_requested)
    secrets = detect_provider_secrets(env)
    cmd = build_live_regression_command(
        baseline=baseline,
        candidate=candidate,
        dataset=dataset_path,
        max_cases=max_cases,
        baseline_artifact=baseline_artifact,
        require_baseline_artifact=require_baseline_artifact,
    )
    policy_reasons = validate_live_command(cmd)
    reasons: list[str] = list(policy_reasons)
    dataset_ok = dataset_path.is_file()
    if not dataset_ok:
        reasons.append(f"dataset missing: {dataset_path}")

    if not opt_in:
        reasons.append(
            f"live opt-in off ({OPT_IN_ENV} not set / --live not passed); "
            "no live provider calls"
        )

    if opt_in and not secrets:
        reasons.append(
            "live opt-in set but no provider API keys present "
            f"(checked: {', '.join(PROVIDER_SECRET_ENVS)})"
        )

    policy_ok = not policy_reasons and dataset_ok
    can_attempt = bool(opt_in and secrets and policy_ok)

    if not opt_in:
        verdict = "SKIPPED_NO_OPT_IN"
    elif not secrets:
        verdict = "FAIL_NO_CREDENTIALS"
    elif not dataset_ok:
        verdict = "FAIL_MISSING_DATASET"
    elif policy_reasons:
        verdict = "FAIL_POLICY"
    elif mode in {"readiness", "command"}:
        verdict = "READY_NOT_EXECUTED"
    else:
        verdict = "READY"

    return LiveGateReadiness(
        mode=mode,
        opt_in=opt_in,
        live_requested=live_requested,
        dataset_present=dataset_ok,
        dataset_path=str(dataset_path),
        provider_secrets_present=secrets,
        provider_secrets_missing_all=not bool(secrets),
        command=cmd,
        policy_ok=policy_ok,
        release_eligible_to_attempt=can_attempt,
        verdict=verdict,
        release_passed=False,
        evidence_valid=False,
        reasons=reasons,
        notes=(
            "Scaffold only: readiness/command never claim release PASS. "
            "Live mode requires opt-in + credentials and still uses "
            "regression_eval --release-gate without mock."
        ),
        created_at=_utc_now_iso(),
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
    """Execute the live regression command (opt-in path only)."""
    completed = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        check=False,
    )
    return int(completed.returncode)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan §7.6 live provider gate scaffold (opt-in live; default readiness)."
    )
    parser.add_argument(
        "--mode",
        choices=("readiness", "command", "live"),
        default="readiness",
        help="readiness=check only; command=print argv; live=opt-in execute",
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tenant", default="all")
    parser.add_argument("--baseline-artifact", default=None)
    parser.add_argument(
        "--require-baseline-artifact",
        action="store_true",
        help="Pass through to regression_eval when baseline artifact is set",
    )
    parser.add_argument(
        "--write-report",
        default=None,
        help="Write JSON readiness/result report path",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="With --mode live, actually subprocess regression_eval (still needs opt-in+keys)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    live_requested = bool(args.live or args.mode == "live")
    readiness = assess_readiness(
        mode=args.mode,
        live_requested=live_requested,
        dataset=args.dataset,
        max_cases=args.max_cases,
        baseline_artifact=args.baseline_artifact,
        require_baseline_artifact=bool(args.require_baseline_artifact),
        baseline=args.baseline,
        candidate=args.candidate,
    )
    # Rebuild command with seed/tenant from CLI for print/execute accuracy.
    readiness.command = build_live_regression_command(
        baseline=args.baseline,
        candidate=args.candidate,
        dataset=args.dataset,
        max_cases=args.max_cases,
        seed=args.seed,
        baseline_artifact=args.baseline_artifact,
        require_baseline_artifact=bool(args.require_baseline_artifact),
        tenant=args.tenant,
    )
    readiness.reasons = [
        r
        for r in readiness.reasons
        if not r.startswith("forbidden") and not r.startswith("missing required")
    ] + validate_live_command(readiness.command)

    report = readiness.to_report()
    report_path = args.write_report
    if report_path is None and args.mode == "readiness":
        report_path = str(DEFAULT_REPORT_DIR / "live-provider-gate-readiness.json")

    if args.mode == "command":
        print(" ".join(readiness.command))
        if report_path:
            write_report(report, Path(report_path))
        return 0

    if args.mode == "readiness":
        if report_path:
            written = write_report(report, Path(report_path))
            report["report_path"] = str(written)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        # Readiness without opt-in is a successful scaffold run (not release PASS).
        return 0

    # mode == live
    if not readiness.opt_in:
        report["gate"]["verdict"] = "SKIPPED_NO_OPT_IN"
        report["reasons"] = readiness.reasons
        if report_path:
            write_report(report, Path(report_path))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if not readiness.release_eligible_to_attempt:
        report["gate"]["verdict"] = readiness.verdict
        report["exit_code"] = 1
        if report_path:
            write_report(report, Path(report_path))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    if not args.execute:
        report["gate"]["verdict"] = "READY_NOT_EXECUTED"
        report["notes"] = (
            readiness.notes
            + " Pass --execute to subprocess regression_eval after opt-in+keys."
        )
        if report_path:
            write_report(report, Path(report_path))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # Actual live subprocess — only with opt-in + keys + --execute.
    code = run_live_subprocess(readiness.command)
    report["subprocess_exit_code"] = code
    report["gate"]["verdict"] = "LIVE_EXECUTED"
    report["exit_code"] = code
    # Do not invent release_passed here; regression_eval report is authoritative.
    report["evidence_valid"] = False
    report["release_passed"] = False
    report["notes"] = (
        "Live subprocess finished; consult regression_eval report for release_passed."
    )
    if report_path:
        write_report(report, Path(report_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())

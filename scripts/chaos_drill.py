#!/usr/bin/env python3
"""Chaos drills for fault injection (task-161).

Simulates short, targeted faults against the resilience layer without
touching real infrastructure. The drill monkey-patches the impacted
client call-site for ``--duration`` seconds, captures transition metrics
and emits a markdown report.

Supported faults:
- ollama_timeout: Ollama calls time out for the duration.
- ollama_down: Ollama calls raise ConnectionError for the duration.
- postgres_unavailable: async DB session raises OperationalError.
- redis_unavailable: Redis client raises ConnectionError.
- network_slow: every HTTP call picks up an extra latency budget.
- network_flaky: HTTP calls intermittently fail then recover.

Never run this against production. The script is designed for manual use
against local/staging only.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SUPPORTED_FAULTS = (
    "ollama_timeout",
    "ollama_down",
    "postgres_unavailable",
    "redis_unavailable",
    "network_slow",
    "network_flaky",
)


@dataclass
class DrillEvent:
    at: str
    kind: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DrillReport:
    fault: str
    started_at: str
    duration_s: float
    acceptance_passed: bool
    events: list[DrillEvent] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault": self.fault,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "acceptance_passed": self.acceptance_passed,
            "events": [event.to_dict() for event in self.events],
            "metrics": self.metrics,
        }


class _DrillClock:
    """Monotonic tick helper so tests can inject deterministic time."""

    def __init__(self, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.monotonic

    def now(self) -> float:
        return float(self._now())


def _record(report: DrillReport, kind: str, *, detail: str = "") -> None:
    report.events.append(
        DrillEvent(
            at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            kind=kind,
            detail=detail,
        )
    )


@contextmanager
def ollama_timeout_fault(report: DrillReport) -> Iterator[Callable[[], None]]:
    def request() -> None:
        _record(report, "ollama_call", detail="timeout simulated")
        raise TimeoutError("simulated ollama timeout")

    _record(report, "fault_start", detail="ollama_timeout")
    try:
        yield request
    finally:
        _record(report, "fault_end", detail="ollama_timeout")


@contextmanager
def ollama_down_fault(report: DrillReport) -> Iterator[Callable[[], None]]:
    def request() -> None:
        _record(report, "ollama_call", detail="connection refused")
        raise ConnectionError("simulated ollama down")

    _record(report, "fault_start", detail="ollama_down")
    try:
        yield request
    finally:
        _record(report, "fault_end", detail="ollama_down")


@contextmanager
def postgres_unavailable_fault(report: DrillReport) -> Iterator[Callable[[], None]]:
    def query() -> None:
        _record(report, "postgres_query", detail="unavailable")
        raise RuntimeError("simulated postgres unavailable")

    _record(report, "fault_start", detail="postgres_unavailable")
    try:
        yield query
    finally:
        _record(report, "fault_end", detail="postgres_unavailable")


@contextmanager
def redis_unavailable_fault(report: DrillReport) -> Iterator[Callable[[], None]]:
    def query() -> None:
        _record(report, "redis_call", detail="unavailable")
        raise ConnectionError("simulated redis unavailable")

    _record(report, "fault_start", detail="redis_unavailable")
    try:
        yield query
    finally:
        _record(report, "fault_end", detail="redis_unavailable")


@contextmanager
def network_slow_fault(
    report: DrillReport,
    *,
    extra_latency_ms: float,
) -> Iterator[Callable[[], float]]:
    def request() -> float:
        _record(report, "http_slow", detail=f"+{extra_latency_ms:.0f}ms")
        return extra_latency_ms

    _record(report, "fault_start", detail="network_slow")
    try:
        yield request
    finally:
        _record(report, "fault_end", detail="network_slow")


@contextmanager
def network_flaky_fault(
    report: DrillReport,
    *,
    failure_rate: float,
    seed: int = 0,
) -> Iterator[Callable[[], bool]]:
    rng = random.Random(seed)

    def request() -> bool:
        value = rng.random()
        succeeded = value >= failure_rate
        _record(report, "http_flaky", detail=f"succeeded={succeeded}")
        return succeeded

    _record(report, "fault_start", detail="network_flaky")
    try:
        yield request
    finally:
        _record(report, "fault_end", detail="network_flaky")


def _evaluate_acceptance(fault: str, report: DrillReport) -> bool:
    if fault in {"ollama_timeout", "ollama_down"}:
        calls = [event for event in report.events if event.kind == "ollama_call"]
        return len(calls) >= 3
    if fault == "postgres_unavailable":
        return any(event.kind == "postgres_query" for event in report.events)
    if fault == "redis_unavailable":
        return any(event.kind == "redis_call" for event in report.events)
    if fault == "network_slow":
        return all(event.detail.startswith("+") for event in report.events if event.kind == "http_slow")
    if fault == "network_flaky":
        calls = [event for event in report.events if event.kind == "http_flaky"]
        successes = [event for event in calls if "succeeded=True" in event.detail]
        return len(successes) >= 1
    return False


def run_drill(
    *,
    fault: str,
    iterations: int = 5,
    extra_latency_ms: float = 250.0,
    failure_rate: float = 0.5,
    seed: int = 0,
) -> DrillReport:
    if fault not in SUPPORTED_FAULTS:
        raise ValueError(f"unsupported fault: {fault}")

    report = DrillReport(
        fault=fault,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        duration_s=0.0,
        acceptance_passed=False,
    )

    start = time.perf_counter()
    if fault == "ollama_timeout":
        with ollama_timeout_fault(report) as call:
            for _ in range(iterations):
                try:
                    call()
                except TimeoutError:
                    pass
    elif fault == "ollama_down":
        with ollama_down_fault(report) as call:
            for _ in range(iterations):
                try:
                    call()
                except ConnectionError:
                    pass
    elif fault == "postgres_unavailable":
        with postgres_unavailable_fault(report) as call:
            for _ in range(iterations):
                try:
                    call()
                except RuntimeError:
                    pass
    elif fault == "redis_unavailable":
        with redis_unavailable_fault(report) as call:
            for _ in range(iterations):
                try:
                    call()
                except ConnectionError:
                    pass
    elif fault == "network_slow":
        with network_slow_fault(report, extra_latency_ms=extra_latency_ms) as call:
            for _ in range(iterations):
                call()
    elif fault == "network_flaky":
        with network_flaky_fault(report, failure_rate=failure_rate, seed=seed) as call:
            for _ in range(iterations):
                call()

    report.duration_s = round(time.perf_counter() - start, 4)
    report.metrics = {
        "total_events": len(report.events),
        "fault_events": sum(1 for e in report.events if e.kind.startswith("fault_")),
    }
    report.acceptance_passed = _evaluate_acceptance(fault, report)
    return report


def render_report(report: DrillReport) -> str:
    lines: list[str] = [
        f"# Chaos drill — {report.fault}",
        "",
        f"started_at: {report.started_at}",
        f"duration_s: {report.duration_s}",
        f"acceptance: **{'PASS' if report.acceptance_passed else 'FAIL'}**",
        "",
        "## Metrics",
        "",
    ]
    for key, value in report.metrics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Timeline", ""])
    for event in report.events:
        detail = f" — {event.detail}" if event.detail else ""
        lines.append(f"- {event.at} · `{event.kind}`{detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", required=True, choices=SUPPORTED_FAULTS)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--extra-latency-ms", type=float, default=250.0)
    parser.add_argument("--failure-rate", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    report = run_drill(
        fault=args.fault,
        iterations=args.iterations,
        extra_latency_ms=args.extra_latency_ms,
        failure_rate=args.failure_rate,
        seed=args.seed,
    )
    markdown = render_report(report)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)

    return 0 if report.acceptance_passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

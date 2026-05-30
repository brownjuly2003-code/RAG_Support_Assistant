#!/usr/bin/env python3
"""Post-deploy smoke suite (task-162).

Runs a short (target: <30s) sanity check against a running RAG instance.
Emits a markdown report and a non-zero exit on the first failed check.

Use after every restart, `alembic upgrade` or restore.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SmokeReport:
    base_url: str
    created_at: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "created_at": self.created_at,
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
        }


def _time_check(name: str, func: Callable[[], tuple[bool, str]]) -> CheckResult:
    start = time.perf_counter()
    try:
        passed, detail = func()
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return CheckResult(name=name, passed=False, detail=f"exception: {exc}", latency_ms=elapsed)
    elapsed = (time.perf_counter() - start) * 1000.0
    return CheckResult(name=name, passed=passed, detail=detail, latency_ms=elapsed)


def _check_liveness(client: httpx.Client) -> tuple[bool, str]:
    response = client.get("/healthz/live")
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    return True, "live"


def _check_readiness(client: httpx.Client) -> tuple[bool, str]:
    response = client.get("/healthz/ready")
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    return True, "ready"


_REQUIRED_METRIC_SUBSTRINGS = (
    "rag_model_routing",
    "rag_llm_cost_usd_total",
    "rag_experiment_auto_rollback_total",
)


def _check_metrics(client: httpx.Client) -> tuple[bool, str]:
    response = client.get("/metrics")
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    body = response.text or ""
    missing = [needle for needle in _REQUIRED_METRIC_SUBSTRINGS if needle not in body]
    if missing:
        return False, f"missing metrics: {missing}"
    return True, f"{body.count(chr(10))} lines"


def _check_ask(client: httpx.Client, *, token: Optional[str]) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        "/api/ask",
        headers=headers,
        json={"question": "What is 2+2?", "tenant_id": "default"},
    )
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    payload = response.json()
    if "answer" not in payload or "trace_id" not in payload:
        return False, "missing answer or trace_id in payload"
    return True, f"trace={payload['trace_id']}"


def _check_admin_providers(client: httpx.Client, *, token: Optional[str]) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.get("/api/admin/providers", headers=headers)
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    payload = response.json() or {}
    providers = payload.get("providers") or []
    names = {str(p.get("id") or p.get("name") or "").lower() for p in providers}
    required = {"ollama"}
    if not required.issubset(names):
        return False, f"missing providers: expected {sorted(required)} in {sorted(names)}"
    return True, f"{len(providers)} providers"


def run_smoke(
    base_url: str,
    *,
    client: Optional[httpx.Client] = None,
    admin_token: Optional[str] = None,
    timeout: float = 10.0,
) -> SmokeReport:
    owns_client = client is None
    if owns_client:
        client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    assert client is not None

    try:
        report = SmokeReport(
            base_url=base_url,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        report.results.append(_time_check("liveness", lambda: _check_liveness(client)))
        report.results.append(_time_check("readiness", lambda: _check_readiness(client)))
        report.results.append(_time_check("metrics", lambda: _check_metrics(client)))
        report.results.append(_time_check("ask", lambda: _check_ask(client, token=admin_token)))
        report.results.append(
            _time_check("admin_providers", lambda: _check_admin_providers(client, token=admin_token))
        )
    finally:
        if owns_client:
            client.close()
    return report


def render_report(report: SmokeReport) -> str:
    lines: list[str] = [
        "# Post-deploy smoke report",
        "",
        f"base_url: {report.base_url}",
        f"created_at: {report.created_at}",
        f"overall: **{'PASS' if report.passed else 'FAIL'}**",
        "",
        "| check | status | latency_ms | detail |",
        "| --- | --- | ---: | --- |",
    ]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        detail = result.detail.replace("|", r"\|")
        lines.append(
            f"| {result.name} | {status} | {result.latency_ms:.1f} | {detail} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--report", default=None)
    parser.add_argument("--token", default=None, help="bearer admin token for /api/admin/* checks")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    report = run_smoke(args.base_url, admin_token=args.token, timeout=args.timeout)
    markdown = render_report(report)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)

    if not report.passed:
        print(json.dumps({"failed": [r.name for r in report.results if not r.passed]}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

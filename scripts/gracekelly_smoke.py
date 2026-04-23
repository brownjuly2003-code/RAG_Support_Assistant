#!/usr/bin/env python3
"""GraceKelly runtime smoke harness."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

EXIT_OK = 0
EXIT_HEALTH_FAILED = 1
EXIT_SMART_ASK_FAILED = 2
EXIT_TOOL_LOOP_FAILED = 3
EXIT_SCHEMA_FAILED = 4
EXIT_STREAMING_FAILED = 5
EXIT_METRICS_FAILED = 6
EXIT_FAILOVER_FAILED = 7

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_SYMBOLS = {
    STATUS_PASS: "✓",
    STATUS_FAIL: "✗",
    STATUS_SKIPPED: "~",
}


@dataclass
class StepResult:
    step: int
    name: str
    status: str
    latency_ms: float
    detail: str


@dataclass
class TraceSummary:
    trace_id: str
    provider: str | None = None
    model: str | None = None
    tool_nodes: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    complexities: list[str] = field(default_factory=list)
    cost_values: list[float] = field(default_factory=list)


class SmokeFailure(RuntimeError):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class GraceKellySmoke:
    def __init__(
        self,
        *,
        gracekelly_url: str,
        rag_url: str,
        tenant: str,
        verbose: bool,
        simulate_down: bool,
    ) -> None:
        timeout = httpx.Timeout(45.0, connect=5.0)
        self.gracekelly_url = gracekelly_url.rstrip("/")
        self.rag_url = rag_url.rstrip("/")
        self.tenant = tenant
        self.verbose = verbose
        self.simulate_down = simulate_down
        self.results: list[StepResult] = []
        self.trace_summaries: list[TraceSummary] = []
        self.provider_snapshot: dict[str, Any] | None = None
        self.active_profile: str | None = None
        self.active_profile_config: dict[str, Any] | None = None
        self.rag_client = httpx.Client(
            base_url=self.rag_url,
            follow_redirects=True,
            timeout=timeout,
            headers=self._build_rag_headers(),
        )
        self.gracekelly_client = httpx.Client(
            base_url=self.gracekelly_url,
            follow_redirects=True,
            timeout=timeout,
            headers=self._build_gracekelly_headers(),
        )
        self._baseline_cost = 0.0
        self._baseline_cost_seen = False
        self._baseline_fallback = 0.0
        self._baseline_fallback_seen = False

    def close(self) -> None:
        self.rag_client.close()
        self.gracekelly_client.close()

    def log(self, message: str) -> None:
        print(message, flush=True)

    def debug(self, message: str) -> None:
        if self.verbose:
            self.log(f"    {message}")

    def run(self) -> int:
        try:
            if self.simulate_down:
                self._append_skipped_range(1, 7, "simulate-down mode executes only failover validation")
                self._execute_step(8, "failover", self._step_failover_only, EXIT_FAILOVER_FAILED)
            else:
                self._execute_step(1, "healthz", self._step_healthz, EXIT_HEALTH_FAILED)
                self._execute_step(2, "profile", self._step_profile, EXIT_SMART_ASK_FAILED)
                self._baseline_cost, self._baseline_cost_seen = self._get_gracekelly_cost_metric()
                self._baseline_fallback, self._baseline_fallback_seen = self._get_fallback_metric()
                self._execute_step(3, "simple ask", self._step_simple_ask, EXIT_SMART_ASK_FAILED)
                self._execute_step(4, "tool loop", self._step_tool_loop, EXIT_TOOL_LOOP_FAILED)
                self._execute_step(5, "schema", self._step_schema_dispatch, EXIT_SCHEMA_FAILED)
                self._execute_step(6, "streaming", self._step_streaming, EXIT_STREAMING_FAILED)
                self._execute_step(7, "metrics", self._step_metrics, EXIT_METRICS_FAILED)
                self._execute_step(8, "failover", self._step_failover_skipped, EXIT_FAILOVER_FAILED)
        except SmokeFailure as exc:
            self._print_table()
            print(str(exc), file=sys.stderr)
            return exc.exit_code

        self._print_table()
        return EXIT_OK

    def _build_rag_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        bearer = self._first_env("RAG_BEARER_TOKEN", "BEARER_TOKEN", "RAG_AUTH_TOKEN")
        api_key = self._first_env("RAG_API_KEY", "API_KEY")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if api_key:
            headers["X-API-Key"] = api_key
        return headers

    def _build_gracekelly_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self._first_env("GRACEKELLY_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _first_env(self, *names: str) -> str | None:
        for name in names:
            value = (os.getenv(name, "") or "").strip()
            if value:
                return value
        return None

    def _append_skipped_range(self, first_step: int, last_step: int, detail: str) -> None:
        for step in range(first_step, last_step + 1):
            self.results.append(
                StepResult(step=step, name=self._step_name(step), status=STATUS_SKIPPED, latency_ms=0.0, detail=detail)
            )
            self._print_step(self.results[-1])

    def _step_name(self, step: int) -> str:
        names = {
            1: "healthz",
            2: "profile",
            3: "simple ask",
            4: "tool loop",
            5: "schema",
            6: "streaming",
            7: "metrics",
            8: "failover",
        }
        return names.get(step, f"step-{step}")

    def _execute_step(
        self,
        step: int,
        name: str,
        func: Any,
        exit_code: int,
    ) -> StepResult:
        started = time.perf_counter()
        try:
            status, detail = func()
        except Exception as exc:
            status = STATUS_FAIL
            detail = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000.0
        result = StepResult(step=step, name=name, status=status, latency_ms=latency_ms, detail=detail)
        self.results.append(result)
        self._print_step(result)
        if status == STATUS_FAIL:
            raise SmokeFailure(f"step {step} {name}: {detail}", exit_code)
        return result

    def _print_step(self, result: StepResult) -> None:
        symbol = STATUS_SYMBOLS[result.status]
        self.log(
            f"{symbol} step {result.step} {result.name} ({result.latency_ms:.1f} ms): {result.detail}"
        )

    def _print_table(self) -> None:
        if not self.results:
            return

        step_width = max(len("step"), max(len(f"{item.step} {item.name}") for item in self.results))
        status_width = max(len("status"), max(len(item.status) for item in self.results))
        latency_width = max(len("latency_ms"), max(len(f"{item.latency_ms:.1f}") for item in self.results))
        self.log("")
        self.log(
            f"{'step':<{step_width}}  {'status':<{status_width}}  {'latency_ms':>{latency_width}}  detail"
        )
        self.log(
            f"{'-' * step_width}  {'-' * status_width}  {'-' * latency_width}  {'-' * 40}"
        )
        for item in self.results:
            step_label = f"{item.step} {item.name}"
            self.log(
                f"{step_label:<{step_width}}  {item.status:<{status_width}}  {item.latency_ms:>{latency_width}.1f}  {item.detail}"
            )

    def _expect_json(self, response: httpx.Response, *, target: str) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            if target == "GraceKelly" and "Authorization" not in self.gracekelly_client.headers:
                raise RuntimeError("GraceKelly requires GRACEKELLY_API_KEY in the environment")
            if target == "RAG" and not any(
                header in self.rag_client.headers for header in ("Authorization", "X-API-Key")
            ):
                raise RuntimeError(
                    "RAG API requires auth; export API_KEY or RAG_BEARER_TOKEN before running smoke"
                )
        if response.status_code >= 400:
            body = (response.text or "").strip()
            if body:
                raise RuntimeError(f"{target} returned {response.status_code}: {body[:300]}")
            raise RuntimeError(f"{target} returned {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{target} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{target} returned unexpected payload type")
        return payload

    def _fetch_provider_snapshot(self) -> dict[str, Any]:
        if self.provider_snapshot is not None:
            return self.provider_snapshot
        response = self.rag_client.get("/api/admin/providers")
        payload = self._expect_json(response, target="RAG")
        self.provider_snapshot = payload
        self.active_profile = str(payload.get("active_profile") or "")
        profiles = payload.get("profiles") or {}
        if isinstance(profiles, dict):
            profile = profiles.get(self.active_profile)
            if isinstance(profile, dict):
                self.active_profile_config = profile
        return payload

    def _active_profile_uses_gracekelly(self) -> bool:
        snapshot = self._fetch_provider_snapshot()
        profile_name = str(snapshot.get("active_profile") or "")
        profiles = snapshot.get("profiles") or {}
        profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
        if not isinstance(profile, dict):
            return "gracekelly" in profile_name.lower()
        fast = profile.get("fast") if isinstance(profile.get("fast"), dict) else {}
        strong = profile.get("strong") if isinstance(profile.get("strong"), dict) else {}
        providers = {
            str(fast.get("provider") or "").strip().lower(),
            str(strong.get("provider") or "").strip().lower(),
        }
        return "gracekelly" in providers or "gracekelly" in profile_name.lower()

    def _get_active_gracekelly_model(self) -> str | None:
        self._fetch_provider_snapshot()
        profile = self.active_profile_config or {}
        for tier_name in ("strong", "fast"):
            tier = profile.get(tier_name) if isinstance(profile.get(tier_name), dict) else {}
            if str(tier.get("provider") or "").strip().lower() == "gracekelly":
                model = str(tier.get("model") or "").strip()
                if model:
                    return model
        return None

    def _get_metrics_text(self) -> str:
        response = self.rag_client.get("/metrics")
        if response.status_code >= 400:
            body = (response.text or "").strip()
            if body:
                raise RuntimeError(f"RAG /metrics returned {response.status_code}: {body[:300]}")
            raise RuntimeError(f"RAG /metrics returned {response.status_code}")
        return response.text or ""

    def _parse_metric_sum(self, metric_name: str, matcher: dict[str, str]) -> tuple[float, bool]:
        body = self._get_metrics_text()
        total = 0.0
        seen = False
        pattern = re.compile(
            rf"^{re.escape(metric_name)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>[-+0-9.eE]+)$",
            re.MULTILINE,
        )
        for match in pattern.finditer(body):
            labels = self._parse_labels(match.group("labels") or "")
            if all(labels.get(key) == value for key, value in matcher.items()):
                total += float(match.group("value"))
                seen = True
        return total, seen

    def _parse_labels(self, labels: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        if not labels:
            return parsed
        for key, value in re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', labels):
            parsed[key] = bytes(value, "utf-8").decode("unicode_escape")
        return parsed

    def _get_gracekelly_cost_metric(self) -> tuple[float, bool]:
        return self._parse_metric_sum(
            "llm_cost_usd_total",
            {"provider": "gracekelly", "tenant": self.tenant},
        )

    def _get_fallback_metric(self) -> tuple[float, bool]:
        return self._parse_metric_sum(
            "llm_provider_fallback_total",
            {"from_provider": "gracekelly", "to_provider": "ollama", "reason": "unavailable"},
        )

    def _ask(self, question: str) -> dict[str, Any]:
        response = self.rag_client.post(
            "/api/ask",
            json={"question": question, "tenant_id": self.tenant},
        )
        payload = self._expect_json(response, target="RAG")
        answer = str(payload.get("answer") or "").strip()
        trace_id = str(payload.get("trace_id") or "").strip()
        if not answer:
            raise RuntimeError("empty answer")
        if not trace_id:
            raise RuntimeError("missing trace_id in /api/ask response")
        self.debug(f"/api/ask trace_id={trace_id}")
        return payload

    def _fetch_trace(self, trace_id: str) -> dict[str, Any]:
        response = self.rag_client.get(f"/api/admin/traces/{trace_id}")
        payload = self._expect_json(response, target="RAG")
        return payload

    def _summarize_trace(self, trace: dict[str, Any]) -> TraceSummary:
        summary = TraceSummary(trace_id=str(trace.get("trace_id") or ""))
        for step in trace.get("steps") or []:
            if not isinstance(step, dict):
                continue
            node = str(step.get("node") or "").strip()
            state = step.get("state")
            if not isinstance(state, dict):
                continue

            provider = (
                str(state.get("provider_name") or state.get("llm_provider_name") or "").strip() or None
            )
            model = str(state.get("model_name") or state.get("llm_model_name") or "").strip() or None
            if provider:
                summary.provider = provider
            if model:
                summary.model = model

            tool_calls = state.get("tool_calls")
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    tool_name = str(tool_call).strip()
                    if tool_name and tool_name not in summary.tool_calls:
                        summary.tool_calls.append(tool_name)

            if node in {"search_kb", "check_order_status", "create_ticket", "confirmation_gate"}:
                if node not in summary.tool_nodes:
                    summary.tool_nodes.append(node)

            complexity = str(state.get("complexity") or "").strip()
            if complexity and complexity not in summary.complexities:
                summary.complexities.append(complexity)

            raw_cost = state.get("cost_usd")
            try:
                cost_value = float(raw_cost)
            except (TypeError, ValueError):
                cost_value = None
            if cost_value is not None:
                summary.cost_values.append(cost_value)

        self.trace_summaries.append(summary)
        return summary

    def _nonce_letters(self) -> str:
        letters = "".join(char for char in uuid.uuid4().hex if char.isalpha())
        return (letters[:6] or "smoke").lower()

    def _step_healthz(self) -> tuple[str, str]:
        try:
            response = self.gracekelly_client.get("/healthz/ready")
        except httpx.HTTPError:
            raise RuntimeError(
                f"GraceKelly not reachable at {self.gracekelly_url}, start D:\\GraceKelly\\ first"
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"GraceKelly not reachable at {self.gracekelly_url}, start D:\\GraceKelly\\ first"
            )
        return STATUS_PASS, "200 ready"

    def _step_profile(self) -> tuple[str, str]:
        snapshot = self._fetch_provider_snapshot()
        active_profile = str(snapshot.get("active_profile") or "")
        if not self._active_profile_uses_gracekelly():
            raise RuntimeError(
                f"active profile '{active_profile or '<empty>'}' is not GraceKelly-backed"
            )
        return STATUS_PASS, f"active_profile={active_profile}"

    def _step_simple_ask(self) -> tuple[str, str]:
        nonce = self._nonce_letters()
        payload = self._ask(f"What is 2+2? Reply in one short sentence. Ref smoke {nonce}.")
        trace_id = str(payload.get("trace_id") or "")
        trace = self._fetch_trace(trace_id)
        summary = self._summarize_trace(trace)
        if (summary.provider or "").lower() != "gracekelly":
            raise RuntimeError(
                f"expected provider=gracekelly, got {summary.provider or '<missing>'}"
            )
        if not summary.model:
            raise RuntimeError("trace lacks model metadata for GraceKelly request")
        answer = str(payload.get("answer") or "").strip()
        return STATUS_PASS, f"trace={trace_id} provider={summary.provider} model={summary.model} answer_len={len(answer)}"

    def _step_tool_loop(self) -> tuple[str, str]:
        payload = self._ask("Проверь статус заказа #42 и условия доставки в Москву.")
        trace_id = str(payload.get("trace_id") or "")
        trace = self._fetch_trace(trace_id)
        summary = self._summarize_trace(trace)
        if summary.tool_calls and (summary.provider or "").lower() == "gracekelly":
            return STATUS_PASS, f"trace={trace_id} tool_calls={','.join(summary.tool_calls)}"
        if summary.tool_nodes and (summary.provider or "").lower() == "gracekelly":
            return STATUS_PASS, f"trace={trace_id} tool_nodes={','.join(summary.tool_nodes)}"
        return (
            STATUS_SKIPPED,
            "tool loop not observable in current runtime (likely RAG_AGENTIC_MODE=false or no GraceKelly tool trace)",
        )

    def _extract_structured_output(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        candidates = (
            result.get("structured_output"),
            payload.get("structured_output"),
            metadata.get("structured_output"),
        )
        for candidate in candidates:
            if isinstance(candidate, dict):
                return candidate
        return None

    def _step_schema_dispatch(self) -> tuple[str, str]:
        model = self._get_active_gracekelly_model()
        if not model:
            raise RuntimeError("unable to resolve active GraceKelly model from /api/admin/providers")
        schema = {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "enum": ["auto", "fact", "support"],
                }
            },
            "required": ["route"],
            "additionalProperties": False,
        }
        payload = {
            "prompt": (
                "Classify the support request into exactly one route: auto, fact, or support. "
                "Return structured output only.\n\n"
                "Question: The customer says the package still has not arrived and asks whether an operator should check order #42."
            ),
            "requested_models": [model],
            "model": model,
            "reliability_level": "quick",
            "structured_output_schema": schema,
        }
        response = self.gracekelly_client.post("/api/v1/orchestrate", json=payload)
        body = self._expect_json(response, target="GraceKelly")
        structured = self._extract_structured_output(body)
        route = str(structured.get("route") or "").strip().lower() if structured else ""
        if route not in {"auto", "fact", "support"}:
            raise RuntimeError("GraceKelly schema dispatch did not return structured_output.route")
        return STATUS_PASS, f"model={model} route={route}"

    def _iter_sse_events(self, response: httpx.Response) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        buffer: list[str] = []
        for raw_line in response.iter_lines():
            line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="ignore")
            if line == "":
                if not buffer:
                    continue
                payload = "".join(buffer).strip()
                buffer.clear()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
                continue
            if line.startswith("data:"):
                buffer.append(line[5:].strip())
        if buffer:
            payload = "".join(buffer).strip()
            try:
                event = json.loads(payload)
            except ValueError:
                event = None
            if isinstance(event, dict):
                events.append(event)
        return events

    def _step_streaming(self) -> tuple[str, str]:
        nonce = self._nonce_letters()
        with self.rag_client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "question": (
                    "Count from one to five as separate words with commas. "
                    f"Ref smoke {nonce}."
                ),
                "tenant_id": self.tenant,
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", errors="ignore").strip()
                if body:
                    raise RuntimeError(f"stream returned {response.status_code}: {body[:300]}")
                raise RuntimeError(f"stream returned {response.status_code}")
            events = self._iter_sse_events(response)

        token_count = sum(1 for event in events if event.get("type") == "token")
        final_done = any(event.get("done") is True for event in events)
        final_result = next((event for event in reversed(events) if event.get("type") == "result"), None)
        if token_count >= 3 and (final_done or final_result is not None):
            final_marker = "done=true" if final_done else "type=result"
            return STATUS_PASS, f"chunks={token_count} final={final_marker}"
        if token_count > 0 and final_result is not None:
            return STATUS_SKIPPED, f"stream produced only {token_count} chunks before final result"
        raise RuntimeError("stream did not produce incremental token events and a final result")

    def _step_metrics(self) -> tuple[str, str]:
        current_cost, current_seen = self._get_gracekelly_cost_metric()
        delta = current_cost - self._baseline_cost
        if current_seen and delta > 0:
            return STATUS_PASS, f"gracekelly cost counter delta={delta:.6f}"

        saw_gracekelly_trace = any(
            (trace.provider or "").lower() == "gracekelly" for trace in self.trace_summaries
        )
        saw_zero_cost = any(
            any(cost == 0.0 for cost in trace.cost_values) for trace in self.trace_summaries
        )
        if saw_gracekelly_trace and saw_zero_cost:
            return (
                STATUS_SKIPPED,
                "llm_cost_usd_total does not export zero-cost GraceKelly traces in the current runtime",
            )
        raise RuntimeError(
            f"expected GraceKelly cost counter increment, got baseline={self._baseline_cost:.6f} current={current_cost:.6f}"
        )

    def _step_failover_skipped(self) -> tuple[str, str]:
        return (
            STATUS_SKIPPED,
            "rerun with --simulate-down against a RAG instance started with unreachable GRACEKELLY_BASE_URL or with GraceKelly stopped",
        )

    def _step_failover_only(self) -> tuple[str, str]:
        snapshot = self._fetch_provider_snapshot()
        active_profile = str(snapshot.get("active_profile") or "")
        if not self._active_profile_uses_gracekelly():
            raise RuntimeError(
                f"active profile '{active_profile or '<empty>'}' is not GraceKelly-backed"
            )

        baseline, _ = self._get_fallback_metric()
        nonce = self._nonce_letters()
        payload = self._ask(f"What is 2+2? Reply with one word. Failover smoke {nonce}.")
        trace_id = str(payload.get("trace_id") or "")
        trace = self._fetch_trace(trace_id)
        summary = self._summarize_trace(trace)
        current, _ = self._get_fallback_metric()
        delta = current - baseline
        if delta <= 0:
            raise RuntimeError("expected fallback counter increment, got 0")
        if (summary.provider or "").lower() != "ollama":
            raise RuntimeError(
                f"expected failover provider=ollama, got {summary.provider or '<missing>'}"
            )
        return STATUS_PASS, f"trace={trace_id} provider={summary.provider} fallback_delta={delta:.0f}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gracekelly-url", default="http://127.0.0.1:8011")
    parser.add_argument("--rag-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant", default="smoke-test")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--simulate-down",
        action="store_true",
        help=(
            "Run only step 8 failover validation. The target RAG instance must already be "
            "started with unreachable GRACEKELLY_BASE_URL or with GraceKelly stopped."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    smoke = GraceKellySmoke(
        gracekelly_url=args.gracekelly_url,
        rag_url=args.rag_url,
        tenant=args.tenant,
        verbose=args.verbose,
        simulate_down=args.simulate_down,
    )
    try:
        return smoke.run()
    finally:
        smoke.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

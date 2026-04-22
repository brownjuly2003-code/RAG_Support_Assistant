from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import post_deploy_smoke


def _transport_router(response_map: dict[tuple[str, str], tuple[int, dict | str]]) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        status, body = response_map.get(key, (404, {"detail": "not found"}))
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(_handler)


def _build_client(response_map: dict[tuple[str, str], tuple[int, dict | str]]) -> httpx.Client:
    transport = _transport_router(response_map)
    return httpx.Client(base_url="http://localhost:8000", transport=transport)


_HAPPY_METRICS_BODY = (
    "# HELP rag_model_routing test\n"
    "rag_model_routing{} 1\n"
    "rag_llm_cost_usd_total{} 0\n"
    "rag_experiment_auto_rollback_total{} 0\n"
)


def test_smoke_passes_when_all_checks_ok() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (200, {"status": "ok"}),
            ("GET", "/healthz/ready"): (200, {"status": "ok"}),
            ("GET", "/metrics"): (200, _HAPPY_METRICS_BODY),
            ("POST", "/api/ask"): (200, {"answer": "4", "trace_id": "trace-smoke"}),
            ("GET", "/api/admin/providers"): (
                200,
                {"providers": [{"id": "ollama"}, {"id": "gracekelly"}]},
            ),
        }
    )

    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)

    assert report.passed is True
    names = {r.name for r in report.results if r.passed}
    assert names == {"liveness", "readiness", "metrics", "ask", "admin_providers"}


def test_smoke_liveness_failure_reported() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (503, {"status": "down"}),
            ("GET", "/healthz/ready"): (503, {"status": "down"}),
            ("GET", "/metrics"): (200, _HAPPY_METRICS_BODY),
            ("POST", "/api/ask"): (200, {"answer": "4", "trace_id": "trace"}),
            ("GET", "/api/admin/providers"): (200, {"providers": [{"id": "ollama"}]}),
        }
    )

    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)

    assert report.passed is False
    failed = [r for r in report.results if not r.passed]
    assert {r.name for r in failed} >= {"liveness", "readiness"}


def test_smoke_metrics_missing_required_keys() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (200, {"status": "ok"}),
            ("GET", "/healthz/ready"): (200, {"status": "ok"}),
            ("GET", "/metrics"): (200, "rag_something_else 1\n"),
            ("POST", "/api/ask"): (200, {"answer": "4", "trace_id": "trace"}),
            ("GET", "/api/admin/providers"): (200, {"providers": [{"id": "ollama"}]}),
        }
    )

    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)

    metrics_result = next(r for r in report.results if r.name == "metrics")
    assert metrics_result.passed is False
    assert "missing metrics" in metrics_result.detail


def test_smoke_ask_rejects_payload_without_trace_id() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (200, {"status": "ok"}),
            ("GET", "/healthz/ready"): (200, {"status": "ok"}),
            ("GET", "/metrics"): (200, _HAPPY_METRICS_BODY),
            ("POST", "/api/ask"): (200, {"answer": "4"}),
            ("GET", "/api/admin/providers"): (200, {"providers": [{"id": "ollama"}]}),
        }
    )

    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)

    ask_result = next(r for r in report.results if r.name == "ask")
    assert ask_result.passed is False
    assert "trace_id" in ask_result.detail


def test_smoke_admin_providers_requires_ollama() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (200, {"status": "ok"}),
            ("GET", "/healthz/ready"): (200, {"status": "ok"}),
            ("GET", "/metrics"): (200, _HAPPY_METRICS_BODY),
            ("POST", "/api/ask"): (200, {"answer": "4", "trace_id": "trace"}),
            ("GET", "/api/admin/providers"): (200, {"providers": [{"id": "gracekelly"}]}),
        }
    )

    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)

    providers_result = next(r for r in report.results if r.name == "admin_providers")
    assert providers_result.passed is False
    assert "ollama" in providers_result.detail


def test_render_report_includes_pass_fail_summary() -> None:
    client = _build_client(
        {
            ("GET", "/healthz/live"): (200, {"status": "ok"}),
            ("GET", "/healthz/ready"): (200, {"status": "ok"}),
            ("GET", "/metrics"): (200, _HAPPY_METRICS_BODY),
            ("POST", "/api/ask"): (200, {"answer": "4", "trace_id": "trace"}),
            ("GET", "/api/admin/providers"): (200, {"providers": [{"id": "ollama"}]}),
        }
    )
    report = post_deploy_smoke.run_smoke("http://localhost:8000", client=client)
    markdown = post_deploy_smoke.render_report(report)

    assert "Post-deploy smoke report" in markdown
    assert "overall: **PASS**" in markdown
    for name in ("liveness", "readiness", "metrics", "ask", "admin_providers"):
        assert name in markdown

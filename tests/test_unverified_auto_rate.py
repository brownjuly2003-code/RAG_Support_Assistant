"""§9.2b — bounded observability for unverified automatic responses."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from monitoring import prometheus as prometheus_metrics


def _metric_value(metrics_text: str, name: str, labels: str) -> float | None:
    match = re.search(
        rf"^{re.escape(name)}\{{{re.escape(labels)}\}}\s+([0-9.e+-]+)$",
        metrics_text,
        re.MULTILINE,
    )
    return None if match is None else float(match.group(1))


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        agentic_mode=False,
        ask_budget_sec=0.0,
        online_evaluators_enabled=False,
        quality_threshold=80,
    )


def test_auto_response_metric_has_bounded_verification_labels() -> None:
    before = prometheus_metrics.generate_latest(prometheus_metrics.REGISTRY).decode()
    before_verified = (
        _metric_value(
            before,
            "rag_auto_responses_total",
            'verification="verified"',
        )
        or 0.0
    )
    before_unverified = (
        _metric_value(
            before,
            "rag_auto_responses_total",
            'verification="unverified"',
        )
        or 0.0
    )

    prometheus_metrics.record_auto_response_verification("verified")
    prometheus_metrics.record_auto_response_verification("not_verified")
    prometheus_metrics.record_auto_response_verification("unsupported")
    prometheus_metrics.record_auto_response_verification("tenant-specific-value")

    after = prometheus_metrics.generate_latest(prometheus_metrics.REGISTRY).decode()
    assert (
        _metric_value(
            after,
            "rag_auto_responses_total",
            'verification="verified"',
        )
        == before_verified + 1.0
    )
    assert (
        _metric_value(
            after,
            "rag_auto_responses_total",
            'verification="unverified"',
        )
        == before_unverified + 3.0
    )
    assert (
        _metric_value(
            after,
            "rag_auto_responses_total",
            'verification="tenant-specific-value"',
        )
        is None
    )


def test_sync_session_records_only_auto_response_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    results = iter(
        [
            {
                "answer": "verified",
                "route": "auto",
                "grounding_status": "verified",
            },
            {
                "answer": "handoff",
                "route": "human",
                "grounding_status": "not_verified",
            },
        ]
    )
    recorded: list[str] = []
    monkeypatch.setattr("config.settings.get_settings", _settings, raising=False)
    monkeypatch.setattr(graph, "run_qa_pipeline", lambda **kwargs: next(results))
    monkeypatch.setattr(
        prometheus_metrics,
        "record_auto_response_verification",
        recorded.append,
        raising=False,
    )

    session = graph.ConversationSession(retriever=object())
    session.ask("first")
    session.ask("second")

    assert recorded == ["verified"]


def test_stream_session_records_auto_response_verification_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    recorded: list[str] = []
    monkeypatch.setattr("config.settings.get_settings", _settings, raising=False)
    monkeypatch.setattr(
        prometheus_metrics,
        "record_auto_response_verification",
        recorded.append,
        raising=False,
    )

    def _events(**kwargs: Any) -> Any:
        yield {
            "type": "pipeline_result",
            "state": {
                "answer": "unexpected auto",
                "route": "auto",
                "grounding_status": "not_verified",
            },
            "nodes": ["log"],
        }

    monkeypatch.setattr(graph, "iter_qa_pipeline_events", _events)

    session = graph.ConversationSession(retriever=object())
    events = list(session.iter_ask_events("streamed"))

    assert events[-1]["state"]["route"] == "auto"
    assert recorded == ["not_verified"]

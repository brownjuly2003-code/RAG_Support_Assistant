"""Prometheus metrics для RAG Support Assistant."""
from __future__ import annotations

from typing import Any

__all__ = [
    "ACTIVE_SESSIONS",
    "CIRCUIT_BREAKER_STATE",
    "CIRCUIT_BREAKER_TRANSITIONS",
    "CONTENT_TYPE_LATEST",
    "ESCALATION_TOTAL",
    "FEEDBACK_COUNT",
    "PROMETHEUS_AVAILABLE",
    "QUALITY_SCORE",
    "REGISTRY",
    "REQUEST_COUNT",
    "REQUEST_DURATION",
    "VECTOR_STORE_DOCS",
    "generate_latest",
    "record_circuit_breaker_change",
]

PROMETHEUS_AVAILABLE = False
CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
REGISTRY: Any = None
generate_latest: Any = None


class _NoopMetric:
    def labels(self, *args: Any, **kwargs: Any) -> "_NoopMetric":
        _ = args, kwargs
        return self

    def inc(self, amount: float = 1.0) -> None:
        _ = amount

    def observe(self, value: float) -> None:
        _ = value

    def set(self, value: float) -> None:
        _ = value


try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Summary,
        generate_latest,
    )
except ImportError:
    REQUEST_COUNT = _NoopMetric()
    REQUEST_DURATION = _NoopMetric()
    QUALITY_SCORE = _NoopMetric()
    ESCALATION_TOTAL = _NoopMetric()
    FEEDBACK_COUNT = _NoopMetric()
    ACTIVE_SESSIONS = _NoopMetric()
    VECTOR_STORE_DOCS = _NoopMetric()
    CIRCUIT_BREAKER_STATE = _NoopMetric()
    CIRCUIT_BREAKER_TRANSITIONS = _NoopMetric()
else:
    PROMETHEUS_AVAILABLE = True
    REGISTRY = CollectorRegistry()

    REQUEST_COUNT = Counter(
        "rag_requests_total",
        "Total number of /api/ask requests",
        ["route"],
        registry=REGISTRY,
    )

    REQUEST_DURATION = Histogram(
        "rag_request_duration_seconds",
        "Request processing time",
        buckets=(0.5, 1, 2, 3, 5, 8, 10, 15, 30),
        registry=REGISTRY,
    )

    QUALITY_SCORE = Summary(
        "rag_quality_score",
        "Quality scores from self-evaluation",
        registry=REGISTRY,
    )

    ESCALATION_TOTAL = Counter(
        "rag_escalation_total",
        "Total escalations to human",
        registry=REGISTRY,
    )

    FEEDBACK_COUNT = Counter(
        "rag_feedback_total",
        "Feedback events",
        ["rating"],
        registry=REGISTRY,
    )

    ACTIVE_SESSIONS = Gauge(
        "rag_active_sessions",
        "Number of active sessions",
        registry=REGISTRY,
    )

    VECTOR_STORE_DOCS = Gauge(
        "rag_vector_store_documents",
        "Number of documents in vector store",
        registry=REGISTRY,
    )

    CIRCUIT_BREAKER_STATE = Gauge(
        "rag_circuit_breaker_state",
        "Current circuit breaker state: 0=closed, 1=half_open, 2=open",
        ["name"],
        registry=REGISTRY,
    )

    CIRCUIT_BREAKER_TRANSITIONS = Counter(
        "rag_circuit_breaker_transitions_total",
        "Total circuit breaker state transitions",
        ["name", "to_state"],
        registry=REGISTRY,
    )


_STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def record_circuit_breaker_change(name: str, from_state: str, to_state: str) -> None:
    CIRCUIT_BREAKER_STATE.labels(name=name).set(_STATE_VALUE.get(to_state, 0))
    if from_state != to_state:
        CIRCUIT_BREAKER_TRANSITIONS.labels(name=name, to_state=to_state).inc()

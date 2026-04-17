"""Prometheus metrics для RAG Support Assistant."""
from __future__ import annotations

from typing import Any

__all__ = [
    "ACTIVE_SESSIONS",
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

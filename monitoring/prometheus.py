"""Prometheus metrics для RAG Support Assistant."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "ACTIVE_SESSIONS",
    "AUTH_FAILURES",
    "AUDIT_PURGED",
    "BODY_SIZE_REJECTIONS",
    "COMPONENT_UP",
    "CIRCUIT_BREAKER_STATE",
    "CIRCUIT_BREAKER_TRANSITIONS",
    "CONTENT_TYPE_LATEST",
    "CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS",
    "CURATED_DATASET_SIZE",
    "DB_POOL_CHECKED_OUT",
    "DB_POOL_OVERFLOW",
    "DB_POOL_SIZE",
    "EVAL_DRIFT",
    "ESCALATION_TOTAL",
    "FACT_VERIFICATION_CONSENSUS_TOTAL",
    "FACTUALITY_SCORE",
    "FEEDBACK_COUNT",
    "HTTP_REQUESTS",
    "HTTP_REQUEST_DURATION",
    "LLM_COST_USD_TOTAL",
    "LLM_PROVIDER_FALLBACK_TOTAL",
    "LLM_CACHE_HITS",
    "LLM_CACHE_MISSES",
    "MESSAGE_PERSIST_FAILURES",
    "OLLAMA_RETRY_EVENTS",
    "ONLINE_EVALUATORS_DROPPED",
    "ONLINE_EVALUATOR_ERRORS_TOTAL",
    "ONLINE_EVALUATOR_RUNS_TOTAL",
    "ONLINE_EVALUATOR_SCORE",
    "PROMETHEUS_AVAILABLE",
    "PIPELINE_REJECTIONS",
    "QUALITY_SCORE",
    "QUALITY_SCORE_SOURCE_TOTAL",
    "RATE_LIMIT_REJECTIONS",
    "RETRIEVER_BM25_ENABLED",
    "REGRESSION_LAST_PASS_RATE",
    "REGRESSION_RUNS_DURATION",
    "REGRESSION_RUNS_TOTAL",
    "REGISTRY",
    "REVIEW_QUEUE_CONFIRMED_TOTAL",
    "REVIEW_QUEUE_OLDEST_PENDING_SECONDS",
    "REVIEW_QUEUE_PENDING_TOTAL",
    "REQUEST_COUNT",
    "REQUEST_DURATION",
    "REQUEST_TIMEOUTS",
    "STALE_IMPORTANT_DOCS",
    "TRACES_PURGED",
    "INFLIGHT_PIPELINES",
    "MODEL_ROUTING",
    "VECTOR_STORE_DOCS",
    "generate_latest",
    "record_component_health",
    "record_llm_cost",
    "record_provider_fallback",
    "record_http_request",
    "record_audit_purged",
    "record_auth_failure",
    "record_body_size_rejection",
    "set_curated_dataset_last_build_timestamp",
    "set_curated_dataset_size",
    "record_db_pool_stats",
    "record_eval_drift",
    "record_circuit_breaker_change",
    "record_message_persist_failure",
    "record_ollama_retry_event",
    "record_online_evaluator_error",
    "record_online_evaluator_run",
    "record_online_evaluators_dropped",
    "record_quality_score_source",
    "record_model_routing",
    "record_pipeline_rejection",
    "record_regression_run",
    "record_rate_limit_rejection",
    "record_request_timeout",
    "set_review_queue_confirmed",
    "set_review_queue_oldest_pending",
    "set_review_queue_pending",
    "set_regression_last_pass_rate",
    "set_retriever_bm25_enabled",
    "record_stale_important_docs",
    "record_traces_purged",
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

    def dec(self, amount: float = 1.0) -> None:
        _ = amount

    def observe(self, value: float) -> None:
        _ = value

    def set(self, value: float) -> None:
        _ = value


if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram, Summary

    # Each metric global below is bound to a real prometheus class when the
    # optional dependency is installed (the `else` branch) and to a _NoopMetric
    # otherwise (the `except` branch). Declare the union for both so mypy stops
    # inferring the type from whichever assignment it sees first. Grouped by the
    # prometheus metric kind; every call site uses a method present on both
    # arms (inc/observe/set), so the union needs no per-call narrowing.
    _CounterT = Counter | _NoopMetric
    _GaugeT = Gauge | _NoopMetric
    _HistogramT = Histogram | _NoopMetric
    _SummaryT = Summary | _NoopMetric

    REQUEST_COUNT: _CounterT
    HTTP_REQUESTS: _CounterT
    LLM_COST_USD_TOTAL: _CounterT
    LLM_PROVIDER_FALLBACK_TOTAL: _CounterT
    ESCALATION_TOTAL: _CounterT
    FACT_VERIFICATION_CONSENSUS_TOTAL: _CounterT
    FEEDBACK_COUNT: _CounterT
    CIRCUIT_BREAKER_TRANSITIONS: _CounterT
    OLLAMA_RETRY_EVENTS: _CounterT
    ONLINE_EVALUATOR_RUNS_TOTAL: _CounterT
    ONLINE_EVALUATOR_ERRORS_TOTAL: _CounterT
    MODEL_ROUTING: _CounterT
    RATE_LIMIT_REJECTIONS: _CounterT
    REGRESSION_RUNS_TOTAL: _CounterT
    REQUEST_TIMEOUTS: _CounterT
    PIPELINE_REJECTIONS: _CounterT
    LLM_CACHE_HITS: _CounterT
    LLM_CACHE_MISSES: _CounterT
    TRACES_PURGED: _CounterT
    AUDIT_PURGED: _CounterT
    AUTH_FAILURES: _CounterT
    BODY_SIZE_REJECTIONS: _CounterT
    QUALITY_SCORE_SOURCE_TOTAL: _CounterT
    MESSAGE_PERSIST_FAILURES: _CounterT
    ONLINE_EVALUATORS_DROPPED: _CounterT

    REQUEST_DURATION: _HistogramT
    HTTP_REQUEST_DURATION: _HistogramT
    ONLINE_EVALUATOR_SCORE: _HistogramT
    REGRESSION_RUNS_DURATION: _HistogramT

    QUALITY_SCORE: _SummaryT
    FACTUALITY_SCORE: _SummaryT

    ACTIVE_SESSIONS: _GaugeT
    VECTOR_STORE_DOCS: _GaugeT
    CIRCUIT_BREAKER_STATE: _GaugeT
    COMPONENT_UP: _GaugeT
    DB_POOL_SIZE: _GaugeT
    DB_POOL_CHECKED_OUT: _GaugeT
    DB_POOL_OVERFLOW: _GaugeT
    REGRESSION_LAST_PASS_RATE: _GaugeT
    REVIEW_QUEUE_PENDING_TOTAL: _GaugeT
    REVIEW_QUEUE_CONFIRMED_TOTAL: _GaugeT
    REVIEW_QUEUE_OLDEST_PENDING_SECONDS: _GaugeT
    STALE_IMPORTANT_DOCS: _GaugeT
    INFLIGHT_PIPELINES: _GaugeT
    EVAL_DRIFT: _GaugeT
    CURATED_DATASET_SIZE: _GaugeT
    CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS: _GaugeT
    RETRIEVER_BM25_ENABLED: _GaugeT


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
    HTTP_REQUESTS = _NoopMetric()
    HTTP_REQUEST_DURATION = _NoopMetric()
    LLM_COST_USD_TOTAL = _NoopMetric()
    LLM_PROVIDER_FALLBACK_TOTAL = _NoopMetric()
    QUALITY_SCORE = _NoopMetric()
    FACTUALITY_SCORE = _NoopMetric()
    ESCALATION_TOTAL = _NoopMetric()
    FACT_VERIFICATION_CONSENSUS_TOTAL = _NoopMetric()
    FEEDBACK_COUNT = _NoopMetric()
    ACTIVE_SESSIONS = _NoopMetric()
    VECTOR_STORE_DOCS = _NoopMetric()
    CIRCUIT_BREAKER_STATE = _NoopMetric()
    CIRCUIT_BREAKER_TRANSITIONS = _NoopMetric()
    COMPONENT_UP = _NoopMetric()
    DB_POOL_SIZE = _NoopMetric()
    DB_POOL_CHECKED_OUT = _NoopMetric()
    DB_POOL_OVERFLOW = _NoopMetric()
    OLLAMA_RETRY_EVENTS = _NoopMetric()
    ONLINE_EVALUATOR_SCORE = _NoopMetric()
    ONLINE_EVALUATOR_RUNS_TOTAL = _NoopMetric()
    ONLINE_EVALUATOR_ERRORS_TOTAL = _NoopMetric()
    MODEL_ROUTING = _NoopMetric()
    RATE_LIMIT_REJECTIONS = _NoopMetric()
    REGRESSION_RUNS_TOTAL = _NoopMetric()
    REGRESSION_RUNS_DURATION = _NoopMetric()
    REGRESSION_LAST_PASS_RATE = _NoopMetric()
    REVIEW_QUEUE_PENDING_TOTAL = _NoopMetric()
    REVIEW_QUEUE_CONFIRMED_TOTAL = _NoopMetric()
    REVIEW_QUEUE_OLDEST_PENDING_SECONDS = _NoopMetric()
    REQUEST_TIMEOUTS = _NoopMetric()
    STALE_IMPORTANT_DOCS = _NoopMetric()
    INFLIGHT_PIPELINES = _NoopMetric()
    PIPELINE_REJECTIONS = _NoopMetric()
    LLM_CACHE_HITS = _NoopMetric()
    LLM_CACHE_MISSES = _NoopMetric()
    TRACES_PURGED = _NoopMetric()
    AUDIT_PURGED = _NoopMetric()
    AUTH_FAILURES = _NoopMetric()
    BODY_SIZE_REJECTIONS = _NoopMetric()
    EVAL_DRIFT = _NoopMetric()
    CURATED_DATASET_SIZE = _NoopMetric()
    CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS = _NoopMetric()
    RETRIEVER_BM25_ENABLED = _NoopMetric()
    QUALITY_SCORE_SOURCE_TOTAL = _NoopMetric()
    MESSAGE_PERSIST_FAILURES = _NoopMetric()
    ONLINE_EVALUATORS_DROPPED = _NoopMetric()
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

    HTTP_REQUESTS = Counter(
        "rag_http_requests_total",
        "HTTP requests by method, endpoint, status (all routes, not just /api/ask)",
        ["method", "endpoint", "status"],
        registry=REGISTRY,
    )

    HTTP_REQUEST_DURATION = Histogram(
        "rag_http_request_duration_seconds",
        "HTTP request duration by method and endpoint",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
        registry=REGISTRY,
    )

    LLM_COST_USD_TOTAL = Counter(
        "llm_cost_usd_total",
        "Accumulated LLM cost in USD grouped by provider, model, and tenant",
        ["provider", "model", "tenant"],
        registry=REGISTRY,
    )

    LLM_PROVIDER_FALLBACK_TOTAL = Counter(
        "llm_provider_fallback_total",
        "Automatic provider failover events grouped by primary, fallback, and reason",
        ["from_provider", "to_provider", "reason"],
        registry=REGISTRY,
    )

    QUALITY_SCORE = Summary(
        "rag_quality_score",
        "Quality scores from self-evaluation",
        registry=REGISTRY,
    )

    FACTUALITY_SCORE = Summary(
        "rag_factuality_score",
        "Share of answer claims supported by retrieved context (0-100)",
        registry=REGISTRY,
    )

    ESCALATION_TOTAL = Counter(
        "rag_escalation_total",
        "Total escalations to human",
        registry=REGISTRY,
    )

    FACT_VERIFICATION_CONSENSUS_TOTAL = Counter(
        "rag_fact_verification_consensus_total",
        "Structured fact verification verdicts grouped by reliability level",
        ["level", "verdict"],
        registry=REGISTRY,
    )

    EXPERIMENT_AUTO_ROLLBACK_TOTAL = Counter(
        "rag_experiment_auto_rollback_total",
        "Auto-rollback events triggered by the drift watcher",
        ["experiment_id", "reason"],
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

    COMPONENT_UP = Gauge(
        "rag_component_up",
        "Health status of a dependency component: 1=ok, 0=error. "
        "Absent when the component is not configured/installed (unavailable).",
        ["component"],
        registry=REGISTRY,
    )

    DB_POOL_SIZE = Gauge(
        "rag_db_pool_size",
        "SQLAlchemy pool size (permanent connections)",
        registry=REGISTRY,
    )

    DB_POOL_CHECKED_OUT = Gauge(
        "rag_db_pool_checked_out",
        "SQLAlchemy pool connections currently in use",
        registry=REGISTRY,
    )

    DB_POOL_OVERFLOW = Gauge(
        "rag_db_pool_overflow",
        "SQLAlchemy pool overflow connections beyond pool_size",
        registry=REGISTRY,
    )

    OLLAMA_RETRY_EVENTS = Counter(
        "rag_ollama_retry_events_total",
        "Retry wrapper events around Ollama calls",
        ["event"],
        registry=REGISTRY,
    )

    ONLINE_EVALUATOR_SCORE = Histogram(
        "online_evaluator_score",
        "Scores emitted by lightweight online evaluators",
        ["evaluator"],
        buckets=(0.1, 0.25, 0.5, 0.75, 0.9, 1.0),
        registry=REGISTRY,
    )

    ONLINE_EVALUATOR_RUNS_TOTAL = Counter(
        "online_evaluator_runs_total",
        "Completed online evaluator runs grouped by evaluator and verdict",
        ["evaluator", "verdict"],
        registry=REGISTRY,
    )

    ONLINE_EVALUATOR_ERRORS_TOTAL = Counter(
        "online_evaluator_errors_total",
        "Errors raised by online evaluators before fallback wrapping",
        ["evaluator"],
        registry=REGISTRY,
    )

    MODEL_ROUTING = Counter(
        "rag_model_routing_total",
        "Classifier decisions: simple routes to fast, complex routes to strong",
        ["complexity"],
        registry=REGISTRY,
    )

    RATE_LIMIT_REJECTIONS = Counter(
        "rag_rate_limit_rejections_total",
        "Requests rejected by slowapi rate limiter",
        ["endpoint"],
        registry=REGISTRY,
    )

    REGRESSION_RUNS_TOTAL = Counter(
        "regression_runs_total",
        "Completed regression runs grouped by result",
        ["result"],
        registry=REGISTRY,
    )

    REGRESSION_RUNS_DURATION = Histogram(
        "regression_runs_duration_seconds",
        "Wall-clock duration of regression runs",
        buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
        registry=REGISTRY,
    )

    REGRESSION_LAST_PASS_RATE = Gauge(
        "regression_last_pass_rate",
        "Most recent candidate pass rate for a baseline/candidate pair",
        ["baseline", "candidate"],
        registry=REGISTRY,
    )

    REVIEW_QUEUE_PENDING_TOTAL = Gauge(
        "review_queue_pending_total",
        "Current review queue size in pending state",
        ["reason"],
        registry=REGISTRY,
    )

    REVIEW_QUEUE_CONFIRMED_TOTAL = Gauge(
        "review_queue_confirmed_total",
        "Current review queue size in confirmed states",
        ["verdict"],
        registry=REGISTRY,
    )

    REVIEW_QUEUE_OLDEST_PENDING_SECONDS = Gauge(
        "review_queue_oldest_pending_seconds",
        "Age of the oldest pending review queue item",
        registry=REGISTRY,
    )

    REQUEST_TIMEOUTS = Counter(
        "rag_request_timeouts_total",
        "Requests exceeding REQUEST_TIMEOUT_SEC wall-time",
        ["endpoint"],
        registry=REGISTRY,
    )

    STALE_IMPORTANT_DOCS = Gauge(
        "rag_stale_important_docs_count",
        "Count of stale documents that are also highly cited",
        registry=REGISTRY,
    )

    INFLIGHT_PIPELINES = Gauge(
        "rag_inflight_pipelines",
        "Number of /api/ask pipelines currently running",
        registry=REGISTRY,
    )

    PIPELINE_REJECTIONS = Counter(
        "rag_pipeline_rejections_total",
        "Requests rejected due to pipeline saturation",
        ["reason"],
        registry=REGISTRY,
    )

    LLM_CACHE_HITS = Counter(
        "llm_cache_hits_total",
        "LLM response cache hits",
        ["tenant"],
        registry=REGISTRY,
    )

    LLM_CACHE_MISSES = Counter(
        "llm_cache_misses_total",
        "LLM response cache misses",
        ["tenant"],
        registry=REGISTRY,
    )

    TRACES_PURGED = Counter(
        "rag_traces_purged_total",
        "SQLite rows deleted by retention purge",
        ["table"],
        registry=REGISTRY,
    )

    AUDIT_PURGED = Counter(
        "rag_audit_purged_total",
        "audit_log rows deleted by retention purge",
        registry=REGISTRY,
    )

    AUTH_FAILURES = Counter(
        "rag_auth_failures_total",
        "Failed /auth/login attempts",
        ["reason"],
        registry=REGISTRY,
    )

    BODY_SIZE_REJECTIONS = Counter(
        "rag_body_size_rejections_total",
        "Requests rejected due to body size limits",
        ["reason"],
        registry=REGISTRY,
    )

    EVAL_DRIFT = Gauge(
        "rag_eval_drift",
        "Relative drift between nightly RAG eval metrics and the rolling baseline",
        ["metric_name"],
        registry=REGISTRY,
    )

    CURATED_DATASET_SIZE = Gauge(
        "curated_dataset_size",
        "Current curated dataset size split by verdict and tenant",
        ["verdict", "tenant"],
        registry=REGISTRY,
    )

    CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS = Gauge(
        "curated_dataset_last_build_timestamp_seconds",
        "Unix timestamp of the latest curated dataset build artifact",
        registry=REGISTRY,
    )

    RETRIEVER_BM25_ENABLED = Gauge(
        "rag_retriever_bm25_enabled",
        "1 when the tenant retriever has an active BM25 index (hybrid search), "
        "0 when it silently degraded to vector-only (e.g. chunks lost on restart)",
        ["tenant"],
        registry=REGISTRY,
    )

    QUALITY_SCORE_SOURCE_TOTAL = Counter(
        "rag_quality_score_source_total",
        "Answers by quality_score provenance: llm (self-eval), heuristic "
        "(streaming length check), fixed (hardcoded agentic constants)",
        ["source"],
        registry=REGISTRY,
    )

    MESSAGE_PERSIST_FAILURES = Counter(
        "rag_message_persist_failures_total",
        "Conversation messages that failed to persist to Postgres (history gap)",
        ["operation"],
        registry=REGISTRY,
    )

    ONLINE_EVALUATORS_DROPPED = Counter(
        "rag_online_evaluators_dropped_total",
        "Online evaluator runs dropped before persisting (timeout or error)",
        ["reason"],
        registry=REGISTRY,
    )

    for _reason in ("thumbs_down", "low_quality", "escalated", "fact_fail", "slow_trace", "manual"):
        REVIEW_QUEUE_PENDING_TOTAL.labels(reason=_reason).set(0)
    for _verdict in ("good", "bad"):
        REVIEW_QUEUE_CONFIRMED_TOTAL.labels(verdict=_verdict).set(0)
    REVIEW_QUEUE_OLDEST_PENDING_SECONDS.set(0)
    CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS.set(0)


_STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def record_component_health(component: str, status: str) -> None:
    """Update the component health gauge."""
    if status == "unavailable":
        return

    value = 1 if status == "ok" else 0
    COMPONENT_UP.labels(component=component).set(value)


def record_db_pool_stats(size: int, checked_out: int, overflow: int) -> None:
    if size >= 0:
        DB_POOL_SIZE.set(size)
    if checked_out >= 0:
        DB_POOL_CHECKED_OUT.set(checked_out)
    if overflow >= 0:
        DB_POOL_OVERFLOW.set(overflow)


def record_http_request(method: str, endpoint: str, status: int, duration_sec: float) -> None:
    HTTP_REQUESTS.labels(
        method=method,
        endpoint=endpoint,
        status=str(status),
    ).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration_sec)


def record_llm_cost(provider: str, model: str, tenant: str, cost_usd: float) -> None:
    if cost_usd <= 0:
        return
    LLM_COST_USD_TOTAL.labels(
        provider=provider,
        model=model,
        tenant=tenant,
    ).inc(float(cost_usd))


def record_provider_fallback(from_provider: str, to_provider: str, reason: str) -> None:
    LLM_PROVIDER_FALLBACK_TOTAL.labels(
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
    ).inc()


def record_circuit_breaker_change(name: str, from_state: str, to_state: str) -> None:
    CIRCUIT_BREAKER_STATE.labels(name=name).set(_STATE_VALUE.get(to_state, 0))
    if from_state != to_state:
        CIRCUIT_BREAKER_TRANSITIONS.labels(name=name, to_state=to_state).inc()


def record_ollama_retry_event(event: str) -> None:
    """Bump the retry counter for a retry wrapper event."""
    OLLAMA_RETRY_EVENTS.labels(event=event).inc()


def record_online_evaluator_run(evaluator: str, verdict: str, score: float) -> None:
    ONLINE_EVALUATOR_RUNS_TOTAL.labels(evaluator=evaluator, verdict=verdict).inc()
    ONLINE_EVALUATOR_SCORE.labels(evaluator=evaluator).observe(
        max(0.0, min(1.0, float(score)))
    )


def record_online_evaluator_error(evaluator: str) -> None:
    ONLINE_EVALUATOR_ERRORS_TOTAL.labels(evaluator=evaluator).inc()


def record_model_routing(complexity: str) -> None:
    MODEL_ROUTING.labels(complexity=complexity).inc()


def record_rate_limit_rejection(endpoint: str) -> None:
    """Increment the rate-limit rejection counter for the request path."""
    RATE_LIMIT_REJECTIONS.labels(endpoint=endpoint).inc()


def record_regression_run(result: str, duration_sec: float) -> None:
    REGRESSION_RUNS_TOTAL.labels(result=result).inc()
    REGRESSION_RUNS_DURATION.observe(max(0.0, float(duration_sec)))


def record_request_timeout(endpoint: str) -> None:
    REQUEST_TIMEOUTS.labels(endpoint=endpoint).inc()


def set_review_queue_pending(reason: str, count: int) -> None:
    REVIEW_QUEUE_PENDING_TOTAL.labels(reason=reason).set(max(0, count))


def set_review_queue_confirmed(verdict: str, count: int) -> None:
    REVIEW_QUEUE_CONFIRMED_TOTAL.labels(verdict=verdict).set(max(0, count))


def set_review_queue_oldest_pending(seconds: float) -> None:
    REVIEW_QUEUE_OLDEST_PENDING_SECONDS.set(max(0.0, float(seconds)))


def set_regression_last_pass_rate(baseline: str, candidate: str, pass_rate: float) -> None:
    REGRESSION_LAST_PASS_RATE.labels(
        baseline=baseline,
        candidate=candidate,
    ).set(max(0.0, float(pass_rate)))


def record_stale_important_docs(count: int) -> None:
    STALE_IMPORTANT_DOCS.set(max(0, count))


def record_pipeline_rejection(reason: str) -> None:
    PIPELINE_REJECTIONS.labels(reason=reason).inc()


def record_traces_purged(table: str, count: int) -> None:
    if count > 0:
        TRACES_PURGED.labels(table=table).inc(count)


def record_audit_purged(count: int) -> None:
    if count > 0:
        AUDIT_PURGED.inc(count)


def record_auth_failure(reason: str) -> None:
    AUTH_FAILURES.labels(reason=reason).inc()


def record_body_size_rejection(reason: str) -> None:
    BODY_SIZE_REJECTIONS.labels(reason=reason).inc()


def record_eval_drift(metric_name: str, value: float) -> None:
    EVAL_DRIFT.labels(metric_name=metric_name).set(value)


def set_curated_dataset_size(verdict: str, tenant: str, count: int) -> None:
    CURATED_DATASET_SIZE.labels(verdict=verdict, tenant=tenant).set(max(0, count))


def set_curated_dataset_last_build_timestamp(timestamp: float) -> None:
    CURATED_DATASET_LAST_BUILD_TIMESTAMP_SECONDS.set(max(0.0, float(timestamp)))


def set_retriever_bm25_enabled(tenant: str, enabled: bool) -> None:
    RETRIEVER_BM25_ENABLED.labels(tenant=tenant or "default").set(1 if enabled else 0)


def record_quality_score_source(source: str) -> None:
    QUALITY_SCORE_SOURCE_TOTAL.labels(source=source or "unknown").inc()


def record_message_persist_failure(operation: str) -> None:
    MESSAGE_PERSIST_FAILURES.labels(operation=operation or "unknown").inc()


def record_online_evaluators_dropped(reason: str) -> None:
    ONLINE_EVALUATORS_DROPPED.labels(reason=reason or "unknown").inc()

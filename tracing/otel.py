"""OpenTelemetry bootstrap with safe no-op behavior when disabled."""
from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any, Literal

# Optional opentelemetry dependency: these module globals start as None and are
# rebound to the real classes by _ensure_dependencies() when the packages are
# installed. Typed as Any so the strict-scope type checker treats them as
# callable/attr-bearing in both the import-present and import-absent states
# (ignore_missing_imports makes the real symbols Any anyway). Runtime unchanged.
trace: Any = None
OTLPSpanExporter: Any = None
Resource: Any = None
TracerProvider: Any = None
BatchSpanProcessor: Any = None
FastAPIInstrumentor: Any = None
HTTPXClientInstrumentor: Any = None
SQLAlchemyInstrumentor: Any = None
RedisInstrumentor: Any = None

_OTEL_INITIALIZED = False


class _NoopSpan:
    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        return False

    def set_attribute(self, key: str, value: object) -> None:
        return None

    def is_recording(self) -> bool:
        return False


class _NoopTracer:
    def start_as_current_span(self, name: str) -> _NoopSpan:
        return _NoopSpan()


def _ensure_dependencies() -> None:
    global BatchSpanProcessor
    global FastAPIInstrumentor
    global HTTPXClientInstrumentor
    global OTLPSpanExporter
    global RedisInstrumentor
    global Resource
    global SQLAlchemyInstrumentor
    global TracerProvider
    global trace

    if all(
        dependency is not None
        for dependency in (
            trace,
            OTLPSpanExporter,
            Resource,
            TracerProvider,
            BatchSpanProcessor,
            FastAPIInstrumentor,
            HTTPXClientInstrumentor,
            SQLAlchemyInstrumentor,
            RedisInstrumentor,
        )
    ):
        return

    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as otel_exporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor as fastapi_instrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor as httpx_instrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor as redis_instrumentor
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor as sqlalchemy_instrumentor,
    )
    from opentelemetry.sdk.resources import Resource as otel_resource
    from opentelemetry.sdk.trace import TracerProvider as otel_provider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor as span_processor

    trace = otel_trace
    OTLPSpanExporter = otel_exporter
    Resource = otel_resource
    TracerProvider = otel_provider
    BatchSpanProcessor = span_processor
    FastAPIInstrumentor = fastapi_instrumentor
    HTTPXClientInstrumentor = httpx_instrumentor
    SQLAlchemyInstrumentor = sqlalchemy_instrumentor
    RedisInstrumentor = redis_instrumentor


def _build_server_request_hook(
    request_id_getter: Callable[[], str | None] | None,
) -> Callable[[Any, dict[str, Any]], None]:
    def hook(span: Any, scope: dict[str, Any]) -> None:
        _ = scope
        if span is None or not getattr(span, "is_recording", lambda: False)():
            return
        if request_id_getter is None:
            return
        request_id = request_id_getter()
        if request_id:
            span.set_attribute("request_id", request_id)

    return hook


def get_tracer(name: str = "rag-support-assistant") -> Any:
    if trace is None:
        return _NoopTracer()
    return trace.get_tracer(name)


def init_otel(
    *,
    service_name: str,
    endpoint: str,
    enabled: bool = True,
    app: Any | None = None,
    sqlalchemy_engine: Any | None = None,
    request_id_getter: Callable[[], str | None] | None = None,
) -> Any:
    global _OTEL_INITIALIZED

    if not enabled:
        return None

    _ensure_dependencies()

    if _OTEL_INITIALIZED:
        return get_tracer(service_name)

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                insecure=endpoint.startswith("http://"),
            )
        )
    )
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    if sqlalchemy_engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine)
    if app is not None:
        FastAPIInstrumentor().instrument_app(
            app,
            server_request_hook=_build_server_request_hook(request_id_getter),
        )

    _OTEL_INITIALIZED = True
    return get_tracer(service_name)

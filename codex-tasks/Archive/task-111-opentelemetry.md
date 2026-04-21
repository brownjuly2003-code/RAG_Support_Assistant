# Task 111 — OpenTelemetry SDK для distributed tracing

## Context
OBS-1 из commercial-plan. Сейчас трейсинг — кастомный SQLite
(`tracing/sqlite_trace.py`) + Langfuse для LLM calls. Langfuse покрывает
только LLM, SQLite — процедурный "journal" не стандартизован. Нет
связки между клиент-запросом и downstream (DB, Redis, external HTTP).

OpenTelemetry = индустриальный стандарт. Traces экспортируются в
Jaeger/Tempo/Datadog, metrics — в Prometheus (уже интегрировано), logs —
структурированно с trace-correlation.

## Goal
Добавить OTel SDK поверх существующей инфры **без удаления** SQLite/
Langfuse на этом этапе. Spans auto-instrumented:
- FastAPI (incoming requests)
- httpx (outgoing к Ollama)
- SQLAlchemy (DB queries)
- Redis client
- LangGraph nodes (manual spans)

Export в OTLP endpoint (Jaeger для dev, Grafana Tempo для prod).

## Files to change
- `requirements.txt` — добавить:
  - `opentelemetry-api`, `opentelemetry-sdk`
  - `opentelemetry-instrumentation-fastapi`, `-httpx`, `-sqlalchemy`, `-redis`
  - `opentelemetry-exporter-otlp`
- `tracing/otel.py` — новый: `init_otel(service_name, endpoint)`:
  настраивает TracerProvider, OTLP exporter, resource attributes
- `api/app.py` — в lifespan startup вызвать `init_otel()` перед созданием
  FastAPI app; применить FastAPIInstrumentor
- `graph.py` — в каждом ключевом node обернуть в `tracer.start_as_current_span`:
  retrieve, rerank, generate, evaluate
- `config/settings.py`:
  - `OTEL_ENABLED: bool = False`
  - `OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"`
  - `OTEL_SERVICE_NAME: str = "rag-support-assistant"`
- `deploy/helm/values.yaml` — секция `otel:` с enabled/endpoint
- `docker-compose.yml` — добавить `jaeger` сервис (dev, all-in-one image)
  для локального просмотра трейсов
- `tests/test_otel.py` — test что tracer init'ится, spans emit'ятся

## Implementation sketch

### tracing/otel.py
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def init_otel(service_name: str, endpoint: str, enabled: bool = True):
    if not enabled:
        return
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    # FastAPI instrumentation — только после создания app:
    # FastAPIInstrumentor.instrument_app(app)
    # SQLAlchemyInstrumentor().instrument(engine=engine)
```

### Manual spans в graph.py
```python
from opentelemetry import trace
tracer = trace.get_tracer("rag.graph")

def retrieve_node(state):
    with tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("rag.question_length", len(state["question"]))
        span.set_attribute("rag.tenant_id", state["tenant_id"])
        docs = retrieve_documents(...)
        span.set_attribute("rag.num_docs", len(docs))
        return {...}
```

### Trace correlation с request_id
Уже есть X-Request-Id middleware (task из арка 68-98). Нужно связать:
OTel sampler → при каждом span устанавливать `attributes["request_id"] = get_request_id()`.

## CONSTRAINTS
- `OTEL_ENABLED=false` default — никаких побочек в тестах
- OTel gRPC exporter требует protobuf; если сложности сборки — fallback
  на HTTP exporter (`opentelemetry-exporter-otlp-proto-http`)
- SQLite tracer оставить как fallback для local dev (где нет Jaeger)
- Langfuse оставить — OTel не заменяет его для LLM-specific аналитики
  (токены, cost, prompts)

## DONE WHEN
- [ ] `OTEL_ENABLED=true` + Jaeger up → трейсы видны в Jaeger UI
      http://localhost:16686
- [ ] Один HTTP /api/ask → span tree: FastAPI → retrieve → rerank →
      generate (with Ollama httpx span) → evaluate
- [ ] `OTEL_ENABLED=false` → pytest passes, никаких OTel errors
- [ ] Helm values включают otel конфиг
- [ ] docker-compose up → Jaeger доступен локально
- [ ] 250+ passed
- [ ] Commit: "OpenTelemetry SDK: distributed tracing w/ auto-instrumentation (task-111)"

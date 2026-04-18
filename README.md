# RAG Support Assistant

Отвечает на вопросы поддержки по базе знаний и решает, можно ли отдать ответ
автоматически или лучше эскалировать запрос человеку.

**Стек:** FastAPI · LangGraph · ChromaDB · локальная LLM через Ollama ·
SQLite для tracing · Postgres для audit/sessions · Redis для cache ·
mock inbox или Bitrix24 для эскалаций.

## Architecture

```text
Пользователь → POST /api/ask
                     ↓
              LangGraph pipeline:
  classify_complexity → transform_query → retrieve → grade_docs
  → generate → verify_facts → evaluate → route_or_retry
                                             ↓         ↓
                                          log     handle_error
                                          ↓              ↓
                                         END      escalate + END
```

- **Retrieval**: ChromaDB (vector) + BM25 hybrid search, Reciprocal Rank Fusion,
  cross-encoder reranking
- **Embeddings**: BGE-M3 (`BAAI/bge-m3`) — multilingual, 1024d
- **Generation**: Ollama/Qwen2.5 7B (локальная LLM). Опциональный A/B routing
  на `llama3.2:3b` для простых вопросов
- **Evaluation**: `quality_score` (0–100) — самооценка модели;
  `factuality_score` (0–100) — доля claim'ов из ответа, подтверждённых
  контекстом
- **Routing**: `auto` / `human` / `retry` / `error`
- **Escalation**: при `route=human` или `route=error` — JSONL inbox или
  Bitrix24 webhook
- **Tracing**: каждый запрос в SQLite (trace_id, nodes, scores, latency)
- **Correlation**: `X-Request-Id` header пробрасывается в лог и в trace_id

## Quick Start

**Prerequisites:** Python 3.11+, `ollama serve`

```bash
# 1. Dependencies
pip install -r requirements.txt

# 2. Start Ollama and pull models
ollama serve
ollama pull qwen2.5:7b
# опционально для A/B routing:
# ollama pull llama3.2:3b

# 3. Run
python main.py
```

Открой:
- **http://localhost:8000** — чат
- **http://localhost:8000/static/admin.html** — admin UI (breaker, traces,
  audit, metrics)
- **http://localhost:8000/static/metrics.html** — dashboard метрик

## Environment Variables

Скопируй `.env.example` → `.env` и поправь по необходимости.

### LLM и модель

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL локального Ollama API |
| `OLLAMA_MODEL_NAME` | `qwen2.5:7b` | основная модель генерации |
| `OLLAMA_FAST_MODEL_NAME` | `llama3.2:3b` | быстрая модель для simple-вопросов и utility-узлов |
| `OLLAMA_REQUEST_TIMEOUT_SEC` | `60` | timeout одного HTTP-вызова к Ollama |
| `MODEL_ROUTING_ENABLED` | `false` | включить classifier + A/B routing fast/strong |
| `REQUIRE_OLLAMA` | `false` | fail-fast на старте, если Ollama недоступна |

### RAG pipeline

| Variable | Default | Description |
|---|---|---|
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | embedding model |
| `RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | reranker |
| `RAG_HYBRID_SEARCH` | `true` | BM25 + vector |
| `RAG_RETRIEVAL_TOP_K` | `20` | кандидаты до rerank |
| `RAG_RERANK_TOP_K` | `5` | документы после rerank |
| `RAG_VECTOR_BACKEND` | `chroma` | vector store |
| `VECTORDB_COLLECTION_PREFIX` | `rag_docs` | префикс ChromaDB collection; полное имя = `{prefix}_{tenant_id}` |
| `RAG_SEMANTIC_CHUNKING` | `false` | семантический chunking |
| `RAG_SELF_RAG_MAX_ITER` | `2` | макс. итераций Self-RAG |
| `RAG_SELF_RAG_MIN_QUALITY` | `70` | минимальный quality_score для route=auto |
| `RAG_HYDE` | `false` | Hypothetical Document Embeddings |
| `RAG_PARENT_CHILD` | `false` | parent-child chunking |
| `FACT_VERIFICATION_ENABLED` | `true` | узел `verify_facts` после generate |
| `FACT_VERIFICATION_MIN_SCORE` | `70` | минимальный factuality_score |

### Resilience (Ollama)

Слои устойчивости применяются в таком порядке:
**timeout → retry → circuit breaker → bounded concurrency → request wall-time.**

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_RETRY_MAX_ATTEMPTS` | `3` | попыток включая первую; 1 = без retry |
| `OLLAMA_RETRY_BASE_DELAY_SEC` | `0.5` | базовая задержка |
| `OLLAMA_RETRY_MAX_DELAY_SEC` | `5.0` | верхняя граница задержки |
| `OLLAMA_RETRY_JITTER` | `true` | jitter ±50% |
| `CIRCUIT_BREAKER_ENABLED` | `true` | CLOSED → OPEN после N подряд идущих ошибок |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | порог ошибок для OPEN |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SEC` | `30` | время до HALF_OPEN пробы |
| `REQUEST_TIMEOUT_SEC` | `30` | wall-time limit на весь `/api/ask`; 504 при превышении |
| `MAX_CONCURRENT_PIPELINES` | `8` | upper bound для `/api/ask`; 503 при saturation |
| `PIPELINE_ACQUIRE_TIMEOUT_SEC` | `0.5` | сколько ждать слот перед 503 |

### Security & Auth

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | — | X-API-Key header (legacy); JWT предпочтительнее |
| `ADMIN_USERNAME` | `admin` | имя admin для `/api/auth/login` |
| `ADMIN_PASSWORD_HASH` | — | bcrypt hash admin-пароля; без него работает dev-режим `admin/admin` |
| `JWT_SECRET` | dev default (≥32 bytes) | секрет для access/refresh token |
| `JWT_ACCESS_TTL` | `3600` | TTL access token (сек) |
| `JWT_REFRESH_TTL` | `604800` | TTL refresh token (сек) |
| `RAG_ENV` | `development` | `development`/`staging`/`production`; в prod `CORS_ORIGINS=*` запрещён |
| `CORS_ORIGINS` | `*` | comma-separated list разрешённых origins |
| `CORS_MAX_AGE_SEC` | `600` | preflight cache TTL |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | 1 MiB лимит тела запроса (кроме `/api/upload`) |
| `MAX_UPLOAD_BYTES` | `52428800` | 50 MiB лимит для `/api/upload` |

### Database & cache

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag_dev_password@localhost:5432/rag_assistant` | Postgres для audit/sessions |
| `REDIS_URL` | `redis://localhost:6379/0` | cache с fallback на in-memory dict |
| `SESSION_TTL_SECONDS` | `7200` | TTL API-сессий |

### Retention & deploy

| Variable | Default | Description |
|---|---|---|
| `TRACE_RETENTION_DAYS` | `90` | retention SQLite traces; 0 = не чистить |
| `TRACE_PURGE_INTERVAL_SEC` | `86400` | интервал фоновой очистки traces |
| `AUDIT_RETENTION_DAYS` | `180` | retention Postgres audit_log |
| `AUDIT_PURGE_INTERVAL_SEC` | `86400` | интервал фоновой очистки audit_log |
| `SHUTDOWN_READY_DELAY_SEC` | `5` | drain period при SIGTERM — readiness→503 перед реальным shutdown |

### Escalation

| Variable | Default | Description |
|---|---|---|
| `SUPPORT_SINK_BACKEND` | `local` | канал эскалации: `local` или `bitrix` |
| `BITRIX_WEBHOOK_URL` | — | URL webhook Bitrix24 |

### Alerting (scripts/check_alerts.py)

| Variable | Default | Description |
|---|---|---|
| `ALERT_WEBHOOK_URL` | — | Slack/Telegram webhook |
| `ALERT_ESCALATION_PCT` | `35` | порог % эскалаций (24h) |
| `ALERT_QUALITY_MIN` | `65` | минимальный avg quality (7d) |
| `ALERT_P95_LATENCY_SEC` | `12` | порог p95 latency (24h) |
| `ALERT_THUMBS_DOWN_PCT` | `20` | порог % thumbs-down (7d) |

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/ask` | user | задать вопрос (sync, JSON); 60 req/min |
| POST | `/api/ask/stream` | user | задать вопрос (SSE streaming) |
| POST | `/api/upload` | agent/admin | загрузить документ; 10 req/min |
| POST | `/api/feedback` | user | оценить ответ (up/down) |
| POST | `/api/auth/login` | — | получить JWT; 5 req/min |
| POST | `/api/auth/refresh` | — | обменять refresh token |
| GET | `/api/health` | — | alias readiness |
| GET | `/api/health/live` | — | liveness probe: 200 пока процесс отвечает |
| GET | `/api/health/ready` | — | readiness probe: полная проверка зависимостей |
| GET | `/api/metrics` | — | JSON-снапшот метрик (latency, quality, escalation) |
| GET | `/metrics` | — | Prometheus exposition format |
| GET | `/api/sessions` | user | список активных сессий |
| GET | `/api/sessions/{id}/history` | user | история сессии |
| DELETE | `/api/sessions/{id}` | user | удалить сессию |
| GET | `/api/feedback/stats` | — | статистика обратной связи |
| GET | `/api/admin/audit` | agent/admin | audit_log entries (filters: actor, action, limit) |
| GET | `/api/admin/traces` | agent/admin | список недавних traces |
| GET | `/api/admin/traces/{trace_id}` | agent/admin | полный trace с шагами + feedback |
| DELETE | `/api/admin/traces?older_than_days=N` | admin | очистка старых traces |
| DELETE | `/api/admin/audit-log?older_than_days=N` | admin | очистка audit_log |
| POST | `/api/admin/circuit-breaker/reset` | admin | форсированный сброс breaker |

**Rate limits**: 60 req/min на `/api/ask`, 10 req/min на `/api/upload`,
5 req/min на `/api/auth/login` (per client IP).

**Correlation ID**: клиент может прислать `X-Request-Id` в запросе
(regex `^[A-Za-z0-9_\-:.]{1,128}$`). Сервер возвращает его в response-header
и использует как `trace_id` в SQLite; если не прислан — генерирует UUID4 hex.

## Monitoring

Три независимых observability-плоскости:

### 1. `GET /api/metrics` — JSON-снапшот из SQLite

```json
{
  "latency": {"p50_sec": 2.1, "p95_sec": 8.4, "p99_sec": 14.2, "window": "24h"},
  "escalation": {"total_traces": 120, "escalated": 18, "rate_pct": 15.0, "window": "24h"},
  "quality": {"scored_traces": 840, "avg_quality": 78.3, "low_quality_share_pct": 12.5, "window": "7d"},
  "errors": {"total_started": 120, "likely_failed": 2, "likely_failure_rate_pct": 1.7, "window": "24h"},
  "feedback": {"total": 95, "thumbs_down": 11, "thumbs_down_rate_pct": 11.6, "window": "7d"}
}
```

Страница `/static/metrics.html` показывает этот снапшот с цветовой
индикацией и автообновлением каждые 30 сек.

### 2. `GET /metrics` — Prometheus

Экспортирует метрики для Grafana/Alertmanager:

- **HTTP**: `rag_http_requests_total{method, endpoint, status}`,
  `rag_http_request_duration_seconds`, `rag_requests_total{route}`
- **Resilience**: `rag_circuit_breaker_state{name}`,
  `rag_circuit_breaker_transitions_total{name, to_state}`,
  `rag_ollama_retry_events_total{event}`, `rag_request_timeouts_total`,
  `rag_inflight_pipelines`, `rag_pipeline_rejections_total{reason}`
- **Health**: `rag_component_up{component}`, `rag_db_pool_size`,
  `rag_db_pool_checked_out`, `rag_db_pool_overflow`
- **Quality**: `rag_quality_score`, `rag_factuality_score`,
  `rag_model_routing_total{complexity}`, `rag_escalation_total`,
  `rag_feedback_total{rating}`
- **Security**: `rag_auth_failures_total{reason}`,
  `rag_rate_limit_rejections_total{endpoint}`,
  `rag_body_size_rejections_total{reason}`
- **Ops**: `rag_traces_purged_total{table}`, `rag_audit_purged_total`

### 3. Prometheus alert rules

`monitoring/alert_rules.yml` содержит готовые alert-правила в 4 группах:
`rag-resilience`, `rag-health`, `rag-quality`, `rag-latency`. Подключаются
через `rule_files` в `prometheus.yml`.

### SQLite alert checker (альтернатива Prometheus)

`scripts/check_alerts.py` — cron каждые 5 минут, дергает webhook при
пороговых значениях из ALERT_*:

```bash
python scripts/check_alerts.py --dry-run
```

## Multi-tenancy

В проект встроена tenant-isolation:
- JWT access-token несёт claim `tenant`
- traces, audit log и admin read/purge endpoints фильтруются по `tenant_id`
- ChromaDB использует per-tenant collections вида `rag_docs_{tenant_id}`
- retriever cache изолирован по tenant

Для существующей legacy collection `rag_docs` используйте одноразовую
миграцию:

```bash
python scripts/migrate_default_collection.py
```

## Web UI

- `/` — чат (светлая/тёмная тема, SSE streaming, upload)
- `/static/help.html` — справка для пользователей
- `/static/metrics.html` — dashboard метрик с автообновлением
- `/static/admin.html` — admin UI: breaker reset, traces, audit, metrics.
  Token хранится в localStorage.

## Tests

```bash
pytest tests/ -v
```

~200 тестов, все должны проходить. При flaky-фейле в
`test_rate_limiting.py` перезапустить — slowapi делит state между тестами.

## Docker

```bash
cp .env.example .env
# настроить OLLAMA_BASE_URL, DATABASE_URL и т.д.
docker compose up
```

Для k8s: liveness-probe на `/api/health/live`, readiness — на
`/api/health/ready`. При SIGTERM сервер flip'ает readiness в 503 за
`SHUTDOWN_READY_DELAY_SEC` секунд до реального shutdown'а, чтобы LB
успел снять pod с rotation.

## Project structure

```
api/              FastAPI app: endpoints, middleware, correlation ID
auth/             JWT handler + RBAC dependencies
cache/            Redis cache with in-memory fallback
channels/         Telegram bot, widget embed
config/           settings.py, logging_config.py
db/               SQLAlchemy engine, models, audit helpers
deploy/           docker-compose, helm chart
evaluation/       RAGAS-style eval, test_cases.json, benchmark runner
graph.py          LangGraph pipeline + nodes
ingestion/        document ingestion pipeline
monitoring/       prometheus.py (metrics), alert_rules.yml
scripts/          check_alerts.py, eval_gate.py
sqlite_trace.py   SQLite tracing + retention purge
static/           chat.html, admin.html, metrics.html, help.html
templates/        Jinja2 HTML templates
tests/            pytest suite
tracing/          langfuse_trace.py
utils/            circuit_breaker, retry, pii redaction
vectordb/         ChromaDB manager + BM25 + reranking
alembic/          migrations (001 initial, 002 users/audit, 003 tenant_id)
codex-tasks/      ждущие задачи для Codex (+ Archive/ для завершённых)
docs/research/    aрхив исследований (rag-landscape-2026, llm-model-selection-2025, ...)
```

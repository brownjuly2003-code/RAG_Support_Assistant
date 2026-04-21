# RAG Support Assistant

[![CI](https://github.com/<user>/RAG_Support_Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/<user>/RAG_Support_Assistant/actions/workflows/ci.yml)

Answers support questions against a knowledge base and decides whether a
request can be resolved automatically or should be escalated to a human.

This README is the source of truth for runtime configuration, public HTTP
endpoints, and Prometheus metric inventory.

**Stack:** FastAPI · LangGraph · ChromaDB · local LLMs via Ollama · SQLite for
trace snapshots · Postgres for sessions/audit/copilot/analytics · Redis for
cache · OpenTelemetry · email/Bitrix escalation channels.

## Architecture

```text
User / Email / Widget
        |
        v
  FastAPI + Auth (JWT / OIDC / RBAC)
        |
        v
  LangGraph pipeline / agent graph
    classify -> retrieve -> rerank -> generate -> verify -> evaluate
          \-> tool calls (search_kb / check_order_status / create_ticket)
        |
        +-> ChromaDB + BM25 + category metadata
        +-> Ollama models
        +-> Postgres (sessions, audit, copilot, analytics)
        +-> Redis cache
        +-> SQLite traces + OTel spans
```

- **Retrieval:** ChromaDB (vector) + BM25 hybrid search, Reciprocal Rank
  Fusion, cross-encoder reranking, contextual headers, and optional document
  category metadata.
- **Generation:** Ollama/Qwen2.5 7B is the default answer model, with optional
  routing to `llama3.2:3b` for cheaper helper flows. Responses can include
  inline citations `[N]` backed by retrieved documents.
- **Agent layer:** Feature-flagged tool use supports multi-step reasoning,
  confirmation-gated irreversible actions, and agent-side ticket creation.
- **Routing:** Requests resolve to `auto`, `human`, `retry`, or `error`
  depending on quality, factuality, and downstream tool outcomes.
- **Channels:** The same backend powers the web chat, agent copilot, and email
  ingestion/reply paths.
- **Security:** JWT auth, Google/Microsoft OIDC SSO, tenant isolation, and
  `pgcrypto` column encryption protect enterprise deployments.
- **Observability:** Request traces are written to SQLite, optional OpenTelemetry
  exports spans to Jaeger/Tempo, and Prometheus exposes operational metrics.
- **Knowledge loops:** Nightly eval drift checks, KB gap clustering, KB draft
  generation, freshness alerts, and weekly reports keep the knowledge base
  improving over time.

## Features

- **Inline citations and source panel:** Answers can embed `[N]` markers that
  resolve to retrieved documents, excerpts, and a dedicated source panel.
- **Mobile-first UI:** `chat`, `help`, `metrics`, `admin`, `agent`, `analytics`,
  and `login` pages ship responsive layouts for phone, tablet, and desktop.
- **WCAG 2.1 AA improvements:** Static pages include accessible labels, visible
  focus states, keyboard-friendly dialogs, and stronger screen-reader support.
- **Chat polish:** Upload progress, retry flows, onboarding prompts, skeleton
  states, and clearer error handling reduce dead-end interactions.
- **Agent copilot:** `/agent` and `/static/agent.html` expose escalated ticket
  queues, conversation context, AI drafts, and similar resolved tickets.
- **Agentic tool use:** The graph can call KB search, order-status, and
  ticket-creation tools, with confirmation required for irreversible actions.
- **Nightly evaluation:** `scripts/nightly_eval.py` runs RAGAS-style checks on
  recent traces and stores drift against a rolling baseline.
- **Knowledge-gap detection:** `scripts/kb_gap_detector.py` clusters unresolved
  questions into admin-visible KB gap records.
- **Contextual ingestion:** New uploads can prepend contextual headers before
  embedding, and `scripts/reindex.py` reprocesses existing documents.
- **OpenTelemetry tracing:** FastAPI, httpx, SQLAlchemy, Redis, and graph nodes
  emit distributed traces to OTLP collectors.
- **OIDC SSO:** Google and Microsoft sign-in flows issue the same application
  JWTs used by password login.
- **Encryption at rest:** Sensitive Postgres columns are encrypted with
  `pgcrypto` and an external `DB_ENCRYPTION_KEY`.
- **Knowledge Builder:** `scripts/kb_builder.py` clusters resolved tickets into
  reviewable KB drafts that admins can publish back into the vector store.
- **Freshness monitoring:** Citation counts plus document age highlight
  stale-but-important documents for review.
- **Auto-categorization:** Uploads are classified into categories from
  `config/categories.yml`, and those categories are stored in document metadata.
- **Analytics dashboard:** `/static/analytics.html` visualizes top topics,
  resolution rates, quality trends, and LLM cost summaries.
- **Weekly reports:** Markdown digests can be pushed through Slack or email on
  a weekly schedule.
- **Email channel:** Incoming support mail can be processed through IMAP
  polling or an inbound webhook, then routed through the same RAG flow.
- **Canonical module layout:** Core agent modules now live under `agent/*`,
  while root-level imports remain as compatibility shims.
- **Centralized tuning:** Retrieval thresholds and operational constants are
  concentrated in `config/settings.py` instead of scattered literals.
- **Integration test suite:** `tests/integration/` covers ingestion,
  conversation, streaming, concurrency, escalation, and async upload paths.

## Quick Start

**Prerequisites:** Python 3.11+, `ollama serve`

```bash
# 1. Dependencies
pip install -r requirements.txt

# 2. Start Ollama and pull models
ollama serve
ollama pull qwen2.5:7b
# Optional fast/helper model:
# ollama pull llama3.2:3b

# 3. Run
python main.py
```

Open:
- **http://localhost:8000** - chat UI
- **http://localhost:8000/static/login.html** - password + SSO login page
- **http://localhost:8000/static/admin.html** - admin UI for traces, audit,
  KB gaps, KB drafts, stale docs, and breaker controls
- **http://localhost:8000/agent** - agent copilot dashboard
- **http://localhost:8000/static/analytics.html** - analytics dashboard
- **http://localhost:8000/static/metrics.html** - system metrics dashboard

## Environment Variables

Copy `.env.example` to `.env`, then adjust only what your deployment needs.

### LLM and models

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL for the local Ollama API |
| `OLLAMA_MODEL_NAME` | `qwen2.5:7b` | Primary answer-generation model |
| `OLLAMA_FAST_MODEL_NAME` | `llama3.2:3b` | Faster model for routing, categorization, and helper/tool flows |
| `MODEL_ROUTING_ENABLED` | `false` | Enable simple/complex model routing |
| `OLLAMA_REQUEST_TIMEOUT_SEC` | `60` | Timeout for a single Ollama HTTP request |
| `REQUIRE_OLLAMA` | `false` | Fail fast at startup if Ollama is unavailable |
| `LANGFUSE_PUBLIC_KEY` | `-` | Optional Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `-` | Optional Langfuse secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host for LLM observability |

### RAG pipeline

| Variable | Default | Description |
|---|---|---|
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model used for documents and queries |
| `RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder reranker |
| `RAG_HYBRID_SEARCH` | `true` | Combine BM25 with vector retrieval |
| `RAG_RETRIEVAL_TOP_K` | `20` | Candidate documents fetched before reranking |
| `RAG_RERANK_TOP_K` | `5` | Final document count after reranking |
| `RRF_K` | `60` | Reciprocal Rank Fusion smoothing constant |
| `RRF_DOC_KEY_CHARS` | `200` | Prefix length used to deduplicate RRF document keys |
| `QUALITY_THRESHOLD` | `80` | Default quality threshold used by routing/evaluation logic |
| `CHUNK_SIZE` | `800` | Default chunk size for ingestion |
| `CHUNK_OVERLAP` | `200` | Default chunk overlap for ingestion |
| `API_DEFAULT_PAGE_SIZE` | `50` | Default page size for list-style admin endpoints |
| `RAG_SEMANTIC_CHUNKING` | `true` | Enable semantic chunking |
| `RAG_CONTEXTUAL_HEADERS` | `true` | Prepend contextual headers during ingestion |
| `RAG_AGENTIC_MODE` | `false` | Enable the tool-calling agent graph |
| `RAG_HYDE` | `false` | Enable Hypothetical Document Embeddings |
| `RAG_PARENT_CHILD` | `false` | Enable parent-child chunking |
| `RAG_SELF_RAG_MAX_ITER` | `2` | Maximum Self-RAG iterations |
| `RAG_SELF_RAG_MIN_QUALITY` | `70` | Minimum quality score to avoid retry/escalation |
| `FACT_VERIFICATION_ENABLED` | `true` | Run fact verification after generation |
| `FACT_VERIFICATION_MIN_SCORE` | `70` | Minimum factuality score threshold |
| `RAG_VECTOR_BACKEND` | `chroma` | Vector store backend |
| `VECTORDB_COLLECTION_PREFIX` | `rag_docs` | Chroma collection prefix; full name is `{prefix}_{tenant_id}` |
| `CATEGORIES_CONFIG_PATH` | `config/categories.yml` | Taxonomy file for upload auto-categorization |

### Resilience and capacity

Resilience layers apply in this order:
**timeout -> retry -> circuit breaker -> bounded concurrency -> request wall-time**

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_RETRY_MAX_ATTEMPTS` | `3` | Retry attempts including the first call; `1` disables retries |
| `OLLAMA_RETRY_BASE_DELAY_SEC` | `0.5` | Base retry delay |
| `OLLAMA_RETRY_MAX_DELAY_SEC` | `5.0` | Maximum retry delay |
| `OLLAMA_RETRY_JITTER` | `true` | Apply jitter to retry delays |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable circuit-breaker protection for Ollama |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before the breaker opens |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SEC` | `30` | Delay before half-open probing |
| `REQUEST_TIMEOUT_SEC` | `30` | Wall-time limit for one `/api/ask` request |
| `MAX_CONCURRENT_PIPELINES` | `8` | Maximum concurrent `/api/ask` pipelines |
| `PIPELINE_ACQUIRE_TIMEOUT_SEC` | `0.5` | How long to wait for a pipeline slot before returning `503` |
| `SESSION_TTL_SECONDS` | `7200` | Session idle timeout in seconds |

### Security and auth

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `-` | Legacy `X-API-Key` protection for API endpoints; JWT is preferred |
| `ADMIN_USERNAME` | `admin` | Username for `/api/auth/login` |
| `ADMIN_PASSWORD_HASH` | `-` | Bcrypt password hash; if empty, dev mode accepts `admin/admin` |
| `JWT_SECRET` | `dev-secret-change-in-production!` | Secret for access/refresh tokens |
| `JWT_ACCESS_TTL` | `3600` | Access-token TTL in seconds |
| `JWT_REFRESH_TTL` | `604800` | Refresh-token TTL in seconds |
| `SESSION_SECRET_KEY` | `JWT_SECRET` fallback | Secret used by `SessionMiddleware` and OIDC state cookies |
| `GOOGLE_OIDC_CLIENT_ID` | `-` | Google OIDC client ID |
| `GOOGLE_OIDC_CLIENT_SECRET` | `-` | Google OIDC client secret |
| `AZURE_OIDC_TENANT` | `-` | Azure AD tenant used for issuer discovery |
| `AZURE_OIDC_CLIENT_ID` | `-` | Azure AD OIDC client ID |
| `AZURE_OIDC_CLIENT_SECRET` | `-` | Azure AD OIDC client secret |
| `TENANT_EMAIL_DOMAINS` | `""` | Domain-to-tenant mapping, for example `acme.com:tenant-acme,beta.io:tenant-beta` |
| `RAG_ENV` | `development` | `development`, `staging`, or `production` |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins; `*` is forbidden in production |
| `CORS_MAX_AGE_SEC` | `600` | Preflight cache TTL |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | 1 MiB request-body limit for non-upload endpoints |
| `MAX_UPLOAD_BYTES` | `52428800` | 50 MiB upload limit for `/api/upload` |

### Database, cache, tracing, and analytics

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | `rag_dev_password` | Local Compose password for the Postgres container |
| `DATABASE_URL` | `postgresql://rag:rag_dev_password@localhost:5432/rag_assistant` | Postgres DSN for sessions, audit, analytics, and copilot data |
| `DB_ENCRYPTION_KEY` | dev fallback | Key used by `pgcrypto`; required in production and for migration `008` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache URL |
| `LLM_CACHE_ENABLED` | `false` | Enable tenant-scoped response caching for `/api/ask` |
| `LLM_CACHE_TTL_SECONDS` | `3600` | TTL for cached LLM responses |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry SDK + instrumentation |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint for Jaeger/Tempo/collectors |
| `OTEL_SERVICE_NAME` | `rag-support-assistant` | `service.name` resource attribute |
| `LLM_COST_PER_1M_TOKENS` | `qwen2.5:0.0,gpt-4:10.0` | Model-to-price mapping used by analytics cost summaries |
| `TRACE_RETENTION_DAYS` | `90` | Retention window for SQLite traces; `0` disables purge |
| `TRACE_PURGE_INTERVAL_SEC` | `86400` | Background trace-purge interval |
| `AUDIT_RETENTION_DAYS` | `180` | Retention window for `audit_log` |
| `AUDIT_PURGE_INTERVAL_SEC` | `86400` | Background audit purge interval |
| `SHUTDOWN_READY_DELAY_SEC` | `5` | Drain delay between readiness flip and shutdown |

### Channels, escalation, and reporting

| Variable | Default | Description |
|---|---|---|
| `SUPPORT_SINK_BACKEND` | `local` | Escalation backend: `local` or `bitrix` |
| `BITRIX_WEBHOOK_URL` | `-` | Bitrix24 webhook URL |
| `TELEGRAM_BOT_TOKEN` | `-` | Optional Telegram bot token |
| `ALERT_WEBHOOK_URL` | `-` | Webhook used by `scripts/check_alerts.py` |
| `ALERT_ESCALATION_PCT` | `35` | Escalation-rate alert threshold over 24h |
| `ALERT_QUALITY_MIN` | `65` | Minimum 7-day average quality |
| `ALERT_LOW_QUALITY_PCT` | `30` | Threshold for low-quality answer share |
| `ALERT_P95_LATENCY_SEC` | `12` | 24h p95 latency alert threshold |
| `ALERT_THUMBS_DOWN_PCT` | `20` | 7-day thumbs-down threshold |
| `ALERT_THUMBS_DOWN_MIN_N` | `50` | Minimum feedback volume before thumbs-down alerts trigger |
| `REPORT_SLACK_WEBHOOK` | `-` | Slack webhook for weekly reports |
| `REPORT_EMAIL_RECIPIENTS` | `""` | Comma-separated email list for weekly reports |
| `REPORT_SMTP_HOST` | `SMTP_HOST` fallback | SMTP host override for weekly reports |
| `REPORT_SMTP_PORT` | `SMTP_PORT` fallback or `587` | SMTP port override for weekly reports |
| `REPORT_SMTP_USER` | `SMTP_USER` fallback | SMTP user override for weekly reports |
| `REPORT_SMTP_PASS` | `SMTP_PASS` fallback | SMTP password override for weekly reports |
| `EMAIL_CHANNEL_MODE` | `disabled` | Email channel mode: `disabled`, `imap`, or `webhook` |
| `IMAP_HOST` | `""` | IMAP server hostname |
| `IMAP_PORT` | `993` | IMAP server port |
| `IMAP_USER` | `""` | IMAP username |
| `IMAP_PASS` | `-` | IMAP password |
| `IMAP_FOLDER` | `INBOX` | IMAP folder polled by `scripts/email_poller.py` |
| `SMTP_HOST` | `""` | SMTP hostname for email replies |
| `SMTP_PORT` | `587` | SMTP port for email replies |
| `SMTP_USER` | `""` | SMTP username |
| `SMTP_PASS` | `-` | SMTP password |
| `SMTP_FROM_ADDRESS` | `support@example.com` | Default sender address for outbound replies |
| `EMAIL_WEBHOOK_SECRET` | `-` | Shared secret used to verify inbound email webhooks |

### LLM response caching

- The final `/api/ask` response is cached for `(tenant, normalized_question)`,
  where normalization is `.strip().lower()`.
- Keys look like `llm_resp:{tenant}:{sha256(question)[:16]}`, so the raw
  question is not stored in Redis.
- Uploads invalidate the tenant namespace `llm_resp:{tenant}:*`.

## API

### Core chat and ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/ask` | user | Ask a question synchronously; returns answer, documents, and citations |
| POST | `/api/ask/stream` | user | Ask a question over SSE streaming |
| POST | `/api/upload` | agent/admin | Upload a document for indexing; returns assigned categories |
| GET | `/api/tasks/{task_id}` | agent/admin | Check background upload task state |
| POST | `/api/feedback` | user | Submit thumbs up/down feedback |
| POST | `/api/escalate` | user | Escalate the current request to a human operator |
| GET | `/api/sessions` | agent/admin | List active sessions |
| GET | `/api/sessions/{session_id}/history` | agent/admin | Return session history |
| DELETE | `/api/sessions/{session_id}` | agent/admin | Delete a session |
| GET | `/api/feedback/stats` | agent/admin | Aggregate feedback statistics |

### Agent and admin workflows

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/agent/tickets` | agent/admin | List escalated tickets, optionally filtered by status |
| GET | `/api/agent/tickets/{ticket_id}` | agent/admin | Return ticket details, session messages, and similar tickets |
| POST | `/api/agent/tickets/{ticket_id}/respond` | agent/admin | Save an operator response and resolve a ticket |
| GET | `/api/agent/similar` | agent/admin | Return similar resolved tickets for a given ticket |
| GET | `/api/admin/audit` | agent/admin | List audit-log entries with filters |
| GET | `/api/admin/traces` | agent/admin | List recent traces |
| GET | `/api/admin/traces/{trace_id}` | agent/admin | Return one trace with steps and feedback |
| DELETE | `/api/admin/traces?older_than_days=N` | admin | Purge old traces |
| DELETE | `/api/admin/audit-log?older_than_days=N` | admin | Purge old audit-log entries |
| POST | `/api/admin/circuit-breaker/reset` | admin | Force-reset the Ollama circuit breaker |
| GET | `/api/admin/kb-gaps` | admin | List detected knowledge gaps |
| GET | `/api/admin/categories` | admin | Return the active category taxonomy |
| GET | `/api/admin/kb-drafts` | admin | List Knowledge Builder drafts |
| PATCH | `/api/admin/kb-drafts/{draft_id}` | admin | Edit a pending KB draft |
| POST | `/api/admin/kb-drafts/{draft_id}/reject` | admin | Reject a pending KB draft |
| POST | `/api/admin/kb-drafts/{draft_id}/publish` | admin | Publish a KB draft into the vector store |
| GET | `/api/admin/stale-docs` | admin | List stale but highly cited documents |
| POST | `/api/admin/stale-docs/{doc_id}/review` | admin | Mark a stale document as reviewed |

### Analytics and channels

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/analytics/top-topics` | agent/admin | Top categories/topics for a time window |
| GET | `/api/analytics/resolution-rate` | agent/admin | Resolution-rate breakdown by category |
| GET | `/api/analytics/cost-summary` | agent/admin | Total and per-category LLM cost summaries |
| GET | `/api/analytics/trends` | agent/admin | Time-series analytics for quality/cost metrics |
| POST | `/api/channels/email/inbound` | webhook secret | Inbound email webhook receiver |

### Auth, health, and metrics

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | `-` | Password login; returns JWT pair |
| POST | `/api/auth/refresh` | `-` | Exchange a refresh token for a new token pair |
| GET | `/api/auth/sso/providers` | `-` | List enabled SSO providers |
| GET | `/api/auth/sso/{provider}/login` | `-` | Start Google or Azure AD OIDC login |
| GET | `/api/auth/sso/{provider}/callback` | `-` | Finish OIDC login and set JWT cookies |
| GET | `/api/health` | `-` | Readiness alias |
| GET | `/api/health/live` | `-` | Liveness probe |
| GET | `/api/health/ready` | `-` | Dependency-aware readiness probe |
| GET | `/api/metrics` | admin | JSON metrics snapshot for the admin dashboard |
| GET | `/metrics` | `-` | Prometheus exposition endpoint |

**Rate limits:** `/api/ask` is limited to 60 req/min, `/api/upload` to
10 req/min, and `/api/auth/login` to 5 req/min per client IP.

**Correlation ID:** Clients may send `X-Request-Id` matching
`^[A-Za-z0-9_\\-:.]{1,128}$`. The server echoes it back, stores it in
SQLite traces, and also propagates it into logs and spans. If it is not
supplied, the API generates a UUID4-derived identifier.

### Example requests

```bash
curl -s http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

```bash
curl -s http://localhost:8000/api/ask \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do returns work?","session_id":"11111111-1111-1111-1111-111111111111"}'
```

```bash
curl -s "http://localhost:8000/api/analytics/top-topics?days=7" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Monitoring

The project exposes three observability surfaces.

### 1. `GET /api/metrics` - JSON snapshot from SQLite

```json
{
  "latency": {"p50_sec": 2.1, "p95_sec": 8.4, "p99_sec": 14.2, "window": "24h"},
  "escalation": {"total_traces": 120, "escalated": 18, "rate_pct": 15.0, "window": "24h"},
  "quality": {"scored_traces": 840, "avg_quality": 78.3, "low_quality_share_pct": 12.5, "window": "7d"},
  "errors": {"total_started": 120, "likely_failed": 2, "likely_failure_rate_pct": 1.7, "window": "24h"},
  "feedback": {"total": 95, "thumbs_down": 11, "thumbs_down_rate_pct": 11.6, "window": "7d"}
}
```

`/static/metrics.html` renders this snapshot with auto-refresh and status
coloring for operators and admins.

### 2. `GET /metrics` - Prometheus

`monitoring/prometheus.py` currently initializes **30** Prometheus collectors
(`Counter`, `Gauge`, `Histogram`, or `Summary`):

- **HTTP and latency:** `rag_requests_total{route}`,
  `rag_request_duration_seconds`, `rag_http_requests_total{method,endpoint,status}`,
  `rag_http_request_duration_seconds{method,endpoint}`
- **Quality and feedback:** `rag_quality_score`, `rag_factuality_score`,
  `rag_escalation_total`, `rag_feedback_total{rating}`,
  `rag_model_routing_total{complexity}`, `rag_eval_drift{metric_name}`
- **Resilience and protection:** `rag_circuit_breaker_state{name}`,
  `rag_circuit_breaker_transitions_total{name,to_state}`,
  `rag_ollama_retry_events_total{event}`,
  `rag_request_timeouts_total{endpoint}`, `rag_inflight_pipelines`,
  `rag_pipeline_rejections_total{reason}`,
  `rag_rate_limit_rejections_total{endpoint}`,
  `rag_body_size_rejections_total{reason}`
- **Platform health and data:** `rag_component_up{component}`,
  `rag_db_pool_size`, `rag_db_pool_checked_out`, `rag_db_pool_overflow`,
  `rag_active_sessions`, `rag_vector_store_documents`,
  `rag_stale_important_docs_count`, `llm_cache_hits_total{tenant}`,
  `llm_cache_misses_total{tenant}`, `rag_traces_purged_total{table}`,
  `rag_audit_purged_total`, `rag_auth_failures_total{reason}`

### 3. Alert rules and scheduled checks

- `monitoring/alert_rules.yml` defines Prometheus alert groups for
  resilience, health, quality, latency, nightly eval drift, and stale docs.
- `scripts/check_alerts.py` is a lightweight SQLite-based checker that can run
  every five minutes and push alerts through `ALERT_WEBHOOK_URL`.
- `scripts/nightly_eval.py` records evaluation drift, and
  `scripts/weekly_report.py` produces tenant-specific weekly reports.

```bash
python scripts/check_alerts.py --dry-run
python scripts/nightly_eval.py
python scripts/weekly_report.py --tenant TEST --dry-run
```

## Multi-tenancy

Tenant isolation is built into the application:

- JWT access tokens carry a `tenant` claim.
- Traces, audit-log queries, analytics, KB drafts, freshness data, and
  admin read/purge endpoints are filtered by `tenant_id`.
- ChromaDB uses per-tenant collections named `rag_docs_{tenant_id}`.
- Response cache keys are tenant-scoped.
- OIDC and email flows can resolve tenants from `TENANT_EMAIL_DOMAINS`.

For an existing legacy collection named `rag_docs`, use the one-time migration:

```bash
python scripts/migrate_default_collection.py
```

## Web UI

- `/` - main chat UI with inline citations, upload progress, onboarding,
  responsive layouts, and SSE streaming
- `/static/login.html` - login page with password, Google, and Microsoft SSO
- `/static/help.html` - end-user help page
- `/static/metrics.html` - system metrics dashboard with auto-refresh
- `/static/admin.html` - admin UI for breaker control, traces, audit logs,
  KB gaps, categories, KB drafts, and stale docs
- `/agent` and `/static/agent.html` - agent copilot dashboard
- `/static/analytics.html` - product analytics dashboard
- `/static/widget.html` - embeddable support widget

## Tests

Run the full test suite:

```bash
pytest tests/ -v
```

Run only the integration suite added in arc `122`:

```bash
pytest tests/integration/ -v
pytest -m integration -q
pytest -m "not integration" -q
```

`tests/integration/` covers full ingestion, multi-turn conversation, SSE
streaming, concurrent sessions, escalation, and async upload flows. Browser
accessibility/mobile smoke tests may skip automatically when optional
Playwright dependencies are not installed.

## CI

GitHub Actions runs `lint`, `test-unit`, `test-integration`, and `pre-commit`
on every push and pull request.
Install local tooling with `pip install -r requirements-dev.txt`.
Run `pre-commit run --all-files`, `pytest tests/ -q --ignore=tests/integration -p no:cacheprovider`, and `pytest tests/integration -q`.
Workflow history and logs are available on the repository `Actions -> CI` page.

## Docker

```bash
cp .env.example .env
# Set at least OLLAMA_BASE_URL, DATABASE_URL, DB_ENCRYPTION_KEY, and auth/SSO values as needed.
docker compose up
```

For Kubernetes, use `/api/health/live` as the liveness probe and
`/api/health/ready` as the readiness probe. During shutdown, readiness flips
to `503` for `SHUTDOWN_READY_DELAY_SEC` seconds before cleanup begins.

For local distributed tracing:

```bash
OTEL_ENABLED=true docker compose up -d jaeger
```

Jaeger UI is available at **http://localhost:16686**. Set
`DB_ENCRYPTION_KEY` before running `alembic upgrade head`; keep that key out of
git and back it up separately from database backups.

## Deployment and Migrations

Deployment artifacts added in arc `102-122` include:

- `deploy/helm/templates/cronjob.yaml` for nightly eval and KB-gap jobs
- `deploy/helm/templates/cronjob-report.yaml` for weekly reports
- `deploy/helm/templates/deployment-email-poller.yaml` for IMAP polling mode
- `.github/workflows/weekly-report.yml` for scheduled managed deployments

Alembic migrations introduced after the original README baseline:

- `004_escalated_tickets` - creates the `escalated_tickets` table for the
  agent copilot and escalation workflow.
- `005_eval_results` - stores nightly eval metrics and drift flags.
- `006_knowledge_gaps` - stores clustered unanswered-question topics.
- `007_user_sso_fields` - adds OIDC provider and subject fields to users.
- `008_enable_pgcrypto` - enables `pgcrypto` and converts sensitive columns to
  encrypted storage.
- `009_kb_drafts` - stores reviewable KB drafts generated from resolved tickets.
- `010_document_stats` - tracks citation counts, freshness, and stale-doc
  review state.
- `011_trace_costs` - stores token usage and cost data for analytics.

## Project structure

```text
api/                    FastAPI app, REST endpoints, middleware, correlation IDs
agent/                  Canonical graph, prompts, state, and tool modules
auth/                   JWT helpers, RBAC dependencies, OIDC integration
cache/                  Redis cache with in-memory fallback
channels/               Telegram and email channel integrations
config/                 settings.py, categories.yml, logging
db/                     SQLAlchemy models, engine, audit helpers, pgcrypto helpers
deploy/                 docker-compose and Helm chart artifacts
evaluation/             RAG evaluation, drift detection, benchmarks
ingestion/              Loaders, pipeline, categorizer, contextual headers
monitoring/             Prometheus collectors and alert rules
reports/                Weekly-report renderer
scripts/                Ops jobs: eval, reindex, KB builder/gap detection, email poller
static/                 chat, admin, agent, analytics, login, metrics, widget UIs
tests/                  Unit and integration test suites
tests/integration/      End-to-end coverage for critical user flows
tracing/                SQLite tracing and OpenTelemetry setup
vectordb/               ChromaDB manager, BM25 fusion, reranking
alembic/                Migrations `001` through `011`
graph.py                Root compatibility shim; new graph code lives in `agent/graph.py`
prompts.py              Root compatibility shim; new prompts live in `agent/prompts.py`
state.py                Root compatibility shim; new state lives in `agent/state.py`
codex-tasks/            Task backlog and archived implementation specs
docs/research/          Research archive
```

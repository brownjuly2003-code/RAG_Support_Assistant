# RAG Support Assistant

[![CI](https://github.com/<user>/RAG_Support_Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/<user>/RAG_Support_Assistant/actions/workflows/ci.yml)

Answers support questions against a knowledge base and decides whether a
request can be resolved automatically or should be escalated to a human.

This README is the source of truth for runtime configuration, public HTTP
endpoints, and Prometheus metric inventory.

**Stack:** FastAPI · LangGraph · ChromaDB · GraceKelly/Ollama provider routing · SQLite for
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
        +-> GraceKelly orchestrator / Ollama fallback
        +-> Postgres (sessions, audit, copilot, analytics)
        +-> Redis cache
        +-> SQLite traces + OTel spans
```

- **Retrieval:** ChromaDB (vector) + BM25 hybrid search, Reciprocal Rank
  Fusion, cross-encoder reranking, contextual headers, and optional document
  category metadata.
- **Generation:** GraceKelly is the default local orchestrator, with explicit
  `local-first` Ollama/Qwen2.5 7B routing for offline-only setups. Responses can include
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

### Module layout (high level)

- `api/app.py` — FastAPI application construction, middleware, lifespan,
  master router include, and compatibility re-exports used by older tests.
  The 2a-2m endpoint split plus auth/session extraction are complete.
- `api/routers/` — extracted sub-routers: `system.py`, `root_pages.py`,
  `agent.py`, `admin_review.py`, `admin_ops.py`, `admin_kb.py`,
  `admin_experiments.py`, `admin_evaluations.py`, `analytics.py`,
  `auth_sso.py`, `conversation.py`, `feedback.py`, `misc.py`,
  `session_auth.py`, and `upload.py`. New endpoint groups are added here,
  not in `api/app.py`.
- `api/_shared.py` — lazy `app_module()` accessor for routers that need
  compatibility access to `api.app` globals patched by tests. Prefer
  `from api._shared import app_module as _app_module` inside routers instead
  of adding a new local wrapper or importing `api.app` at module load time.
- `agent/` — LangGraph pipeline + state + prompts.
- `auth/` — JWT, X-API-Key, OIDC, RBAC. `mypy --strict` clean.
- `db/` — SQLAlchemy models, async engine, audit log, pgcrypto field.
- `llm/providers/` — Ollama / Mistral / GraceKelly providers + cost guard.
- `vectordb/` — tenant-aware vector store factory (`vectordb.manager`) plus base implementation (`vectordb._base_manager`).
- `evaluation/` — RAGAS metrics, online evaluators, regression framework.
- `monitoring/` — Prometheus metrics (~50). `tracing/` — Langfuse + OTel + SQLite trace store.
- `scripts/` — operational CLIs (regression eval, KB builders, chunking eval, nightly tasks).

> For a complete audit and an implementation log of recent hardening work,
> see `audit_opus_2026-04-26.md` (especially section 12) and
> `DEPRECATIONS.md`. Quick handover for new sessions:
> `docs/SESSION-NOTES-2026-04-26-audit.md`.

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
- **Online evaluators:** seven lightweight per-trace checks score citation
  coverage, answer-length anomalies, retrieval hit rate, tool efficiency,
  refusals, PII suspicion, and language mismatch without judge LLM calls.
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
- **Review queue:** `scripts/build_review_queue.py` collects weak, escalated,
  slow, or thumbs-down traces into a human review backlog with admin actions.
- **Freshness monitoring:** Citation counts plus document age highlight
  stale-but-important documents for review.
- **Auto-categorization:** Uploads are classified into categories from
  `config/categories.yml`, and those categories are stored in document metadata.
- **Analytics dashboard:** `/static/analytics.html` visualizes top topics,
  resolution rates, quality trends, and LLM cost summaries.
- **Weekly reports:** Markdown digests can be pushed through Slack or email on
  a weekly schedule.
- **Improvement backlog:** A weekly generator combines confirmed bad reviews,
  KB gaps, slow endpoints, stale docs, evaluator drift, and thumbs-down trends
  into a prioritized improvement backlog.
- **Email channel:** Incoming support mail can be processed through IMAP
  polling or an inbound webhook, then routed through the same RAG flow.
- **Canonical module layout:** Core agent modules live under `agent/*`; the
  old root-level `graph.py`, `prompts.py`, and `state.py` shims were removed.
- **Centralized tuning:** Retrieval thresholds and operational constants are
  concentrated in `config/settings.py` instead of scattered literals.
- **Integration test suite:** `tests/integration/` covers ingestion,
  conversation, streaming, concurrency, escalation, and async upload paths.

## Quick Start

> Полная пошаговая справка со сценариями GraceKelly primary, explicit local-only Ollama, Mistral и mixed routing — в [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

**Prerequisites:** Python 3.11+, локальный `D:\GraceKelly` на `http://127.0.0.1:8011` для default `gracekelly-primary` profile.

```bash
# 1. Dependencies — pinned hashes for reproducibility (Python 3.11+, Linux x86_64)
pip install --require-hashes -r requirements.lock
# Or for development (adds pytest/ruff/pre-commit):
# pip install --require-hashes -r requirements-dev.lock

# 2. Start the default GraceKelly orchestrator
cd D:\GraceKelly
uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

# 3. Run RAG Support Assistant
cd D:\RAG_Support_Assistant
python main.py
```

Explicit Ollama-only mode is still available:

```bash
ollama serve
ollama pull qwen2.5:7b
LLM_PROVIDER_PROFILE=local-first python main.py
```

Альтернативные routing profiles (см. `LLM_PROVIDER_PROFILE` ниже): `local-first`, `external-mistral`, `gracekelly-mixed`. Подробнее — в `config/providers.yml` и в `docs/QUICKSTART.md` секции 5-6.

Open:
- **http://localhost:8000/static/login.html** - password + SSO login page
- **http://localhost:8000/static/chat.html** - chat UI
- **http://localhost:8000/static/admin.html** - admin UI for traces, audit,
  review queue, providers, KB gaps, KB drafts, stale docs, and breaker controls
- **http://localhost:8000/agent** - agent copilot dashboard
- **http://localhost:8000/static/analytics.html** - analytics dashboard
- **http://localhost:8000/static/metrics.html** - system metrics dashboard

> 2026-04-27: legacy unauthenticated `/` index page и `/ask`, `/escalations`,
> `/traces`, `/escalations-ui`, `/traces-ui*` endpoints из `main.py`
> удалены (Codex audit P0). Production entrypoint: `uvicorn api.app:app`.
> `python main.py` делегирует в `api.app:app`.

## Dependency lock

`requirements.lock` and `requirements-dev.lock` are generated with [`uv`](https://github.com/astral-sh/uv) from the corresponding `requirements*.txt` files. They pin every transitive dependency with sha256 hashes for reproducible installs (Python 3.11+, Linux x86_64 — same target as the `python:3.11-slim` Docker image).

Update flow when bumping a dependency:

```bash
# 1. Edit requirements.txt or requirements-dev.txt with the new constraint.
# 2. Regenerate the lock(s):
uv pip compile requirements.txt -o requirements.lock \
  --generate-hashes --python-version 3.11 --python-platform linux
uv pip compile requirements-dev.txt -o requirements-dev.lock \
  --generate-hashes --python-version 3.11 --python-platform linux
# 3. Verify install in a clean venv:
python -m venv .venv-lock && .venv-lock/bin/pip install --require-hashes -r requirements.lock
# 4. Commit requirements.txt + requirements*.lock together.
```

CI installs from the lock files and Dockerfile uses `--require-hashes`, so any drift between the constraint file and the lock will fail the build.

## Environment Variables

Copy `.env.example` to `.env`, then adjust only what your deployment needs.

### LLM and models

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL for explicit `local-first` Ollama mode or GraceKelly fallback |
| `OLLAMA_MODEL_NAME` | `qwen2.5:7b` | Primary Ollama model when `LLM_PROVIDER_PROFILE=local-first` |
| `OLLAMA_FAST_MODEL_NAME` | `llama3.2:3b` | Faster Ollama model for explicit local helper/tool flows |
| `MODEL_ROUTING_ENABLED` | `false` | Enable simple/complex/global model routing |
| `OLLAMA_REQUEST_TIMEOUT_SEC` | `60` | Timeout for a single Ollama HTTP request |
| `REQUIRE_OLLAMA` | `false` | Fail fast at startup if explicit Ollama mode/fallback validation requires Ollama |
| `LANGFUSE_PUBLIC_KEY` | `-` | Optional Langfuse public key |
| `LANGFUSE_SECRET_KEY` | `-` | Optional Langfuse secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host for LLM observability |

### Provider profiles and live external APIs

| Variable | Default | Description |
|---|---|---|
| `PROVIDER_REGISTRY_PATH` | `config/providers.yml` | YAML registry with providers, pricing, capabilities, and routing profiles |
| `LLM_PROVIDER_PROFILE` | `gracekelly-primary` | Active routing profile; defaults to the local GraceKelly orchestrator |
| `LLM_BENCHMARK_ALLOW_PAID_APIS` | `false` | Backward-compatible flag that allows live external-provider calls in provider benchmarks |
| `DAILY_COST_LIMIT_USD` | `5.0` | Fail fast when tracked direct-provider spend for the current UTC day reaches this limit |
| `MISTRAL_API_KEY` | `changeme` | Direct Mistral API key; placeholder values are treated as missing |
| `GRACEKELLY_BASE_URL` | `http://127.0.0.1:8011` | Base URL for the local GraceKelly orchestrator |
| `GRACEKELLY_API_KEY` | `-` | Optional GraceKelly bearer token for non-public endpoints |
| `GRACEKELLY_API_KEY_ENV` | `GRACEKELLY_API_KEY` | Env var name used by the runtime to look up the optional GraceKelly API key |
| `GRACEKELLY_HEALTH_CHECK_TIMEOUT_SEC` | `2.0` | Readiness-probe timeout before GraceKelly is considered unavailable |
| `GRACEKELLY_REQUEST_TIMEOUT_SEC` | `30.0` | Timeout for a single GraceKelly `/api/v1/smart` call |
| `FAILOVER_CHAIN_ENABLED` | `true` | Enable GraceKelly -> Ollama automatic failover for profiles that declare a local fallback |
| `FAILOVER_FALLBACK_CACHE_SECONDS` | `300` | Cache a successful local fallback decision for this many seconds |

### RAG pipeline

| Variable | Default | Description |
|---|---|---|
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model used for documents and queries |
| `RAG_RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Multilingual cross-encoder reranker (pairs with BGE-M3) |
| `RAG_HYBRID_SEARCH` | `true` | Combine BM25 with vector retrieval |
| `RAG_RETRIEVAL_STRATEGY` | `hybrid` | Retrieval strategy: `vector`, `hybrid`, or `graph`; graph falls back to hybrid until a graph retriever is configured |
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
| `RAG_STRUCTURAL_CHUNKING` | `true` | Split markdown by headers (sections), cap to `CHUNK_SIZE` |
| `RAG_PARENT_EXPANSION` | `true` | Post-rerank: supplement final chunks with neighbouring sections of their source |
| `RAG_PARENT_EXPANSION_WINDOW` | `2` | Sections taken from each side of a selected chunk |
| `RAG_PARENT_EXPANSION_MAX_CHARS` | `3600` | Cap on expanded chunk text (core + neighbours) |
| `RAG_GRAPH_RETRIEVAL` | `off` | Graph-lane activation gate: `off`/`on`/`auto`; condition evaluated & logged at ingestion (lane itself = Phase 2, not built) |
| `RAG_GRAPH_MIN_CHUNKS` | `20000` | `auto`: minimal chunk count to consider the graph lane |
| `RAG_GRAPH_MIN_CROSSDOC_SHARE` | `0.15` | `auto`: minimal cross-doc entity share (connectivity gate) |
| `RAG_GRAPH_CROSSDOC_SHARE` | unset | Measured probe value (`scripts/graph_probe.py`; 2026-06-06 corpus: **0.296**, gate passed); unset = probe not run, `auto` stays off |
| `RAG_SELF_RAG_MAX_ITER` | `2` | Maximum Self-RAG iterations |
| `RAG_SELF_RAG_MIN_QUALITY` | `70` | Minimum quality score to avoid retry/escalation |
| `STREAMING_QUALITY_EVAL` | `true` | Streaming `/api/ask/stream` runs one cheap Self-RAG self-eval so streamed answers are quality-routed on par with non-streaming; set `false` to roll back to the legacy synthetic-score streaming path |
| `FACT_VERIFICATION_ENABLED` | `true` | Run fact verification after generation |
| `FACT_VERIFICATION_MIN_SCORE` | `70` | Minimum factuality score threshold |
| `FACT_VERIFY_CONTEXT_MAX_DOCS` | `5` | Max retrieved docs used as evidence when verifying answer facts |
| `FACT_VERIFY_CONTEXT_CHARS_PER_DOC` | `3600` | Chars per doc used as fact-verification evidence; aligned with `RAG_PARENT_EXPANSION_MAX_CHARS` so verification sees full parent-expanded chunks |
| `SLOW_TRACE_THRESHOLD_MS` | `10000` | Trace-duration threshold for review queue collection |
| `THRESHOLD_ANALYSIS_MIN_LABELS` | `20` | Minimum labeled traces required before suggesting a new threshold |
| `REVIEW_QUEUE_ENABLED` | `true` | Enable review queue builder and admin endpoints |
| `ONLINE_EVALUATORS_ENABLED` | `true` | Enable lightweight per-trace online evaluators, persistence, and admin views |
| `ONLINE_EVALUATORS_TIMEOUT_SEC` | `1.0` | Per-trace online-evaluator wall-clock budget; runs that exceed it are dropped and counted in `rag_online_evaluators_dropped_total{reason}` |
| `REGRESSION_GATE_MAX_REGRESSIONS` | `2` | Maximum allowed curated regressions before the gate fails |
| `REGRESSION_GATE_MIN_PASS_RATE` | `0.85` | Minimum candidate pass rate required by the regression gate |
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
| `STREAMING_TIMEOUT_SEC` | `120` | Wall-clock budget for the SSE token loop in `/api/ask/stream` (separate from `REQUEST_TIMEOUT_SEC`) |
| `DB_PERSIST_TIMEOUT_SEC` | `2.0` | Timeout for persisting one conversation message to Postgres before the write is dropped and counted in `rag_message_persist_failures_total{operation}` |
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
| `ALLOW_ANONYMOUS_ADMIN` | `-` | Opt-in escape hatch when `API_KEY` is empty: set to `1`/`true` to permit anonymous admin (otherwise endpoints return HTTP 503). Local-dev only. Added 2026-04-26 audit. |
| `HOST` | `127.0.0.1` (bare run) | Used only when launching via `python main.py`. Default Docker Compose is local-dev only and binds host ports to `127.0.0.1`. |
| `PORT` | `8000` | Same — bare run only. |
| `AUTO_MIGRATE` | `true` | Run `alembic upgrade head` in startup lifespan. In production, errors abort startup unless `AUTO_MIGRATE_FAIL_OPEN=true` is explicitly set. |
| `AUTO_MIGRATE_FAIL_OPEN` | `false` | Production escape hatch for temporarily logging migration failures instead of aborting startup. |

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
| `LLM_INPUT_PRICE_PER_1M_TOKENS` | `0.0` | Fallback input-token price when a model is not listed in the provider registry |
| `LLM_OUTPUT_PRICE_PER_1M_TOKENS` | `0.0` | Fallback output-token price when a model is not listed in the provider registry |
| `LLM_MODEL_PRICES` | `-` | Optional JSON override for legacy analytics or unregistered models |
| `LLM_COST_PER_1M_TOKENS` | legacy fallback | Backward-compatible legacy pricing format kept for old local setups |
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
| `BACKLOG_WEIGHT_REVIEW_BAD` | `3.0` | Impact weight for confirmed-bad review backlog items |
| `BACKLOG_WEIGHT_THUMBS_DOWN` | `2.0` | Impact weight for thumbs-down backlog items |
| `BACKLOG_WEIGHT_SLOW` | `1.5` | Impact weight for slow-endpoint backlog items |
| `BACKLOG_WEIGHT_FRESHNESS` | `1.0` | Impact weight for stale-document backlog items |
| `BACKLOG_WEIGHT_EVALUATOR_DRIFT` | `2.5` | Impact weight for evaluator drift backlog items |
| `BACKLOG_MAX_ITEMS` | `30` | Maximum number of improvement backlog items kept after ranking |
| `BACKLOG_FRESHNESS_MAX_DAYS` | `90` | Freshness cutoff for stale-doc backlog items |
| `BACKLOG_EMAIL_ENABLED` | `false` | Email the generated backlog to `TENANT_ADMIN_EMAIL` after each run |
| `TENANT_ADMIN_EMAIL` | `""` | Optional recipient for backlog email delivery |
| `EMAIL_CHANNEL_MODE` | `disabled` | Email channel mode: `disabled`, `imap`, or `webhook` |
| `IMAP_HOST` | `""` | IMAP server hostname |
| `IMAP_PORT` | `993` | IMAP server port |
| `IMAP_USER` | `""` | IMAP username |
| `IMAP_PASS` | `-` | IMAP password (`IMAP_PASSWORD` is also accepted) |
| `IMAP_FOLDER` | `INBOX` | IMAP folder polled by `scripts/email_poller.py` |
| `IMAP_POLL_INTERVAL_SEC` | `60` | Delay between IMAP polling cycles |
| `SMTP_HOST` | `""` | SMTP hostname for email replies |
| `SMTP_PORT` | `587` | SMTP port for email replies |
| `SMTP_USER` | `""` | SMTP username |
| `SMTP_PASS` | `-` | SMTP password (`SMTP_PASSWORD` is also accepted) |
| `SMTP_FROM_ADDRESS` | `support@example.com` | Default sender address for outbound replies |
| `EMAIL_WEBHOOK_SIGNING_SECRET` | `-` | Shared secret used to verify inbound email webhooks (`EMAIL_WEBHOOK_SECRET` remains a legacy fallback) |

### Email channel

- IMAP mode runs through `scripts/email_poller.py` and polls `IMAP_FOLDER` every `IMAP_POLL_INTERVAL_SEC` seconds.
- `python scripts/email_poller.py --once` is the easiest dev-mode smoke check for one poll cycle.
- Webhook mode supports **SendGrid Inbound Parse** style payloads with `from`, `to`, `subject`, `text`, optional `html`, and optional raw `headers`.
- The webhook accepts `POST /webhook/email`; `/api/channels/email/inbound` remains as a compatibility alias.
- Signatures use `HMAC-SHA256(body, EMAIL_WEBHOOK_SIGNING_SECRET)` in the `X-Signature` header.
- Tenant routing uses the sender email domain from `TENANT_EMAIL_DOMAINS`, for example `TENANT_EMAIL_DOMAINS=acme.com:acme,*:default`.
- Low-quality email answers are persisted into `escalated_tickets` with `status="pending_response"` for the existing operator flow.

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
| GET | `/api/admin/evaluations/trends?evaluator=<name>&days=30` | admin | Return daily mean-score trends for one online evaluator |
| GET | `/api/admin/evaluations/worst?evaluator=<name>&limit=20` | admin | Return the worst recent traces for one online evaluator |
| GET | `/api/admin/categories` | admin | Return the active category taxonomy |
| GET | `/api/admin/kb-drafts` | admin | List Knowledge Builder drafts |
| PATCH | `/api/admin/kb-drafts/{draft_id}` | admin | Edit a pending KB draft |
| POST | `/api/admin/kb-drafts/{draft_id}/reject` | admin | Reject a pending KB draft |
| POST | `/api/admin/kb-drafts/{draft_id}/publish` | admin | Publish a KB draft into the vector store |
| GET | `/api/admin/improvement-backlog/current` | admin | Return the latest improvement backlog as JSON |
| GET | `/api/admin/improvement-backlog/archive?year=2026` | admin | List archived improvement backlog weeks |
| GET | `/api/admin/stale-docs` | admin | List stale but highly cited documents |
| POST | `/api/admin/stale-docs/{doc_id}/review` | admin | Mark a stale document as reviewed |
| GET | `/api/admin/curated-dataset/stats` | admin | Aggregate curated dataset counts by verdict, tenant, and channel |
| POST | `/api/admin/curated-dataset/rebuild` | admin | Trigger an async rebuild of `evaluation/curated_cases.jsonl` |
| GET | `/api/admin/providers` | admin | Return provider registry metadata, active profile, recent usage, and 24h cost |

### Analytics and channels

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/analytics/top-topics` | agent/admin | Top categories/topics for a time window |
| GET | `/api/analytics/resolution-rate` | agent/admin | Resolution-rate breakdown by category |
| GET | `/api/analytics/cost-summary` | agent/admin | Total and per-category LLM cost summaries |
| GET | `/api/analytics/trends` | agent/admin | Time-series analytics for quality/cost metrics |
| POST | `/webhook/email` | webhook secret | Preferred inbound email webhook receiver |
| POST | `/api/channels/email/inbound` | webhook secret | Backward-compatible inbound email webhook alias |

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

## Experiments

Prompt, model, and retrieval changes can be tracked as YAML experiments in
`evaluation/experiments/`.

Create a new draft from the current runtime snapshot:

```bash
python scripts/experiment_new.py --name "concise-answers" --from current --description "Shorter support replies"
```

Stage an experiment without changing committed defaults:

```bash
python scripts/experiment_apply.py 2026-04-21-concise-answers --mode stage
EXPERIMENT_ID=2026-04-21-concise-answers python -c "from config.settings import get_settings; print(get_settings().retrieval_top_k)"
```

Recommended workflow:

1. Create a draft with `experiment_new.py`.
2. Stage it with `experiment_apply.py --mode stage`.
3. Run nightly or regression evaluation against the staged `EXPERIMENT_ID`.
4. Deploy with `experiment_apply.py --mode deploy` once metrics look acceptable.

In stage mode, `EXPERIMENT_ID` plus `config/experiment_override.yaml` applies to
the runtime pipeline on the next request without any git edits or deploy-mode
rewrite of `agent/prompts.py`.

Admin endpoints:

- `GET /api/admin/experiments`
- `GET /api/admin/experiments/{id}`
- `POST /api/admin/experiments/{id}/archive`
- `POST /api/admin/experiments/{id}/regression-run?baseline=current`
- `GET /api/admin/regression-runs`
- `GET /api/admin/regression-runs/{run_id}`

## Providers

Provider routing is configured through `config/providers.yml`, which defines:

- enabled providers (`ollama`, `gracekelly`, `mistral`)
- model aliases such as `ollama-small`, `gk-fast`, and `mistral-small-latest`
- per-model input/output pricing, rate limits, and capability flags
- routing profiles `local-first`, `gracekelly-primary`, `gracekelly-mixed`, and `external-mistral`

Runtime behavior:

- `gracekelly-primary` is the default profile and routes both tiers through the local GraceKelly orchestrator.
- `local-first` is the explicit Ollama-only profile and keeps both fast/strong lanes on Ollama.
- `gracekelly-primary` falls back only to the declared Ollama fallback when GraceKelly is unavailable and failover is enabled.
- `gracekelly-mixed` keeps browser-backed strong answer generation on GraceKelly while routing fast helper/evaluator calls through direct Mistral; use it only for explicit live benchmark runs.
- `external-mistral` uses the direct Mistral API and is the intended non-local deployment option when GraceKelly is not present.
- Startup validation loads the registry, verifies `LLM_PROVIDER_PROFILE`, and treats placeholder credentials such as `changeme` as missing.
- Each traced LLM step now records `provider_name`, `model_name`, token usage, and cost; Prometheus exports `llm_cost_usd_total{provider,model,tenant}`.
- Automatic failover events are exported as `llm_provider_fallback_total{from_provider,to_provider,reason}`.
- `mistral-small` is GraceKelly's local fast-lane model name; use `mistral-small-latest` when you want the direct Mistral alias.
- The admin UI exposes a **Providers** tab backed by `GET /api/admin/providers`, including active profile, configured providers, 1-minute usage, 24-hour cost, and the last successful call timestamp.

### GraceKelly provider

- `gracekelly-primary` is intended for local setups where `D:\GraceKelly\` runs on `http://127.0.0.1:8011`.
- The provider uses `GET /healthz/ready` before the first request and calls `POST /api/v1/smart` with `reliability_level=quick`.
- If GraceKelly is down or times out, the runtime switches only to the declared local fallback (`ollama`) and caches that decision for `FAILOVER_FALLBACK_CACHE_SECONDS`. Ollama is not otherwise required by the default health path.
- GraceKelly calls are treated as proxy/orchestrator traffic, so `cost_usd` remains `0.0` in local traces.

### Mistral provider

- `external-mistral` is the direct Mistral fallback for deployments where GraceKelly is unavailable.
- The provider uses `POST https://api.mistral.ai/v1/chat/completions` with OpenAI-compatible chat payloads and reads token usage from `usage.prompt_tokens` / `usage.completion_tokens`.
- Placeholder `MISTRAL_API_KEY=changeme` is treated as missing both in startup validation and in the provider constructor.
- `DAILY_COST_LIMIT_USD` applies to the direct Mistral profile and blocks new runtime creation after the current UTC-day spend is exhausted.

## Regression eval

Curated regression runs compare a baseline against `current` or an experiment
without invoking the heavy nightly RAGAS pipeline.

```bash
python scripts/regression_eval.py \
  --baseline current \
  --candidate 2026-04-21-concise-answers \
  --dataset evaluation/curated_cases.jsonl \
  --tenant all \
  --max-cases 100 \
  --seed 42
```

- The script writes `reports/regression/<timestamp>-<baseline>-vs-<candidate>.md`
  and a JSON sidecar next to it.
- Exit code `0` means the candidate satisfied the regression gate, `1` means
  gate failure, and `2` is reserved for infrastructure/runtime errors.
- Each completed run is persisted into `eval_results` with `kind='regression'`,
  `run_id`, baseline/candidate experiment ids, and the report path.
- `temperature=0` is forced for Ollama-backed regression runs to keep
  comparisons reproducible.
- GitHub Actions exposes an informational `regression-eval` job on pull
  requests that touch `agent/prompts.py`, `config/settings.py`, or
  `evaluation/experiments/*.yaml`.

## Provider benchmarking

The same regression runner also supports provider/model benchmarks by passing
registry aliases instead of experiment ids.

```bash
python scripts/regression_eval.py \
  --baseline ollama-small \
  --candidate mistral-small-latest \
  --dataset evaluation/curated_cases.jsonl \
  --tenant all \
  --max-cases 50 \
  --seed 42
```

- Alias resolution comes from `config/providers.yml`, so `ollama-small`,
  `gk-fast`, `gk-strong`, and `mistral-small-latest` can be used directly.
- Use `mistral-small-latest` for direct Mistral benchmarks; bare `mistral-small`
  belongs to the GraceKelly profile.
- Default mode is `mock-provider-benchmark`: answers are derived from the
  curated dataset and pricing/latency/refusal metrics are simulated so CI does
  not call live external providers accidentally.
- Live calls require explicit opt-in via `--allow-paid-apis` or
  `LLM_BENCHMARK_ALLOW_PAID_APIS=true`.
- Reports compare pass rate, latency, total cost, and refusal rate for the
  baseline and candidate provider targets.
- Direct-provider profiles are blocked when `DAILY_COST_LIMIT_USD` is already
  exhausted for the current UTC day.

## Online evaluators

Online evaluators are synchronous, low-cost checks that run on the final trace
state after the main graph finishes. They are enabled by
`ONLINE_EVALUATORS_ENABLED=true` and persist one row per evaluator into
`trace_evaluations`.

- `citation_coverage` measures the share of answer sentences carrying `[N]`
  citations.
- `answer_length_anomaly` flags answers whose word-count z-score falls outside
  the baseline.
- `retrieval_hit_rate` measures the share of retrieved documents whose rerank
  `relevance_score` is above `0.5`.
- `tool_use_efficiency` compares final-answer tokens against tool-call token
  spend.
- `refusal_detected` flags refusal-style phrases from
  `config/evaluator_patterns.yml`.
- `pii_leak_suspicion` flags phone/email/card-like patterns and stores only the
  matched pattern names, never raw values.
- `language_mismatch` compares detected query and answer languages.

Operational surfaces:

- `GET /api/admin/evaluations/trends?evaluator=<name>&days=30`
- `GET /api/admin/evaluations/worst?evaluator=<name>&limit=20`
- `python scripts/eval_daily_snapshot.py --date 2026-04-20`
- `deploy/helm/templates/cronjob-eval-snapshot.yaml` runs the daily snapshot at
  `02:00 UTC`

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

`monitoring/prometheus.py` currently initializes Prometheus collectors
(`Counter`, `Gauge`, `Histogram`, or `Summary`):

- **HTTP and latency:** `rag_requests_total{route}`,
  `rag_request_duration_seconds`, `rag_http_requests_total{method,endpoint,status}`,
  `rag_http_request_duration_seconds{method,endpoint}`
- **Quality and feedback:** `rag_quality_score`, `rag_factuality_score`,
  `rag_escalation_total`, `rag_feedback_total{rating}`,
  `rag_model_routing_total{complexity}`, `rag_eval_drift{metric_name}`,
  `regression_runs_total{result}`, `regression_runs_duration_seconds`,
  `regression_last_pass_rate{baseline,candidate}`,
  `online_evaluator_score{evaluator}`,
  `online_evaluator_runs_total{evaluator,verdict}`,
  `online_evaluator_errors_total{evaluator}`
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
  `llm_cost_usd_total{provider,model,tenant}`,
  `rag_stale_important_docs_count`, `llm_cache_hits_total{tenant}`,
  `llm_cache_misses_total{tenant}`, `rag_traces_purged_total{table}`,
  `rag_audit_purged_total`, `rag_auth_failures_total{reason}`,
  `review_queue_pending_total{reason}`,
  `review_queue_confirmed_total{verdict}`,
  `review_queue_oldest_pending_seconds`

### 3. Alert rules and scheduled checks

- `monitoring/alert_rules.yml` defines Prometheus alert groups for
  resilience, health, quality, latency, nightly eval drift, and stale docs.
- `scripts/check_alerts.py` is a lightweight SQLite-based checker that can run
  every five minutes and push alerts through `ALERT_WEBHOOK_URL`.
- `scripts/nightly_eval.py` records evaluation drift, and
  `scripts/weekly_report.py` produces tenant-specific weekly reports.
- `scripts/build_review_queue.py` is intended for hourly automation and feeds
  the continuous-learning review backlog.
- `scripts/generate_improvement_backlog.py` aggregates the weekly actionable
  backlog and writes `reports/improvement_backlog/<YYYY-Www>.md`.

```bash
python scripts/check_alerts.py --dry-run
python scripts/build_review_queue.py --days 1 --tenant all
python scripts/nightly_eval.py
python scripts/weekly_report.py --tenant TEST --dry-run
python scripts/generate_improvement_backlog.py --tenant all --week 2026-W17 --out reports/improvement_backlog/2026-W17.md
```

## Review queue

The review queue keeps weak or high-risk traces from being lost between
tracing, feedback, and escalation flows.

```bash
python scripts/build_review_queue.py --days 7 --tenant all
```

- The builder inserts `pending` cases for `thumbs_down`, `low_quality`,
  `escalated`, `fact_fail`, and `slow_trace` signals.
- The admin UI exposes a **Review Queue** tab with filters, status counters,
  `Confirm good` / `Confirm bad` / `Dismiss` actions, and links to
  `/admin/traces/{trace_id}`.
- For single-user offline review, export a JSONL batch, annotate `review.*`
  fields in an editor, then import the verdicts back through the CLI.
- For Kubernetes, use `deploy/helm/templates/cronjob-review-queue.yaml` to run
  the builder hourly with `--days 1`.

## Improvement backlog

The improvement backlog turns one week of review, KB, freshness, latency, and
evaluation signals into a ranked list of changes worth making this week.

```bash
python scripts/generate_improvement_backlog.py --tenant all --week 2026-W17 --out reports/improvement_backlog/2026-W17.md
```

- Ranking uses `impact * frequency * recency`, where recency decays
  exponentially from the latest occurrence.
- The generator keeps at most `BACKLOG_MAX_ITEMS` items and renders markdown
  sections for critical, high, and medium priorities.
- `GET /api/admin/improvement-backlog/current` returns the latest backlog JSON
  for the current admin tenant.
- `GET /api/admin/improvement-backlog/archive?year=2026` lists stored markdown
  backlog weeks under `reports/improvement_backlog/`.
- For Kubernetes, use `deploy/helm/templates/cronjob-improvement-backlog.yaml`
  to generate the backlog every Monday at `06:00 UTC`.

## Curated dataset

Confirmed review cases can be promoted into a reusable JSONL dataset for
regression checks and provider benchmarks.

```bash
python scripts/build_curated_dataset.py --tenant all --since 2026-04-01 --out evaluation/curated_cases.jsonl --include-bad
```

- Each line in `evaluation/curated_cases.jsonl` is a standalone case with
  `input.query`, `input.context_hint`, `input.channel`, `expected.*`,
  `human_verdict`, `reviewer_notes`, `source_trace_id`, and `created_at`.
- `confirmed_good` rows always participate; add `--include-bad` to also export
  `confirmed_bad` rows.
- Re-running the builder is idempotent by `case_id`, so the file can be
  refreshed safely during iterative review.
- `GET /api/admin/curated-dataset/stats` returns dataset counts split by
  verdict, tenant, and channel.
- `POST /api/admin/curated-dataset/rebuild` queues an async rebuild and stores
  progress in Redis under a `curated-dataset-job:<job_id>` tracker key.

## Offline review workflow

Use the export/import pair when reviewing pending cases locally instead of
clicking through the admin UI one by one.

```bash
python scripts/review_export.py --status pending --tenant all --limit 5
python scripts/review_import.py .review_local/review_batch_<timestamp>.jsonl --dry-run
python scripts/review_import.py .review_local/review_batch_<timestamp>.jsonl --confirm
```

- `scripts/review_export.py` writes a comment header plus one JSON object per
  review case with `query`, `answer`, `retrieved_docs`, `tool_calls`,
  `citations`, and an empty `review` object for manual annotation.
- By default export files are written to `.review_local/`, and both
  `.review_local/` and `review_batch_*.jsonl` are ignored by git.
- Edit only the nested `review` object per line:
  `verdict = good | bad | dismiss`, optional `notes`, optional `fix_hint`,
  optional `tags`.
- `scripts/review_import.py` skips comments, ignores rows with `review.verdict =
  null`, and refuses to overwrite items that are no longer `pending`.
- Set `REVIEWER_EMAIL` before import. In the current schema it must match an
  existing `users.username` so the import can persist `reviewed_by`.
- For large batches, either pass `--confirm` up front or answer the interactive
  confirmation prompt when more than 10 verdicts would be applied.

## Threshold tuning

Threshold recommendations are generated from recent traces plus
`review_queue` verdicts. The analyzer writes a markdown report and exposes a
JSON view for admin tooling.

```bash
python scripts/analyze_thresholds.py --tenant all --days 30 --out reports/threshold_recommendations.md
```

- `scripts/analyze_thresholds.py` evaluates `QUALITY_THRESHOLD`,
  `FACT_VERIFICATION_MIN_SCORE`, `ESCALATION_THRESHOLD`, and
  `SLOW_TRACE_THRESHOLD_MS` against labeled bad/good traces and suggests the
  best cutoff by F1.
- `GET /api/admin/thresholds/analysis?days=30` returns the latest cached JSON
  analysis for the current tenant.
- `POST /api/admin/thresholds/refresh?days=30` forces a refresh and rewrites
  `reports/threshold_recommendations.md`.
- `deploy/helm/templates/cronjob-threshold-analysis.yaml` runs the analyzer
  weekly.
- If fewer than `THRESHOLD_ANALYSIS_MIN_LABELS` labeled traces are available,
  the report keeps the metric section but marks it as insufficient data.

## Multi-tenancy

Tenant isolation is built into the application:

- JWT access tokens carry a `tenant` claim.
- Traces, audit-log queries, analytics, KB drafts, freshness data, and
  admin read/purge endpoints are filtered by `tenant_id`.
- ChromaDB uses per-tenant collections named `rag_docs_{tenant_id}`.
- Response cache keys are tenant-scoped.
- OIDC and email flows can resolve tenants from `TENANT_EMAIL_DOMAINS`, for example `acme.com:acme,*:default`.

For an existing legacy collection named `rag_docs`, use the one-time migration:

```bash
python scripts/migrate_default_collection.py
```

## Web UI

- `/static/chat.html` - main chat UI with inline citations, upload progress, onboarding,
  responsive layouts, and SSE streaming
- `/static/login.html` - login page with password, Google, and Microsoft SSO
- `/static/help.html` - end-user help page
- `/static/metrics.html` - system metrics dashboard with auto-refresh
- `/static/admin.html` - admin UI for breaker control, traces, audit logs,
  review queue, KB gaps, categories, KB drafts, and stale docs
- `/agent` and `/static/agent.html` - agent copilot dashboard
- `/static/analytics.html` - product analytics dashboard
- `/static/widget.html` - embeddable support widget

## Accessibility

- Latest axe audit: [docs/a11y/axe-audit-2026-04-21.md](docs/a11y/axe-audit-2026-04-21.md)
- Current blocking status: **PASS** for scanned UI pages and rendered Jinja
  templates (`0` critical, `0` serious)
- Axe/Lighthouse verification 2026-05-03: `tests/test_a11y.py` ran with
  `@axe-core/cli` 4.11.3 installed and completed with `38 passed`.
- Lighthouse mobile `/static/chat.html`: performance `99`, accessibility
  `100`, best-practices `96`, SEO `90`.
- Local unit gate runs `tests/test_a11y.py` through `@axe-core/cli` when the
  CLI is installed; axe subprocesses use an explicit timeout budget so the
  full unit suite does not hang under `pytest --timeout=60`.
- Source status: static coverage now includes `/static/widget.html`; source
  updates have landed for explicit `<main>` landmarks, the admin analytics
  `<nav>` landmark, and the rendered `ask_result` heading order.

## Tests

Run the full test suite:

```bash
pytest tests/ -v
```

On Windows, use the repository-local temp directory and disable the broken
auto-loaded Schemathesis plugin. The full workflow is documented in
[`docs/windows-test-workflow.md`](docs/windows-test-workflow.md):

```bash
python -m pytest -p no:schemathesis --basetemp=.tmp/pytest
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
Install local tooling with `pip install --require-hashes -r requirements-dev.lock`.
Run `pre-commit run --all-files`, `pytest tests/ -q --ignore=tests/integration -p no:cacheprovider`, and `pytest tests/integration -q`.
Workflow history and logs are available on the repository `Actions -> CI` page.

## Docker

The default `docker-compose.yml` is a local development stack, not a
production deployment manifest. Published host ports are bound to `127.0.0.1`
and the app container sets `RAG_ENV=development`; use the Helm chart or a
separate production manifest for reachable deployments.

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

### Deployment topology

**Run exactly one worker and one replica.** Session history, pending
confirm-actions (the human-approval step for irreversible actions such as
`create_ticket`), the LLM/retriever/store caches, the regression-job registry
and the circuit breaker all live in process memory and are **not** shared across
workers or replicas. With more than one process:

- a confirm-action started on process A is invisible to process B, so the user
  is re-prompted forever and the action never completes;
- session continuity and in-memory caches diverge per process;
- queued regression jobs can appear stuck.

The SQLite trace DB uses WAL + `busy_timeout` and tolerates concurrent access,
but that does **not** make the application multi-worker safe. Defaults reflect
the invariant: `Dockerfile` runs `--workers 1`, and the Helm chart ships
`replicaCount: 1` with `autoscaling.enabled: false`. A startup warning fires
when `WEB_CONCURRENCY > 1` (best-effort; it does not catch an explicit
`uvicorn --workers N` flag). Scaling out requires first externalising session
state and pending confirm-actions to Redis/Postgres (the `Message`/`Session`
models exist; `pending_action` and server-side history do not yet).

Deployment artifacts added in arc `102-122` include:

- `deploy/helm/templates/cronjob.yaml` for nightly eval and KB-gap jobs
- `deploy/helm/templates/cronjob-eval-snapshot.yaml` for daily online-evaluator snapshots
- `deploy/helm/templates/cronjob-review-queue.yaml` for hourly review-queue builds
- `deploy/helm/templates/cronjob-improvement-backlog.yaml` for weekly improvement backlog generation
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
- `012_review_queue` - creates the `review_queue` table for human quality review.
- `013_regression_eval_runs` - extends `eval_results` for curated regression runs.
- `014_trace_evaluations` - stores per-trace online evaluator outputs.
- `015_experiment_deployments` - stores staged/deployed/rolled-back
  experiment lifecycle records.
- `016_experiment_assignments` - stores tenant rollout assignments and
  rollout percentages.
- `017_curated_case_status` - stores freshness status for curated regression
  cases.

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
integrations/           Bitrix and local support inbox integrations
monitoring/             Prometheus collectors and alert rules
reports/                Weekly-report renderer
scripts/                Ops jobs: eval, review queue, reindex, KB builder/gap detection, chunking eval, email poller
static/                 chat, admin, agent, analytics, login, metrics, widget UIs
tests/                  Unit and integration test suites
tests/integration/      End-to-end coverage for critical user flows
tracing/                SQLite tracing base/wrapper and OpenTelemetry setup
vectordb/               ChromaDB manager, BM25 fusion, reranking
alembic/                Migrations `001` through `017`
demo/                   Demo docs and seed helpers
codex-tasks/            Task backlog and archived implementation specs
docs/research/          Research archive
```

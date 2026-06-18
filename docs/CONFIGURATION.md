# Configuration — RAG Support Assistant

> Moved out of the top-level README to keep it scannable; this is the full runtime-configuration reference.

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
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model used for documents and queries (local backend) |
| `RAG_EMBEDDING_BACKEND` | `local` | `local` = SentenceTransformer on `RAG_DEVICE`; `remote` = OpenAI/Mistral-compatible embeddings API. Remote frees ingest/search from loading the heavy local model (e.g. unblocks Windows under the 1-GiB/process rule). Remote vectors are L2-normalized to match the local path |
| `RAG_EMBEDDING_REMOTE_URL` | `https://api.mistral.ai/v1/embeddings` | Remote embeddings endpoint (OpenAI-compatible `{model, input:[...]}`) |
| `RAG_EMBEDDING_REMOTE_MODEL` | `mistral-embed` | Remote embedding model name |
| `RAG_EMBEDDING_REMOTE_API_KEY_ENV` | `MISTRAL_API_KEY` | Name of the env var holding the remote API key (the key itself is never stored in settings/logs) |
| `RAG_EMBEDDING_REMOTE_BATCH` | `32` | Inputs per remote embeddings request |
| `RAG_EMBEDDING_REMOTE_TIMEOUT_SEC` | `60` | Timeout for a single remote embeddings request |
| `RAG_RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Multilingual cross-encoder reranker (pairs with BGE-M3) |
| `RAG_HYBRID_SEARCH` | `true` | Combine BM25 with vector retrieval |
| `RAG_RETRIEVAL_STRATEGY` | `hybrid` | Retrieval strategy: `vector`, `hybrid`, `graph`, or `factcard`; `graph` and `factcard` fall back to `hybrid` when their store is absent. `factcard` (opt-in) serves whole fact-cards for enumeration queries (fields/documents/conditions) — closes the `customs-clearance-fields` recall gap; build the collection with `scripts/build_factcards.py`. Auto-routing into `factcard` is intentionally NOT default (NO-SHIP pending Phase-5 offline-delta — see `docs/operations/2026-06-14-adaptive-retrieval-closure.md`) |
| `RAG_RETRIEVAL_TOP_K` | `20` | Candidate documents fetched before reranking |
| `RAG_RERANK_TOP_K` | `5` | Final document count after reranking |
| `RRF_K` | `60` | Reciprocal Rank Fusion smoothing constant |
| `RRF_DOC_KEY_CHARS` | `200` | Prefix length used to deduplicate RRF document keys |
| `QUALITY_THRESHOLD` | `80` | Default quality threshold used by routing/evaluation logic |
| `CHUNK_SIZE` | `800` | Default chunk size for ingestion |
| `CHUNK_OVERLAP` | `200` | Default chunk overlap for ingestion |
| `API_DEFAULT_PAGE_SIZE` | `50` | Default page size for list-style admin endpoints |
| `RAG_SEMANTIC_CHUNKING` | `true` | Enable semantic chunking |
| `RAG_CONTEXTUAL_HEADERS` | `true` | Prepend contextual headers during ingestion. Cheap by default (`build_vector_store` derives headers from chunk metadata — no LLM/network). The LLM-generated variant runs **only** when `INGESTION_BATCH_ENABLED=true`, and then per *document*, not per chunk |
| `INGESTION_CONTEXTUAL_CONCURRENCY` | `4` | Bounded concurrency for the LLM contextual-header fallback (providers without a native batch API). `1` = strictly serial. Caps in-flight requests so a full-corpus ingest cannot fan out unbounded provider calls. Progress is logged as `[contextual_headers] i/N` |
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
| `RAG_ASK_BUDGET_SEC` | `0` | Optional wall-clock budget for a single `ConversationSession.ask()` outside the HTTP path (which already has `request_timeout_sec`). `0` = off (blocking). When >0 and exceeded, `ask()` returns a graceful degraded result (`route="timeout"`) instead of hanging on a flapping provider; the background run is not cancellable |
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
| `ONLINE_EVALUATORS_ENABLED` | `true` | Enable lightweight per-trace online evaluators, persistence, and admin views. When persistence fails (e.g. Postgres unreachable in a standalone graph run), the first failure logs at WARNING and identical repeats drop to DEBUG — one signal per process, not one per request; answers are unaffected |
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
| `UVICORN_RELOAD` | `false` | `python main.py` only: enable uvicorn auto-reload. Default off is headless-safe — auto-reload restarts the API on any write under `data/`/`demo/`, which flaps headless ingest/eval runs. Set `true` for the local dev loop. |
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

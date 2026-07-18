# RAG Support Assistant

[![CI](https://github.com/brownjuly2003-code/RAG_Support_Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/brownjuly2003-code/RAG_Support_Assistant/actions/workflows/ci.yml)

Answers support questions against a knowledge base and decides whether a
request can be resolved automatically or should be escalated to a human.

Public HTTP endpoints are documented below; runtime configuration lives in [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and the metric / monitoring inventory in [docs/OPERATIONS.md](docs/OPERATIONS.md).

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

- `api/app.py` + `api/routers/` — FastAPI app construction and the extracted
  sub-routers (system, agent, admin_*, analytics, auth_sso, conversation,
  feedback, upload, …). New endpoint groups land in `api/routers/`, not `app.py`.
- `api/_shared.py`, `api/correlation.py`, `api/rate_limit.py` — lazy `app_module()`
  accessor, request-correlation context, and rate-limit primitives.
- `agent/` — LangGraph pipeline + state + prompts.
- `auth/` — JWT, X-API-Key, OIDC, RBAC.
- `db/` — SQLAlchemy models, async engine, audit log, pgcrypto field.
- `llm/providers/` — Ollama / Mistral / GraceKelly providers + cost guard.
- `vectordb/` — tenant-aware vector store factory + base implementation.
- `evaluation/` — RAGAS metrics, online evaluators, regression framework.
- `monitoring/` — Prometheus metrics (~50); `tracing/` — Langfuse + OTel + SQLite trace store.
- `ingestion/` — loaders, pipeline, categorizer, contextual headers.
- `scripts/` — operational CLIs (regression eval, KB builders, chunking eval, nightly tasks).

All production packages are `mypy --strict` clean (CI-enforced).

> For a complete audit and an implementation log of recent hardening work,
> see `docs/audits/audit_opus_2026-04-26.md` (especially section 12) and
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

**Prerequisites:** Python 3.11+, локальный GraceKelly на `http://127.0.0.1:8011` для default `gracekelly-primary` profile.

```bash
# 1. Dependencies — pinned hashes for reproducibility (Python 3.11+, Linux x86_64)
pip install --require-hashes -r requirements.lock
# Or for development (adds pytest/ruff/pre-commit):
# pip install --require-hashes -r requirements-dev.lock

# 2. Start the default GraceKelly orchestrator
cd ../GraceKelly   # path to your local GraceKelly checkout
uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

# 3. Run RAG Support Assistant
cd RAG_Support_Assistant
python main.py
```

Explicit Ollama-only mode is still available:

```bash
ollama serve
ollama pull qwen2.5:7b
LLM_PROVIDER_PROFILE=local-first python main.py
```

Альтернативные routing profiles (см. `LLM_PROVIDER_PROFILE` в [docs/CONFIGURATION.md](docs/CONFIGURATION.md)): `local-first`, `external-mistral`, `gracekelly-mixed`. Подробнее — в `config/providers.yml` и в `docs/QUICKSTART.md` секции 5-6.

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
| POST | `/api/auth/login` | `-` | Password login; returns JWT pair + sets httpOnly auth cookies |
| POST | `/api/auth/refresh` | `-` | Exchange a refresh token for a new token pair (cookies rotated) |
| POST | `/api/auth/session` | bearer | Re-issue a pasted bearer token as an httpOnly cookie (browser UIs) |
| POST | `/api/auth/logout` | `-` | Clear the httpOnly auth cookies |
| GET | `/api/auth/sso/providers` | `-` | List enabled SSO providers |
| GET | `/api/auth/sso/{provider}/login` | `-` | Start Google or Azure AD OIDC login |
| GET | `/api/auth/sso/{provider}/callback` | `-` | Finish OIDC login and set JWT cookies |
| GET | `/api/health` | `-` | Readiness alias |
| GET | `/api/health/live` | `-` | Liveness probe |
| GET | `/api/health/ready` | `-` | Dependency-aware readiness probe |
| GET | `/api/metrics` | admin | JSON metrics snapshot for the admin dashboard |
| GET | `/metrics` | `-` | Prometheus exposition endpoint |

**Rate limits:** `/api/ask` is limited to 60 req/min, `/api/upload` to
10 req/min, and `/api/auth/login` / `/api/auth/session` to 5 req/min per
client IP.

**Browser auth:** the admin/agent/analytics pages authenticate via httpOnly
`SameSite=Strict` cookies (no tokens in `localStorage`); a cookie bridge maps
the cookie onto the `Authorization` header server-side and refuses
cookie-derived auth for state-changing requests whose `Origin` does not match
the host. Header-based bearer auth for API clients is unchanged.

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


## Configuration

Runtime configuration — every environment variable, LLM/provider profiles, RAG-pipeline knobs, resilience/capacity limits, auth, storage, and channel settings — is documented in **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**.

## Operations & evaluation

Monitoring (Prometheus + JSON metrics), the regression-eval and provider-benchmark harnesses, online evaluators, experiments, the review queue, improvement backlog, curated dataset, offline-review workflow, and threshold tuning are documented in **[docs/OPERATIONS.md](docs/OPERATIONS.md)**.

## Deployment

Docker, deployment topology, database migrations, and the pinned dependency-lock workflow are documented in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

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

## License

MIT. See [LICENSE](LICENSE).

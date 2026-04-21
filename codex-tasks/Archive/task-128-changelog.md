# Task 128 — CHANGELOG.md

## Goal
Создать `docs/CHANGELOG.md` с полной историей развития проекта от arc 68 (production hardening) до arc 122 (code quality polish). Цель — чтобы через 6 месяцев можно было вспомнить, что и когда появилось, без чтения 100+ коммитов.

## Context
- Repo: `D:\RAG_Support_Assistant` (FastAPI + LangGraph + ChromaDB + Ollama).
- Две полных арки:
  - **Arc 68-101 (production hardening)** — 71+ commits. Ядро: resilience (retry/breaker/semaphore/timeout), observability (24 Prometheus метрики, correlation ID), health/readiness split, admin UI, multi-tenancy (schema → enforcement → per-tenant ChromaDB), fact-verification node, security (auth hardening, CORS, body size), model routing, tech debt closure.
  - **Arc 102-122 (product + enterprise + polish)** — 21 таск в 5 батчах:
    - A (UX 102-106): inline citations, mobile responsive, WCAG, UX polish, agent copilot
    - B (RAG intel 107-110): agentic tool use, nightly RAGAS, KB gap detection, contextual headers
    - C (enterprise 111-113): OpenTelemetry, SSO/OIDC, encryption at rest
    - D (differentiation 114-119): KB builder, freshness, auto-categorization, analytics, weekly reports, email channel
    - E (polish 120-122): module dedup, magic numbers → settings, integration test suite
- Spec-файлы всех тасков:
  - `codex-tasks/Archive/task-35-*.md` … `task-101-*.md` (arc 68-101 — часть в Archive, часть с ранних арок)
  - `codex-tasks/Archive/task-114-*.md` … `task-119-*.md`
  - `codex-tasks/task-10{2..9}-*.md`, `task-11{0..3}-*.md`, `task-12{0..2}-*.md`
- README.md (после task-124) — актуальный обзор фич.
- Дата закрытия arc 101: 2026-04-20. Дата закрытия arc 102-122: ~2026-04-21.

## Deliverables
`docs/CHANGELOG.md` по адаптированному Keep-a-Changelog формату:

```markdown
# Changelog

Все значимые изменения в проекте. Формат адаптирован под [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Arc 102-122] — 2026-04-21 — Product, enterprise, polish

### Batch A — UX (tasks 102-106)
- **Inline citations** в ответах RAG — источники встроены в текст с хоткей-линками (task-102).
- **Mobile responsive UI** — CSS breakpoints, туманные 375/768/1024 (task-103).
- **WCAG 2.1 AA** — контраст, keyboard nav, ARIA (task-104).
- **UX polish** — skeleton loaders, focus states, микро-анимации (task-105).
- **Agent copilot** — `/static/agent.html` с tool-use panel (task-106).

### Batch B — RAG intelligence (tasks 107-110)
- **Agentic tool use** — LLM function calling для search / lookup / escalate (task-107).
- **Nightly RAGAS evaluation** — `scripts/nightly_eval.py` + CronJob (task-108).
- **KB gap detection** — unanswered queries → `scripts/kb_gap_detector.py` (task-109).
- **Contextual ingestion headers** — секционные метаданные в chunks (task-110).

### Batch C — Enterprise (tasks 111-113)
- **OpenTelemetry** distributed tracing — `tracing/otel.py`, OTLP exporter (task-111).
- **SSO via OIDC** — `auth/oidc.py`, login flow, provider discovery (task-112).
- **Encryption at rest** — AES-256 application layer + pgcrypto колонки (task-113).

### Batch D — Differentiation (tasks 114-119)
- **Knowledge builder** — авто-драфты KB из FAQ-паттернов (task-114).
- **Freshness alerts** — документы, устаревающие по TTL (task-115).
- **Auto-categorization** — `ingestion/categorizer.py` + `config/categories.yml` (task-116).
- **Analytics dashboard** — `/static/analytics.html` (task-117).
- **Weekly quality reports** — `scripts/weekly_report.py` + GitHub Action (task-118).
- **Email channel** — IMAP poller + signed webhook (task-119).

### Batch E — Code quality (tasks 120-122)
- **Module dedup** — `prompts.py`, `state.py`, `graph.py`, `tools.py` → `agent/*` с deprecation shims (task-120).
- **Magic numbers → settings** — константы вынесены в `config/settings.py` (task-121).
- **Integration test suite** — `tests/integration/` (task-122).

### Migrations
- 004_escalated_tickets, 005_eval_results, 006_knowledge_gaps, 007_user_sso_fields,
  008_enable_pgcrypto, 009_kb_drafts, 010_document_stats, 011_trace_costs

### Testing
- 222 → 293 tests (+71).

## [Arc 68-101] — 2026-04-20 — Production hardening

### Resilience (tasks ~68-83)
- **Ollama timeout + retry с backoff/jitter** (task-69).
- **Circuit breaker** вокруг Ollama — callback вне `self._lock`, чтобы избежать deadlock (task-71).
- **Bounded pipeline concurrency** — `asyncio.Semaphore` lazy-init per-loop (task-83).
- **Request wall-time timeout** + offload CPU-bound через `asyncio.to_thread` (task-82).

### Observability (tasks ~72-81)
- **24 Prometheus метрики** + `monitoring/alert_rules.yml` (task-73, 76, 78, 81).
- **JSON `/api/metrics`** snapshot + Prometheus `/metrics`.
- **X-Request-Id** correlation ID через `ContextVar`, threads в `graph.state.trace_id` (task-79).
- **Admin view endpoints** — audit / traces / breaker reset (task-74, 90).

### Health & deploy (tasks 75, 77, 80, 98)
- **Postgres / Redis probes** (task-75).
- **`/api/health/live` vs `/ready` split** (task-77).
- **Graceful shutdown** — readiness flip до реального shutdown (task-80).
- **DB pool saturation metrics** (task-98).

### Multi-tenancy (tasks 91, 93, 95, 96)
- **Phase 1 — schema** — `tenant_id` в 12 таблицах + JWT claim (task-91).
- **Phase 2 — propagation** — state / traces / graph (task-93).
- **Phase 3 — query enforcement** — фильтр на reads, 404 вместо 403 для foreign tenant (task-95).
- **Phase 4 — per-tenant ChromaDB** — изолированные vector stores (task-96).

### Security (tasks 86, 87, 88, 92)
- **Auth rate-limit** 5/min + failure metrics + audit (task-86).
- **CORS fail-fast** в production, `*` запрещён (task-87).
- **Body-size middleware** — 1 MiB обычные, 50 MiB upload (task-88).
- **Fact-verification node** — LLM-cross-check на hallucinations (task-92).

### Admin (tasks 74, 90, 94)
- **Breaker reset** через `/admin/breaker/reset`.
- **Trace / audit purge** — auto-rотация + manual endpoint.
- **Admin UI** — `/static/admin.html`.

### Model routing (task 97)
- Classifier → simple → `llm_fast`, complex → `llm_strong`. Ambiguous → COMPLEX (safer).
- `MODEL_ROUTING_ENABLED` default off (feature flag).

### Tech debt closure (tasks 99-101)
- Fix flaky `test_rate_limiting` — conftest reset slowapi state.
- Redis cache на LLM responses — `LLM_CACHE_ENABLED` flag.
- `.gitattributes` для LF normalization.

### Testing
- Arc start: ~130 tests → Arc end: 222 tests.
```

## Acceptance
- Разделение по аркам и батчам сохранено.
- Каждый таск arc 102-122 упомянут (по функции, не по голому номеру).
- Arc 68-101 покрыт на уровне key architectural decisions, не построчно — ориентир как в skелете выше.
- Формат единый (bullet → **bold title** → краткое описание → `(task-N)` ссылка).
- Ссылки на файлы / пути — точные (не выдуманные).
- `docs/` директория создана, если отсутствует.
- Файл на русском, UTF-8.

## Notes
- **НЕ генерировать из `git log`** — слишком зашумлено, коммиты arc-end часто `Archive specs`, `Parallel batch`, и т.п.
- **Источник истины** — spec-файлы в `codex-tasks/` и `codex-tasks/Archive/`.
- Если spec недоступен (ранние tasks < 35 не архивированы специально) — полагаться на README.md и git log как второстепенный источник.
- Не дублировать содержимое README.md — CHANGELOG по сути, README по состоянию.
- Не включать дату каждого commit'а — только дата закрытия арки.
- Не писать "breaking changes" секцию, пока не возникнет реальный break.
- Скелет выше — ориентир, не обязательный дословный формат. Можешь улучшать структуру.

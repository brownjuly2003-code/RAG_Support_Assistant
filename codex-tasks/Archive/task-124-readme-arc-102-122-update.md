# Task 124 — README update for arc 102-122

## Goal
Обновить `README.md` чтобы отразить функциональность, добавленную в arc 102-122 (batches A/B/C/D/E). README сейчас актуален до arc 101 — он не знает про inline citations, mobile UI, agent copilot, OpenTelemetry, SSO/OIDC, encryption, email channel, analytics, categorization, KB drafts/freshness, integration tests.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- README.md — source of truth для env vars / API / metrics inventory (так помечено в project memory и reflected in README.md:top).
- В arc 102-122 добавлено (по батчам):
  - **A (UX)**: inline citations в ответах (task-102), mobile responsive CSS (task-103), WCAG 2.1 AA соответствие (task-104), UX polish — skeleton loaders / focus states (task-105), agent copilot UI на `/static/agent.html` (task-106).
  - **B (RAG intelligence)**: agentic tool use — function calling через LLM (task-107), nightly RAGAS evaluation (task-108), KB gap detection — находит пропуски знаний из unanswered queries (task-109), contextual headers при ingestion (task-110).
  - **C (Enterprise)**: OpenTelemetry distributed tracing (task-111), SSO via OIDC (task-112), encryption at rest — AES-256 + pgcrypto (task-113).
  - **D (Differentiation)**: knowledge builder — авто-черновики KB из FAQ-паттернов (task-114), knowledge freshness alerts (task-115), auto-categorization документов (task-116), analytics dashboard `/static/analytics.html` (task-117), weekly quality reports (task-118), email channel — IMAP poller + webhook (task-119).
  - **E (Code quality)**: dedup root modules — perompts/state/graph → `agent/*` с deprecation shims (task-120), magic numbers → `config/settings.py` (task-121), integration test suite `tests/integration/` (task-122).
- Spec-файлы: `codex-tasks/task-10{2..9}-*.md`, `task-11{0..3}-*.md`, `task-12{0..2}-*.md`, `codex-tasks/Archive/task-11{4..9}-*.md`.
- Новые файлы окружения:
  - `.env.example` — новые переменные (openотelemetry, OIDC, encryption key, email IMAP, feature flags).
  - `config/categories.yml` — категории для task-116.
  - `alembic/versions/004_escalated_tickets.py` … `011_trace_costs.py` — 8 новых миграций.
- Новые модули:
  - `agent/{graph,prompts,state,tools}.py` — переехавшие модули.
  - `auth/oidc.py`, `channels/email_channel.py`, `channels/email_webhook.py`.
  - `db/crypto.py`, `tracing/otel.py`, `evaluation/drift.py`, `ingestion/categorizer.py`.
  - `scripts/{email_poller,kb_builder,kb_gap_detector,nightly_eval,reindex,rotate_encryption_key,weekly_report}.py`.
- Новые UI: `static/{agent,analytics,login}.html`, `static/styles/agent.css`.
- Новые deploy-артефакты: `deploy/helm/templates/{cronjob-report,cronjob,deployment-email-poller}.yaml`, `.github/workflows/weekly-report.yml`.

## Deliverables
Обновлённый `README.md`:
- Раздел **Features** — новые пункты по функциональности arc 102-122, сгруппированы логически (не по task-номерам).
- Раздел **Environment variables** — все новые переменные из `.env.example`, с кратким описанием и значением по умолчанию.
- Раздел **API / Endpoints** — новые HTTP endpoints (агент, analytics, OIDC callback, email webhook).
- Раздел **Monitoring / Metrics** — новые Prometheus метрики, обновлённый итоговый счётчик (было 24, сейчас >24).
- Раздел **Deployment / Migrations** — перечисление миграций 004-011 одной строкой каждая.
- Раздел **Architecture** (если есть) — упоминание OpenTelemetry, encryption, auto-categorization в общей картине.
- Раздел **Testing** — упоминание `tests/integration/` suite.

## Acceptance
- README упоминает (по функции, не номеру task'а) все 21 фичи arc 102-122.
- Все env vars из `.env.example` описаны.
- Все новые endpoints (`/agent/*`, `/analytics/*`, `/auth/oidc/*`, `/webhook/email`, etc.) описаны в API-разделе. Проверка: `grep -rE "^@(app|router)\\.(get|post|put|delete)" api/ auth/ channels/ agent/ | sort -u`.
- Счётчик метрик: финальное число = фактическое кол-во `Counter/Gauge/Histogram/Summary` инициализаций в `monitoring/prometheus.py` + новых местах.
- Копипастабельные примеры (curl / docker-compose / env) валидны.
- Никаких ссылок на удалённые файлы или устаревшие endpoint'ы.
- README на английском (структура русская = отказ).

## Notes
- Source of truth для каждой фичи — spec-файл таска (читать каждый, не домысливать из кода).
- Не переписывать README с нуля — сохранить существующий структурный костяк (расположение TOC, стиль заголовков, форматирование таблиц).
- Не раздувать — по 2-4 строки на фичу достаточно, детали — в spec-файлах.
- Не коммитить — только изменить файл.
- Alembic: 8 миграций, для каждой одна строка вида `- 004_escalated_tickets — создаёт таблицу ... для task-XXX`.

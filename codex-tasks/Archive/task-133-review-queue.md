# Task 133 — Review queue для слабых/эскалированных трейсов

## Goal
Автоматически формировать очередь трейсов для human review (thumbs_down, low quality, escalated, fact-verification fail) — чтобы сигнал не терялся между таблицами traces/escalations/feedback.

## Context
- Repo: `D:\RAG_Support_Assistant` (FastAPI + LangGraph + ChromaDB + Ollama), 319 тестов passing, ruff clean.
- Arc 6 / Batch F — Continuous Learning Lab. Эта задача — **foundation** для последующих (curated dataset, regression runner, export). Без review queue нет источника подтверждённых кейсов.
- Текущие сигналы разбросаны:
  - `traces` таблица — `final_quality`, `fact_score`, `model_name`, `cost_usd`, `route`
  - `feedback` — thumbs_down (если уже есть; иначе смотрим state_json в traces)
  - `escalated_tickets` таблица (migration 004)
  - `traces.duration_ms` — slow traces
- Admin UI: `/static/admin.html` + `templates/traces.html` — есть base для view endpoint.

## Deliverables
1. **Alembic migration 012** (`alembic/versions/012_review_queue.py`):
   - Таблица `review_queue`: `id` pk, `trace_id` fk (unique), `tenant_id`, `reason` (enum: `thumbs_down`, `low_quality`, `escalated`, `fact_fail`, `slow_trace`, `manual`), `status` (enum: `pending`, `in_review`, `confirmed_good`, `confirmed_bad`, `dismissed`), `reviewer_notes` text, `created_at`, `reviewed_at`, `reviewed_by` (user_id fk nullable).
   - Indexes: `(tenant_id, status, created_at)`.
2. **`scripts/build_review_queue.py`**:
   - CLI: `python scripts/build_review_queue.py --days N --tenant <id|all>`.
   - Скан `traces` за период: вставляет в `review_queue` с `status=pending` если трейс соответствует одному из:
     - `final_quality < settings.quality_threshold`
     - `fact_score < settings.fact_verification_min_score` и `FACT_VERIFICATION_ENABLED=true`
     - `duration_ms > settings.slow_trace_threshold_ms` (new setting, default 10000)
     - есть связанный `escalated_tickets` запись
     - есть thumbs_down в feedback (если таблица feedback есть; если нет — смотри state_json)
   - Идемпотентность: не дублирует записи (unique trace_id).
3. **Admin endpoint** `api/app.py`:
   - `GET /admin/review-queue?status=pending&reason=*&limit=50&offset=0` — листинг с фильтрами.
   - `POST /admin/review-queue/{id}` — обновить `status`, `reviewer_notes`, `reviewed_by` (auth required, RBAC admin).
   - `GET /admin/review-queue/stats` — счётчики по `status`/`reason`.
4. **Admin UI**: extend `static/admin.html` — новый tab "Review queue" с таблицей (trace_id, reason, quality, duration, created_at) + кнопки `Confirm good`/`Confirm bad`/`Dismiss`. Не дублировать trace detail view — линк на `/admin/traces/{trace_id}`.
5. **Settings**: `config/settings.py` + `.env.example` — `SLOW_TRACE_THRESHOLD_MS: int = 10000`, `REVIEW_QUEUE_ENABLED: bool = True`.
6. **Prometheus metrics**: `review_queue_pending_total{reason}`, `review_queue_confirmed_total{verdict}`, `review_queue_oldest_pending_seconds`.
7. **Cronjob / scheduled**: документировать в `deploy/helm/templates/cronjob-review-queue.yaml` — запуск `build_review_queue.py --days 1` раз в час.
8. **Tests** (`tests/test_review_queue.py`) — минимум 8 тестов:
   - Миграция up/down.
   - `build_review_queue.py` добавляет трейс с low quality.
   - Не добавляет трейс с нормальным quality.
   - Не дублирует записи (idempotent).
   - Эскалированный трейс попадает с `reason=escalated`.
   - Slow trace попадает с `reason=slow_trace`.
   - Endpoint `/admin/review-queue` возвращает только tenant'а аутентифицированного user'а.
   - POST endpoint обновляет status + пишет `reviewed_by`.

## Acceptance
- Migration 012 up/down работает на disposable Postgres.
- `python scripts/build_review_queue.py --days 7 --tenant all` на seed-данных создаёт ≥1 запись.
- `curl -H "Authorization: Bearer <admin_jwt>" /admin/review-queue` возвращает JSON с пагинацией.
- Admin UI открывается, показывает таблицу, кнопки работают (POST).
- Prometheus: `curl /metrics | grep review_queue_` — 3+ метрики.
- pytest ≥ 319 + 8 new = 327+. Ruff clean.
- README обновлён: секция "Review queue" с командой запуска и описанием.

## Notes
- **Parallel-safe with**: task-135 (prompt registry), task-137 (online evaluators), task-139 (threshold recommendations) — разные файлы/таблицы.
- **Blocks**: task-134 (curated dataset builder), task-138 (weekly backlog), task-140 (review export).
- Не трогать существующие миграции 001-011.
- Reason enum: `review_queue_reason` как PG ENUM type (создать в миграции).
- RBAC: `/admin/review-queue` — `require_roles(["admin", "reviewer"])`.
- Не смешивать review queue с `escalated_tickets` — это разные сущности (escalation = клиенту нужен человек; review = нам нужен review качества).

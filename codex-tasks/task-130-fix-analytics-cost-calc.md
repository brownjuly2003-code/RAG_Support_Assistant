# Task 130 — Fix analytics cost calculation (task-117 follow-up)

## Goal
Починить расчёт `cost_usd` в analytics dashboard. Сейчас функция жёстко пишет `cost_usd: 0.0`, и dashboard показывает нули — фича формально есть, но пустая.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Задача — follow-up на task-117 (`codex-tasks/Archive/task-117-analytics-dashboard.md`), который был принят с ⚠️/❌ в `codex-tasks/verification-report.md`.
- Корень проблемы: функция `_load_recent_trace_summaries()` (искать в `api/app.py` — анализ `/analytics/*` endpoint'ов, либо в `api/analytics.py` если такой есть) хардкодит `cost_usd: 0.0` вместо реального вычисления из token counts.
- Миграция `alembic/versions/011_trace_costs.py` добавляет (предположительно) колонки `input_tokens`, `output_tokens`, `cost_usd` или аналогичные в `traces` / `trace_events` — это и есть source данных. Прочитать миграцию, чтобы понять схему.
- Предположительный путь вычисления:
  ```
  cost_usd = (input_tokens / 1_000_000) * input_price_per_1m
           + (output_tokens / 1_000_000) * output_price_per_1m
  ```
  где цены — per-model. Модели: `ollama_model_name` (local, cost ≈ 0, но трекать обязательно), `ollama_fast_model_name`. Когда будущая интеграция Claude API — разные цены per model.
- В `config/settings.py` может быть или надо добавить: `LLM_COST_INPUT_PER_1M_TOKENS`, `LLM_COST_OUTPUT_PER_1M_TOKENS` (per default model), или dict `llm_cost_per_1m_tokens` = `{"model_name": {"input": 0.0, "output": 0.0}}`.
- Dashboard endpoint: `/static/analytics.html` читает `/api/analytics/summary` (или подобное). Frontend показывает `total_cost_usd` за период, per-tenant breakdown, per-model breakdown.

## Deliverables
1. **Backend**:
   - Найти все места, где `cost_usd: 0.0` хардкодится. Заменить на реальное вычисление.
   - Если token counts в trace уже есть — вычислить cost на SELECT в БД (SQL: `SUM(input_tokens * input_price + output_tokens * output_price) / 1e6`), не в Python loop.
   - Если миграция 011 добавила колонку `cost_usd` для persistence — заполнять её на insert trace (в `tracing/` модуле).
   - Добавить в `config/settings.py` per-model pricing (минимум: `llm_input_price_per_1m_tokens: float`, `llm_output_price_per_1m_tokens: float`, defaults 0.0).
   - `.env.example` — задокументировать новые vars.
2. **Frontend** (`static/analytics.html` + JS):
   - Dashboard показывает реальные числа (не нули).
   - При cost=0 per-tenant (локальная Ollama) — показать "Free tier" или "$0.00" с tooltip "локальные модели не тарифицируются", а не пустое поле.
3. **Tests** (`tests/test_analytics.py`):
   - Фикстура создаёт трейсы с `input_tokens=100, output_tokens=50, model_name="claude-opus-4-7"`.
   - Тест: cost_usd рассчитывается корректно по формуле.
   - Тест: при `model_name="ollama-local"` cost_usd = 0 (но trace сохраняется).
   - Тест: aggregate по периоду даёт сумму.
4. **Migration sanity**:
   - Проверить, что alembic/versions/011_trace_costs.py реально применяется (`alembic upgrade head` — локально на disposable Postgres).
   - Если поле `cost_usd` в таблице — значение при insert пишется реально, не NULL.

## Acceptance
- `grep -rE "cost_usd[[:space:]]*[:=][[:space:]]*0\.0\b" --include="*.py" .` возвращает 0 матчей в production-коде (только в тестах как assertion allowed).
- Существующий dashboard на `/static/analytics.html` открыт — показывает реальные числа (или "Free tier" если Ollama only, но данные присутствуют).
- `pytest tests/test_analytics.py -v` — зелёный.
- `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — успешно.
- ruff clean.
- Итого: `pytest tests/ -q` ≥ 293 passed.

## Notes
- **НЕ менять** схему БД без миграции (alembic-migration добавлять, если нужно).
- Цены per-model — в settings, не в коде. Дефолт 0.0 для всех — безопасно.
- Если реализация уже читает `trace.input_tokens` / `output_tokens`, но пересчёт в USD отсутствует — это основная точка внедрения.
- Если в БД нет колонок `input_tokens`/`output_tokens` — добавить миграцией 012 (НЕ менять 011 post-factum).
- Не писать UI с нуля — минимально изменить существующий `static/analytics.html` чтобы корректно отображать новые значения.

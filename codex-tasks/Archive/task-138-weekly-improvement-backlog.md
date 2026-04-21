# Task 138 — Weekly improvement backlog

## Goal
Автоматический weekly agrегирующий отчёт, сводящий feedback/review queue/KB gaps/freshness/slow traces/low-score trends в приоритизированный backlog улучшений. Сейчас данные есть, но они не складываются в список "что делать на этой неделе".

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- **Зависит от task-133** (review queue).
- Существующее: `scripts/weekly_report.py` (task-118 quality reports), `scripts/kb_gap_detector.py` (task-109), `scripts/nightly_eval.py`, freshness alerts (task-115). Этот таск агрегирует ИХ output, не дублирует.

## Deliverables
1. **`scripts/generate_improvement_backlog.py`**:
   - CLI: `python scripts/generate_improvement_backlog.py --tenant <id|all> --week <YYYY-Www> --out reports/improvement_backlog/<YYYY-Www>.md`.
   - Собирает сигналы за 7 дней:
     - Top 10 review_queue confirmed_bad (task-133) — по частоте topic/category.
     - Top 10 KB gaps cluster (task-109).
     - Top 10 slow traces per endpoint (p95 > threshold).
     - Freshness alerts: docs с `last_update > settings.freshness_max_days` (task-115).
     - Evaluator trends (task-137): evaluator'ы, чей mean score упал >10% WoW.
     - Thumbs-down escalations (task-118 feedback).
   - Priority score per item: `impact × frequency × recency`.
     - `impact`: confirmed_bad > thumbs_down > slow > freshness > evaluator_drift (weights tunable).
     - `frequency`: сколько раз встречается в неделю.
     - `recency`: exponential decay (days ago).
   - Sort by score desc, cap at 30 items total.
2. **Output format** `reports/improvement_backlog/<week>.md`:
   ```markdown
   # Improvement backlog — week 2026-W17 (2026-04-22 to 2026-04-28)
   
   ## Summary
   - Items: 23 (priority ≥3)
   - Top source: review_queue (8), kb_gaps (6), slow_traces (5), ...
   
   ## Priority 1 — Critical (> 7)
   ### [review] Misinformation about refund policy
   - Source: review_queue, 12 confirmed_bad cases
   - Impact: high, frequency: 12, recency: 2d
   - Priority: 8.4
   - Suggested action: update prompt SUMMARIZE_PROMPT_V1 OR add FAQ entry
   - Related trace_ids: [list]
   
   ## Priority 2 — High (5-7)
   ...
   
   ## Priority 3 — Medium (3-5)
   ...
   
   ## Backlog stats
   - Items by type: review 8, kb_gaps 6, ...
   - Most common tenant: acme (14 items)
   ```
3. **Admin endpoint**:
   - `GET /admin/improvement-backlog/current` — latest week's backlog as JSON.
   - `GET /admin/improvement-backlog/archive?year=2026` — list of historical weeks.
4. **Cronjob**: `deploy/helm/templates/cronjob-improvement-backlog.yaml` — понедельник 06:00 UTC.
5. **Config** (`config/settings.py`):
   - `BACKLOG_WEIGHT_REVIEW_BAD: float = 3.0`.
   - `BACKLOG_WEIGHT_THUMBS_DOWN: float = 2.0`.
   - `BACKLOG_WEIGHT_SLOW: float = 1.5`.
   - `BACKLOG_WEIGHT_FRESHNESS: float = 1.0`.
   - `BACKLOG_WEIGHT_EVALUATOR_DRIFT: float = 2.5`.
   - `BACKLOG_MAX_ITEMS: int = 30`.
   - `BACKLOG_FRESHNESS_MAX_DAYS: int = 90`.
6. **Integration с email channel** (task-131):
   - Optional: отправлять backlog по email (TENANT_ADMIN_EMAIL env) — feature flag `BACKLOG_EMAIL_ENABLED`.
7. **Tests** (`tests/test_improvement_backlog.py`) — 6+ тестов:
   - Generator объединяет 3 источника (review queue + KB gaps + slow traces), ранжирует по priority.
   - Recency decay: сегодняшний event > неделю назад при равных impact/frequency.
   - Cap на `BACKLOG_MAX_ITEMS`.
   - Markdown output валиден (parse без ошибок).
   - Endpoint возвращает JSON.
   - Пустая неделя → отчёт с `items: 0`, не fail.

## Acceptance
- На seed'е (5 review + 3 kb_gaps + 2 slow traces) — backlog с 10 items, корректная сортировка.
- `reports/improvement_backlog/2026-W17.md` читаем.
- `pytest tests/test_improvement_backlog.py` — зелёный.
- pytest ≥ 327 + 6 new = 333+. Ruff clean.
- README секция "Improvement backlog".

## Notes
- **Blocked by**: task-133 (review_queue). Остальные источники (KB gaps, slow traces, freshness) уже existing.
- **Parallel-safe with**: task-135, task-136, task-137, task-139, task-140.
- Не дублировать логику task-118 weekly quality report — это про метрики; этот таск про actionable items.
- Веса — в settings, чтобы user'у было easy tune без кода.
- Markdown как primary format (для email / Slack / print). JSON — только для API.
- Priority computation тестируется отдельно (pure function), не нужна БД.

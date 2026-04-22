# Task 141 — Fix: implement online evaluators runtime (gap task-137)

## Goal
Закрыть task-137 полностью. Существующий test-файл `tests/test_online_evaluators.py` (16 тестов) написан в batch F но runtime не реализован — все 16 FAIL на HEAD арки 6 batch F. Этот таск добавляет runtime так, чтобы 16 тестов стали зелёными без модификации.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- HEAD — первый коммит арки 6 batch F (7 из 8 тасков landed; task-137 отложен под этот fix).
- Тесты `tests/test_online_evaluators.py` уже в working tree (после коммита — в репо), 16 штук, описывают весь функционал:
  - 7 evaluator-функций по одному-двум тестам
  - runner с error-trapping и timeout
  - migration upgrade/downgrade
  - persistence hook в pipeline
  - 2 admin endpoints
  - daily snapshot script
- Миграция 013 уже занята под `013_regression_eval_runs.py` (task-136 `eval_results` extension). Поэтому `trace_evaluations` идёт как **014**.
- ВАЖНО: один тест `test_online_evaluations_migration_upgrade_creates_table_and_indexes` ищет файл `alembic/versions/013_trace_evaluations.py`. После создания `014_trace_evaluations.py` — поправить этот тест на 014 (2 строки). Это единственная модификация существующего теста, остальные 15 должны работать без изменений.

## Deliverables

### 1. `evaluation/online_evaluators.py`
Функции, каждая принимает `trace_state: dict` и возвращает `{"score": float, "verdict": str, "metadata": dict}`:

- `evaluate_citation_coverage(state)` — доля sentences в answer с `[N]` footnote. 1.0 все, 0.0 ни одна.
- `evaluate_answer_length_anomaly(state, mean, std)` — z-score длины answer; `|z|>2` → anomaly (score=1.0), иначе 0.0. Verdict: `"ok"` / `"anomaly"`.
- `evaluate_retrieval_hit_rate(state)` — доля `retrieved_docs` с `relevance_score > 0.5`. Если rerank-scores отсутствуют — `verdict="unknown"`, `score=0.0`.
- `evaluate_tool_use_efficiency(state)` — `answer_final_tokens / total_tokens_including_tool_thrashing`. Requires `tool_calls` + `tokens` fields in state.
- `evaluate_refusal_detected(state)` — regex/keyword match по answer ("я не знаю", "не могу помочь", "обратитесь к менеджеру", "i don't know", "cannot help"). Match → score=1.0.
- `evaluate_pii_leak_suspicion(state)` — regex на phone/email/card-like patterns в answer. Match → score=1.0, metadata с matched patterns (не сами значения).
- `evaluate_language_mismatch(state)` — `langdetect.detect(query) != langdetect.detect(answer)` → score=1.0. Для очень коротких строк (<4 слов) → `verdict="low_confidence"`, score=0.0.

Regex-паттерны вынести в `config/evaluator_patterns.yml` (create new file) чтобы tune без кода. Функции читают паттерны на первом вызове и кешируют в модульную переменную.

### 2. `evaluation/evaluator_runner.py`
- `run_online_evaluators(trace_state: dict, *, timeout_ms: int = 500) -> dict[str, EvalResult]`:
  - Вызывает все 7 evaluator'ов.
  - Если evaluator raise'нет — пишет `{"score": 0.0, "verdict": "error", "metadata": {"error": str(e)}}` и продолжает.
  - Total wall-clock > `timeout_ms` → оставшиеся evaluator'ы возвращают `{"verdict": "timeout"}` и увеличивают counter.
- `persist_online_evaluations(trace_id: str, results: dict, session_factory=async_session) -> None`:
  - INSERT в `trace_evaluations` по одной строке на evaluator.

### 3. Migration `alembic/versions/014_trace_evaluations.py`
```python
revision = "014"
down_revision = "013"
```
Таблица:
- `id` pk autoincrement
- `trace_id` str(64), FK `traces.id` ON DELETE CASCADE
- `evaluator_name` str(64), NOT NULL
- `score` Float, NOT NULL
- `verdict` str(32), NOT NULL
- `metadata` jsonb, NOT NULL DEFAULT '{}'
- `evaluated_at` TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

Indexes: `(trace_id)`, `(evaluator_name, evaluated_at)`.

Поправить в `tests/test_online_evaluators.py` — единственная строка где ищется `013_trace_evaluations.py` → `014_trace_evaluations.py`.

### 4. Pipeline integration в `agent/graph.py`
После `finalize_trace` (там где пишется `state_json`) — async call:
```python
if settings.online_evaluators_enabled:
    results = await asyncio.wait_for(
        asyncio.to_thread(run_online_evaluators, trace_state),
        timeout=1.0,
    )
    await persist_online_evaluations(trace_id, results)
```
Safe-fail: при exception — log warning, не падать.

### 5. Settings в `config/settings.py` + `.env.example`
- `online_evaluators_enabled: bool = True` (env `ONLINE_EVALUATORS_ENABLED`).
- Feature flag off → pipeline пропускает persistence, endpoints возвращают empty lists.

### 6. Admin endpoints в `api/app.py`
- `GET /admin/evaluations/trends?evaluator=<name>&days=30` — time-series: `[{date, mean_score, run_count}]`. RBAC admin.
- `GET /admin/evaluations/worst?evaluator=<name>&limit=20` — топ worst scores: `[{trace_id, score, verdict, evaluated_at}]`. RBAC admin.

### 7. Prometheus metrics в `monitoring/prometheus.py`
- `online_evaluator_score` — Histogram labelled by `evaluator`, buckets [0.1, 0.25, 0.5, 0.75, 0.9, 1.0].
- `online_evaluator_runs_total{evaluator,verdict}` — Counter.
- `online_evaluator_errors_total{evaluator}` — Counter.

### 8. `scripts/eval_daily_snapshot.py`
CLI: `python scripts/eval_daily_snapshot.py --date YYYY-MM-DD` (default: вчера).
- Aggregate `trace_evaluations` за день: per-evaluator mean score, verdict counts, top-10 worst traces per evaluator.
- Записать в `reports/eval_daily/<date>.json`.
- Идемпотентность: перезаписывает если файл есть.

### 9. Cronjob `deploy/helm/templates/cronjob-eval-snapshot.yaml`
Запуск `eval_daily_snapshot.py` 02:00 UTC ежедневно.

### 10. README — раздел "Online evaluators"
Описание 7 evaluator'ов, feature flag, endpoints, snapshot workflow.

## Acceptance
- `pytest tests/test_online_evaluators.py -v` — **16/16 passing** (исключая 1 поправленную строку на `014_trace_evaluations.py`).
- `pytest tests/ -q` — **390+ passing** (374 baseline батча F + 16 online).
- `ruff check .` — clean.
- `curl /metrics | grep online_evaluator_` — 3 метрики видны.
- `curl -H "Authorization: Bearer <admin>" /admin/evaluations/trends?evaluator=citation_coverage&days=30` — 200, JSON.
- `python scripts/eval_daily_snapshot.py --date 2026-04-20` — создаёт `reports/eval_daily/2026-04-20.json`.

## Notes
- **Dependencies**: `langdetect` — проверить `requirements.txt`; если нет — добавить.
- **Metadata field**: в PG — `jsonb`; в SQLite (тесты) — `JSON` (SQLAlchemy alias работает).
- **Не писать heavy judge-LLM вызовы** — всё только на state и regex/math.
- **Не записывать в metadata полный `retrieved_docs`** — только compact summary (count, min/max/mean score).
- **Evaluator patterns YAML** пример:
  ```yaml
  refusal:
    - "я не знаю"
    - "не могу помочь"
    - "обратитесь к менеджеру"
    - "i don't know"
    - "cannot help"
  pii:
    phone: '\+?\d{1,3}[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2,4}'
    email: '[\w.+-]+@[\w-]+\.[\w.-]+'
    card: '\b(?:\d{4}[\s-]?){3}\d{4}\b'
  ```
- **После успеха — переместить `task-137-online-evaluators.md` + этот фикс-спек в `codex-tasks/Archive/`.**

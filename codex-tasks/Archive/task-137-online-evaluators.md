# Task 137 — Cheap online evaluators (без heavy judge-LLM)

## Goal
Добавить lightweight per-trace evaluators, работающие в real-time (или async через worker) без вызова heavy judge-LLM. Существующие signals: quality / factuality (LLM-cross-check — heavy). Нужно: быстрые сигналы, которые можно крутить на каждом трейсе и агрегировать в daily snapshot.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- Существующие scoring: fact-verification (task-92, LLM-based, slow), quality_threshold (quality_score из graph LLM). Оба требуют LLM → дорого на каждый запрос.
- В `state.json` трейса уже есть: `retrieved_docs`, `answer`, `citations`, `tool_calls`, `final_route`, `duration_ms`.

## Deliverables
1. **`evaluation/online_evaluators.py`** — модуль с функциями, каждая принимает `trace_state: dict` и возвращает `{score: float [0..1], verdict: str, metadata: dict}`:
   - `evaluate_citation_coverage(state)` — доля утверждений в ответе, имеющих citation'ы ( heuristic: sentences без `[N]` footnote → no citation). 1.0 = все sentences имеют, 0.0 = ни одно.
   - `evaluate_answer_length_anomaly(state, mean, std)` — z-score от rolling mean/std длины ответов того же канала; |z|>2 → anomaly.
   - `evaluate_retrieval_hit_rate(state)` — доля retrieved_docs с `relevance_score > 0.5` (если rerank scores доступны).
   - `evaluate_tool_use_efficiency(state)` — для agentic mode: `answer_final_tokens / total_tokens_including_tool_thrashing`. Низкое значение = потрачено много на tool loops.
   - `evaluate_refusal_detected(state)` — regex + keyword match на отказ ("я не знаю", "не могу помочь", "обратитесь к менеджеру" и т.д.) с score=1.0 если detected.
   - `evaluate_pii_leak_suspicion(state)` — regex match на phone/email/ID patterns в answer (shouldn't normally be there).
   - `evaluate_language_mismatch(state)` — detected language of answer ≠ detected language of query → 1.0.
2. **Orchestrator** `evaluation/evaluator_runner.py`:
   - `run_online_evaluators(trace_state) -> dict[str, EvalResult]` — запускает все evaluators, timeout 500ms на trace.
   - Безопасный fail: если evaluator кидает — записать `error` в metadata, не fail целиком.
3. **Persistence**:
   - Migration 013 (`alembic/versions/013_trace_evaluations.py`):
     - Таблица `trace_evaluations`: `trace_id` fk, `evaluator_name`, `score`, `verdict`, `metadata jsonb`, `evaluated_at`.
     - Indexes: `(trace_id)`, `(evaluator_name, evaluated_at)`.
4. **Integration point**:
   - В `agent/graph.py` на завершении pipeline (сразу после `finalize_trace`) — async вызов `run_online_evaluators` + persistence.
   - Feature flag: `ONLINE_EVALUATORS_ENABLED: bool = True` в settings.
   - При false — просто skip (no-op).
5. **Daily snapshot script** `scripts/eval_daily_snapshot.py`:
   - Aggregate `trace_evaluations` за вчерашний день.
   - Записать в `reports/eval_daily/<date>.json`: per-evaluator mean score, verdicts counts, top-10 worst traces per evaluator.
   - Cronjob `deploy/helm/templates/cronjob-eval-snapshot.yaml` — 1× день 02:00 UTC.
6. **Admin endpoint**:
   - `GET /admin/evaluations/trends?evaluator=<name>&days=30` — time-series mean score.
   - `GET /admin/evaluations/worst?evaluator=<name>&limit=20` — worst traces.
7. **Prometheus**:
   - `online_evaluator_score{evaluator}` — histogram.
   - `online_evaluator_runs_total{evaluator,verdict}`.
   - `online_evaluator_errors_total{evaluator}`.
8. **Tests** (`tests/test_online_evaluators.py`) — 10+ тестов, по 1-2 на каждый evaluator:
   - Citation coverage: answer с 2/3 sentences citations → 0.67.
   - Refusal detected: "я не знаю" → 1.0; нормальный ответ → 0.0.
   - PII leak: phone в answer → score > 0.
   - Language mismatch: ru query + en answer → 1.0.
   - Runner: если evaluator throws — безопасно записан error, остальные продолжают.
   - Persistence: после invoke pipeline запись появляется в `trace_evaluations`.
   - Feature flag off → не пишет в БД.

## Acceptance
- Evaluator runner работает в <500ms на trace (benchmark).
- Migration 013 up/down.
- Prometheus метрики видны на `/metrics`.
- Daily snapshot создаёт JSON файл.
- pytest ≥ 319 + 10 new = 329+. Ruff clean.

## Notes
- **Parallel-safe with**: task-133, task-134, task-135, task-139, task-140.
- **Blocks**: — (independent).
- Heavy evaluators (RAGAS, LLM judge) — не включать сюда; отдельная nightly pipeline (task-108) для них.
- Для language detection — использовать `langdetect` (уже в deps) или `lingua` — если ни того ни другого — добавить `langdetect` в `requirements.txt`.
- Все regex для refusal/PII — в config (`config/evaluator_patterns.yml`) чтобы tune без кода.
- Не записывать полные `retrieved_docs` в `trace_evaluations.metadata` — только scores / compact summary.

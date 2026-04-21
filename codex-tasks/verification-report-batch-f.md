# Arc 6 / Batch F — Verification sweep (2026-04-21)

Repo: `D:\RAG_Support_Assistant`, HEAD = `ee5ff51` (arc 102-122 fully closed).
Codex выполнил 8 тасков (133-140) в working tree; ничего не закоммичено.

## Environment check
- `pytest tests/ -q` — **374 passed, 16 failed (`tests/test_online_evaluators.py` — все 16)**. Длительность 10:12.
- `ruff check .` — **All checks passed**.
- `git status` — 10 modified + 38 untracked; спек-файлы 133-140 и оркестратор ещё в `codex-tasks/`, не в `Archive/`.

## Per-task verdict

| Task | Verdict | Tests | Notes |
|------|---------|-------|-------|
| 133 review queue | ✅ PASS | 9/9 | spec fully covered |
| 134 curated dataset | ✅ PASS | 8/8 | spec fully covered |
| 135 experiment registry | ⚠️ PARTIAL | 8/8 | graph.py gap |
| 136 regression runner | ✅ PASS | 10/10 | migration reuse is reasonable |
| 137 online evaluators | ❌ FAIL | 0/16 | only тест-файл, рантайма нет |
| 138 improvement backlog | ✅ PASS | 7/7 | spec fully covered |
| 139 threshold recommendations | ✅ PASS | 6/6 | report уже сгенерирован |
| 140 review export/import | ✅ PASS | 6/6 | spec fully covered |

### task-133 — Review queue ✅
- Migration `alembic/versions/012_review_queue.py` — таблица + ENUMs + index по `(tenant_id, status, created_at)` по spec.
- `scripts/build_review_queue.py` — CLI `--days/--tenant`, all 6 reasons (thumbs_down/low_quality/escalated/fact_fail/slow_trace/manual), idempotent через `ON CONFLICT (trace_id) DO NOTHING`.
- Admin endpoints: `GET /admin/review-queue`, `POST /admin/review-queue/{id}`, `GET /admin/review-queue/stats` ✓.
- Settings: `review_queue_enabled`, `slow_trace_threshold_ms=10000` ✓.
- Prometheus: `set_review_queue_pending/confirmed/oldest_pending` — 3 метрики ✓.
- Admin UI: 23 упоминания `review-queue` в `static/admin.html` — tab wired.
- Cronjob: `deploy/helm/templates/cronjob-review-queue.yaml` ✓.
- Tests: 9 passing, spec требовал 8+.

### task-134 — Curated dataset builder ✅
- `scripts/build_curated_dataset.py` с `--include-bad`, dedup по `case_id` ✓.
- `evaluation/dataset.py` + `evaluation/curated_cases.jsonl` placeholder ✓.
- Endpoints: `GET /admin/curated-dataset/stats`, `POST /admin/curated-dataset/rebuild` (async job через Redis tracker) ✓.
- Prometheus: `set_curated_dataset_size`, `set_curated_dataset_last_build_timestamp` — 2 метрики ✓.
- Tests: 8 passing, spec требовал 7+.

### task-135 — Prompt / experiment registry ⚠️
- `evaluation/experiment_schema.py` — pydantic `Experiment` модель ✓.
- Scripts `experiment_new.py`, `experiment_apply.py` — CLI + dry-run/stage/deploy ✓.
- `config/settings.py`:649-653 читает `EXPERIMENT_ID` env + `config/experiment_override.yaml` ✓.
- `agent/prompts.py`: `PROMPT_REGISTRY` dict + `DEPLOYED_PROMPT_OVERRIDES` ✓.
- `agent/prompt_registry.py`: `get_prompt(name, experiment)` с приоритетом experiment→staged→default ✓.
- Admin endpoints: list + detail + archive + regression-run trigger ✓.
- Tests: 8 passing, spec требовал 6+.
- **Gap:** spec требовал «существующие потребители `agent/graph.py` переведены на `get_prompt("summarize", experiment)` вместо прямого import». Grep в `graph.py` не находит ни `get_prompt`, ни импорта `prompt_registry`. Прямые импорты prompts остались. Staged overrides не достигнут runtime-pipeline'а, только если через `DEPLOYED_PROMPT_OVERRIDES` (что deploy-mode, не stage).

### task-136 — Regression runner ✅
- `scripts/regression_eval.py` — CLI с baseline/candidate/dataset/tenant/max-cases/seed ✓.
- `REGRESSION_GATE_MAX_REGRESSIONS=2`, `REGRESSION_GATE_MIN_PASS_RATE=0.85` в settings ✓.
- `.github/workflows/ci.yml:121-181` — job `regression-eval` ✓.
- Endpoints: `POST /admin/experiments/{id}/regression-run`, `GET /admin/regression-runs`, `GET /admin/regression-runs/{id}` ✓.
- Prometheus: `regression_runs_total{result}`, `regression_runs_duration_seconds` ✓.
- Migration: `013_regression_eval_runs.py` — расширяет `eval_results` колонками `kind`, `run_id`, `baseline_experiment_id`, `candidate_experiment_id`. Spec задачи не требовал отдельной миграции — reuse разумный.
- Tests: 10 passing, spec требовал 7+.

### task-137 — Online evaluators ❌ **FAIL** (критично)
Это единственный катастрофический gap в батче. Написан только test-файл (16 тестов) — все 16 FAIL, потому что **runtime не реализован вовсе**:

| Spec deliverable | Status |
|------------------|--------|
| `evaluation/online_evaluators.py` (7 функций) | ❌ отсутствует |
| `evaluation/evaluator_runner.py` (orchestrator + timeout) | ❌ отсутствует |
| `scripts/eval_daily_snapshot.py` | ❌ отсутствует |
| Migration 013 `trace_evaluations` | ❌ 013 занят под regression_eval_runs (task-136) |
| Integration в `agent/graph.py` + `ONLINE_EVALUATORS_ENABLED` | ❌ ни флага, ни wire-in |
| Admin endpoints `/admin/evaluations/trends`, `/admin/evaluations/worst` | ❌ тесты возвращают 404 |
| Prometheus `online_evaluator_*` | ❌ grep не находит |
| Cronjob `cronjob-eval-snapshot.yaml` | ❌ не создан |
| README раздел | ❌ отсутствует |

Ошибки pytest подтверждают каждый пункт: `FileNotFoundError` на `013_trace_evaluations.py`, `ImportError` на `scripts.eval_daily_snapshot`, 404 на `/admin/evaluations/trends|worst`, пустой persist на pipeline-hook.

**Требуется отдельный fix-spec (task-141)** — либо полноценно реализовать online evaluators (спек 137 остаётся в силе), либо сузить scope и закрыть частично.

### task-138 — Weekly improvement backlog ✅
- `scripts/generate_improvement_backlog.py` агрегирует review_queue/KB gaps/slow traces/freshness/evaluator drift с priority = impact × frequency × recency.
- Endpoints `/admin/improvement-backlog/current`, `/admin/improvement-backlog/archive` ✓.
- Cronjob `cronjob-improvement-backlog.yaml` ✓.
- Settings: все `BACKLOG_WEIGHT_*` + `BACKLOG_MAX_ITEMS=30` + `BACKLOG_FRESHNESS_MAX_DAYS=90` + `BACKLOG_EMAIL_ENABLED` ✓.
- Tests: 7 passing, spec требовал 6+.
- Замечание: evaluator drift сигнал ссылается на task-137 агрегаты — в текущем состоянии будет no-op пока 137 не починят, но backlog корректно не падает.

### task-139 — Threshold recommendations ✅
- `scripts/analyze_thresholds.py` с F1-optimization ✓.
- `reports/threshold_recommendations.md` — **уже сгенерирован** (`untracked`).
- Endpoints `/admin/thresholds/analysis`, `/admin/thresholds/refresh` ✓.
- Cronjob `cronjob-threshold-analysis.yaml` ✓.
- Settings: `THRESHOLD_ANALYSIS_MIN_LABELS=20` ✓.
- Tests: 6 passing, spec требовал 5+.

### task-140 — Review export/import ✅
- `scripts/review_export.py` + `scripts/review_import.py` ✓.
- `.gitignore:19` — `review_batch_*.jsonl` ✓.
- Dry-run, REVIEWER_EMAIL env, `--confirm` для больших batch'ей — по spec.
- Tests: 6 passing, spec требовал 6+.

## Aggregate metrics
- **Tests:** 319 baseline → 374 passing (+55) + 16 failing = **390 total**. Target arc 6 был ~370+, достигнут по количеству.
- **Ruff:** clean.
- **Migrations:** 012 ok, 013 nomenclature ambiguous (нужен либо 014 для task-137 trace_evaluations, либо переименовать).
- **Admin endpoints:** +15 новых (review-queue ×3, curated ×2, thresholds ×2, backlog ×2, experiments ×4, regression ×2), minus task-137 ×2.
- **Prometheus:** +6 групп (review_queue ×3, curated_dataset ×2, regression_runs ×2), minus task-137 ×3.
- **Cronjobs:** review-queue, improvement-backlog, threshold-analysis ✓; eval-snapshot (task-137) ✗.

## Required fix-specs

### task-141 — fix: implement online evaluators runtime
**Goal:** закрыть полный функционал task-137 (см. исходный spec `task-137-online-evaluators.md`) так, чтобы существующие 16 тестов стали зелёными без модификации.

**Must do:**
- Создать `evaluation/online_evaluators.py` с 7 функциями по spec.
- Создать `evaluation/evaluator_runner.py` с `run_online_evaluators(state)` + 500ms timeout + safe-fail.
- Создать `scripts/eval_daily_snapshot.py` с ежедневным агрегатом в `reports/eval_daily/<date>.json`.
- Создать миграцию `alembic/versions/014_trace_evaluations.py` (013 уже занят под regression) с таблицей `trace_evaluations` + обновить `down_revision` для регрессионного — либо переименовать 013→014 и сделать trace_evaluations = 013 (менее инвазивно, но ломает уже написанный тест, который ищет 013 по названию). Рекомендуется: миграция 014 и поправить один тест в `test_online_evaluators.py`, который ищет `013_trace_evaluations.py` → `014_trace_evaluations.py`.
- Wire в `agent/graph.py` после `finalize_trace` async вызов runner'а + `ONLINE_EVALUATORS_ENABLED` flag (default true).
- Endpoints `/admin/evaluations/trends?evaluator=&days=`, `/admin/evaluations/worst?evaluator=&limit=`.
- Prometheus: histogram `online_evaluator_score{evaluator}`, counters `online_evaluator_runs_total{evaluator,verdict}` + `online_evaluator_errors_total{evaluator}`.
- `deploy/helm/templates/cronjob-eval-snapshot.yaml` 02:00 UTC.
- README section "Online evaluators".

**Acceptance:** `pytest tests/test_online_evaluators.py -v` — 16/16 зелёные.

### task-142 — fix: route graph.py through prompt_registry.get_prompt
**Goal:** чтобы experiment stage-mode реально менял поведение pipeline'а, а не только deploy-mode.

**Must do:**
- В `agent/graph.py` заменить прямые импорты `from agent.prompts import ...` на `from agent.prompt_registry import get_prompt`, где применяется промпт — звать `get_prompt(name, experiment)`.
- Experiment передавать через LangGraph `state` (если его можно протащить) или модульную переменную, инициализируемую один раз на request scope.
- Добавить тест: при `EXPERIMENT_ID=...` set + `config/experiment_override.yaml` с `prompt_overrides`, пайплайн отдаёт override'нутый промпт на `rewrite`/`summarize`.

**Acceptance:** `pytest tests/test_experiment_registry.py` остаётся зелёным + новый integration test на graph routing.

## Commit recommendation

Предлагаемая последовательность коммитов (НЕ batch, отдельно per task — легче bisect):

1. `feat(review-queue): task-133 review queue with reasons + admin UI + metrics`
2. `feat(curated-dataset): task-134 JSONL curated dataset builder`
3. `feat(experiments): task-135 prompt/experiment registry with staged overrides`
4. `feat(regression): task-136 regression runner + CI gate`
5. `feat(backlog): task-138 weekly improvement backlog`
6. `feat(thresholds): task-139 F1-based threshold recommendations`
7. `feat(review-sync): task-140 offline review export/import`
8. `chore: archive arc 6 batch F specs 133/134/135/136/138/139/140`
9. После fix-specs 141/142: `fix(evaluators): task-141 implement online evaluators runtime` + `fix(graph): task-142 route prompts through get_prompt`
10. `chore: archive fix-specs 141/142 + close arc 6 batch F`

task-137 спека **не** архивируется до 141 — держать как reminder что функциональность не закрыта.

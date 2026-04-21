# Task 136 — Regression runner для experiment × curated dataset

## Goal
Автоматический прогон curated dataset (task-134) против current OR experimental конфигурации (task-135) с сравнением `baseline vs candidate`. Результат — pass/fail regression gate. Без regression runner изменения в prompts/models идут «наощупь».

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- **Зависит от task-134** (curated_cases.jsonl) и task-135 (experiment registry).
- Существующий `scripts/nightly_eval.py` делает RAGAS eval — но на каком dataset, как интерпретируется pass/fail — непрозрачно. Этот task не замещает nightly, а дополняет: более быстрый, целевой на regression gate перед изменениями.
- `eval_results` таблица (migration 005) — есть поля `quality_score`, `factuality_score`. Добавим persistence run'ов туда.

## Deliverables
1. **`scripts/regression_eval.py`**:
   - CLI: `python scripts/regression_eval.py --baseline <exp_id|current> --candidate <exp_id|current> --dataset evaluation/curated_cases.jsonl --tenant <id|all> --max-cases 100 --seed 42`.
   - Для каждого `CuratedCase`:
     - Run baseline config → capture answer, quality, factuality, citations, duration_ms, cost_usd, route.
     - Run candidate config → то же.
     - Diff: `{answer_changed, quality_delta, factuality_delta, route_changed, citations_delta, cost_delta}`.
   - Apply acceptance from `case.expected`:
     - `answer_contains` — all strings present in answer.
     - `answer_not_contains` — none present.
     - `route` matches.
     - `min_quality` / `min_factuality` — scores ≥ thresholds.
     - `citations_min_count` — count ≥ value.
   - Aggregate: baseline_pass_rate, candidate_pass_rate, regressions (case passed on baseline, failed on candidate), new_passes (vice versa), neutral.
2. **Output**:
   - `reports/regression/<timestamp>-<baseline>-vs-<candidate>.md` — human-readable отчёт:
     - Summary table.
     - Regressions list (case_id, query, baseline_answer, candidate_answer, why failed).
     - New passes list.
     - Aggregate metrics.
   - JSON sidecar для программной обработки.
   - Запись в `eval_results` таблицу (одна на run, с `kind='regression'` и ссылкой на experiment_ids).
3. **Regression gate policy** (`config/settings.py` + `.env.example`):
   - `REGRESSION_GATE_MAX_REGRESSIONS: int = 2` — fail CI / deploy если регрессий >N.
   - `REGRESSION_GATE_MIN_PASS_RATE: float = 0.85`.
4. **Exit code**:
   - 0 = candidate ≥ baseline по всем gate criteria.
   - 1 = regression violation (CI fail).
   - 2 = infrastructure error (Ollama down, etc.).
5. **GitHub Actions job** (`.github/workflows/ci.yml` extension):
   - Новый job `regression-eval` — `continue-on-error: true` (первые прогонов не блокируют).
   - Условие: если в PR изменён `agent/prompts.py`, `config/settings.py`, или `evaluation/experiments/*.yaml`.
6. **Admin endpoint**:
   - `POST /admin/experiments/{id}/regression-run?baseline=<id>` — триггер async regression, job_id в ответе.
   - `GET /admin/regression-runs?limit=20` — листинг последних runs.
   - `GET /admin/regression-runs/{id}` — report.
7. **Prometheus**: `regression_runs_total{result=pass|fail}`, `regression_runs_duration_seconds`, `regression_last_pass_rate{baseline,candidate}`.
8. **Tests** (`tests/test_regression_runner.py`) — 7+ тестов:
   - Run на mock dataset (3 cases), mock LLM — baseline vs candidate, aggregation correct.
   - Regression detection: case passing baseline, failing candidate → в regressions list.
   - New pass detection: vice versa.
   - Exit code 1 при `regressions > REGRESSION_GATE_MAX_REGRESSIONS`.
   - Exit code 0 при pass.
   - Idempotent: same seed → same results.
   - JSON output schema валиден.

## Acceptance
- На seed'е 5+ curated cases `regression_eval.py --baseline current --candidate current` → pass_rate 100%, regressions=0, exit 0.
- Candidate с явно сломанным prompt (overriden в experiment) → regressions > 0, exit 1.
- Report `.md` человеко-читаем, JSON валидный.
- `pytest tests/test_regression_runner.py` — зелёный.
- pytest ≥ 334 + 7 new = 341+. Ruff clean.
- README раздел "Regression eval" с workflow.

## Notes
- **Blocked by**: task-134 (curated_cases.jsonl) + task-135 (experiment registry).
- **Blocks**: — (independent tail).
- **Parallel-safe with**: task-137, task-138, task-139, task-140 (файлы не пересекаются).
- Определённость: фиксировать `temperature=0` (или equivalent) в обоих конфигах runtime; иначе regression будет шумный.
- Для Ollama `temperature` передаётся через `LocalOllamaLLM`. Проверить, что можно принудительно задать через experiment overrides.
- `--max-cases` должен randomly sample (seed'ом) subset — для быстрого CI-режима.
- НЕ запускать heavy judge-LLM (`ragas`) внутри regression runner — cheap metrics (quality/factuality scores из state.json, answer substring checks). Heavy eval — в task-108 nightly.
- Не смешивать regression runs с nightly eval results — разные таблицы / разные записи.

# Task 177 — Regression benchmark via GraceKelly Claude Sonnet, on expanded KB

## Status

Closed 2026-04-26 on the RAG side. The original single-model
`gracekelly-primary` acceptance path was superseded by task-178:
`scripts/regression_eval.py` now accepts routing-profile targets, and the
live run uses `--candidate-profile gracekelly-mixed` so fast Self-RAG helper
calls go through Mistral while strong answer generation goes through
GraceKelly browser routing.

Current evidence:

- `evaluation/curated_cases.jsonl` contains 20 cases.
- `scripts/run_regression_via_gracekelly.ps1` supports `-CandidateProfile`.
- Full 20-case evidence landed in `reports/regression/20260426T113855Z-*`.
- Final closure is documented in
  `codex-tasks/verification-report-regression-gracekelly.md` rev 5.
- `task-178` is archived in
  `codex-tasks/Archive/task-178-regression-eval-profile-target.md`.

This file is kept in `codex-tasks/` as a visible historical task note; do not
restart the original `claude-sonnet-4-6-api` single-model path unless you
explicitly want a browser-only stress test rather than the product pipeline.

## Goal
Получить честный quality/cost/latency сигнал на Claude Sonnet 4.6, не упираясь в Mistral free-tier 60 rpm. Candidate = `claude-sonnet-4-6-api` через GraceKelly (`gracekelly-primary` profile, browser.perplexity adapter). Baseline = `ministral-3b-latest` direct Mistral (уже в `external-mistral` profile). Расширить curated dataset до 20 cases на текущем KB, чтобы статистика была не из 5 точек.

## Dependency
**Блокировано task-176 continuation** (bug 2 asyncpg race + bug 4 FK ordering). Без них live regression run потеряет большинство `trace_evaluations` в racing INSERT-ах и финальный `INSERT INTO eval_results` упадёт, а значит candidate pass rate будет искажён. HEAD `324305c` = partial landing (bugs 1 + 3 закрыты, bug 2 + 4 ждут). Эта таска стартует после того как task-176 continuation landed и live run выходит clean (0 warnings).

## Context
- Первый regression run через RAG pipeline (commit `d7f8382`) использовал `ministral-3b-latest` vs `mistral-small-latest`. Результат на 5 cases: baseline 100%/candidate 80%. `mistral-large-latest` провалил free-tier rate limit (60 rpm) — на case делается ~4 LLM calls, 5 cases × 4 ≈ 20 calls, плюс evaluator calls — переходит лимит окна.
- `GraceKelly` (D:\GraceKelly\) запущен на `http://127.0.0.1:8011`, поднимается через `uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011`. Конфиг .env у GraceKelly имеет `GRACEKELLY_EXECUTION_PROFILE=dry-run` — это симулирует ответы. **Перед прогоном этого таска профиль должен быть переключён на real execution** (через `.env` GraceKelly или override env при запуске).
- `config/providers.yml` уже содержит `claude-sonnet-4-6-api` под gracekelly provider (alias `gk-claude-sonnet`, `gk-strong`).
- GraceKelly `/api/v1/orchestrate {model:"claude-sonnet-4-6",...}` работает end-to-end (verified в commit `e703571`, smoke) — no rate limit (browser Perplexity).
- Текущий `evaluation/curated_cases.jsonl`: 10 cases (warranty 3, returns 3, errors 4), все KB-aligned, формат Pydantic `CuratedCase`.
- Seed docs: `docs/{warranty.md,returns_policy.md,errors_e10_e30.md}`. Русскоязычные.
- `scripts/regression_eval.py` требует `run_qa_pipeline` через полный RAG стек (Postgres + Redis + Ollama + ChromaDB). Ollama используется только для embedding / reranker, не для LLM при `LLM_PROVIDER_PROFILE=gracekelly-primary`.

## Deliverables

### Expanded dataset
- `evaluation/curated_cases.jsonl`: расширить с 10 до 20 cases. Покрытие — тот же 3-документный KB, но глубже:
  - warranty: 5 cases (текущие 3 + "что не входит в гарантию" expanded, "срок хранения чека", "куда нести если чека нет").
  - returns: 5 cases (3 существующих + "возврат денег на другую карту", "что если упаковки нет").
  - errors: 7 cases (4 существующих + различие E20 засор vs насос, сброс E25 шаг-за-шагом, действия при E30).
  - 3 "off-topic" кейса: вопросы ВНЕ KB (например "как работает wi-fi"), `expected.answer_contains: ["не знаю", "обратитесь"]` — проверяет graceful refusal.
- Формат: один JSON-object per line, Pydantic `CuratedCase` schema (`case_id, tenant_id, query, expected.{answer_contains, route, min_quality, answer_not_contains}`). Language query: русский (как KB).

### Regression prerequisites wrapping
- `scripts/run_regression_via_gracekelly.sh` (или `.ps1` если проще для Windows dev): shell wrapper, который:
  1. Stоп-guard: если GraceKelly не отвечает `/healthz/ready`, печатает инструкцию по запуску + exit 1.
  2. Stop-guard: если `curl /api/admin/providers` показывает `GRACEKELLY_EXECUTION_PROFILE=dry-run`, печатает warning + exit 1.
  3. Стартует disposable `postgres:16-alpine` + `redis:7-alpine` (port-less или известные порты), waits ready.
  4. Применяет миграции (`alembic upgrade head`).
  5. Прогоняет ingestion: `python -c "from ingestion.pipeline import IngestPipeline; ..."` поверх `docs/` (или seed через `python -m demo.seed_docs` + ingest).
  6. Запускает `python scripts/regression_eval.py --baseline ministral-3b-latest --candidate claude-sonnet-4-6-api --allow-paid-apis --max-cases 20` с правильным env (`LLM_PROVIDER_PROFILE=gracekelly-primary` + `MISTRAL_API_KEY` + `GRACEKELLY_BASE_URL`).
  7. Stop disposable containers в trap.
- Скрипт должен быть idempotent: повторный запуск не ломается на already-running containers (use `docker ps -q -f name=...` check).
- Скрипт не коммитит артефакты — это задача того, кто запускает.

### Verification report
- `codex-tasks/verification-report-regression-gracekelly.md`: документирует прогон (baseline/candidate метрики + pass-rate delta + cost ratio + 2-3 примера неудачных кейсов с текстом ответа для контраста).
- `reports/regression/` наполняется двумя файлами (json + md) из прогона — commit в том же change.

## Acceptance criteria
- [ ] task-176 continuation landed — live regression run выходит без `InterfaceError` и `ForeignKeyViolationError` warnings (предусловие).
- [ ] `evaluation/curated_cases.jsonl` содержит 20 cases: 17 KB-aligned + 3 off-topic refusal cases. Все валидны `CuratedCase` schema.
- [ ] `scripts/run_regression_via_gracekelly.sh` exit 0 при правильно запущенном GraceKelly (live execution profile) и exit 1 с понятным сообщением в остальных случаях.
- [ ] Прогон `scripts/regression_eval.py` через gracekelly-primary profile candidate=`claude-sonnet-4-6-api`:
  - `aggregate.candidate_pass_rate >= 0.85` на 20 cases (gate project'а).
  - Нет повторяющихся WARNING'ов из task-176.
  - `aggregate.candidate_total_cost_usd == 0.0` (GraceKelly cost model — 0, proxy through Perplexity Pro).
  - `aggregate.candidate_refusal_rate` отражает 3 off-topic cases корректно (close to 0.15 для правильной модели).
- [ ] Reports landed в `reports/regression/` + `verification-report-regression-gracekelly.md` в `codex-tasks/`.
- [ ] `ruff check scripts/ evaluation/` clean.
- [ ] `pytest tests/ --ignore=tests/integration --ignore=tests/test_a11y.py -p no:schemathesis -q --tb=no` — без регрессий (baseline 511 passed / 1 skipped).

## Notes
- **GraceKelly execution profile**: проверить `D:\GraceKelly\.env` field `GRACEKELLY_EXECUTION_PROFILE`. Сейчас `dry-run` (возвращает `"[dry-run] Simulated response for: ..."`). Для real signal нужен `production` или эквивалент. **Не менять** её `.env` без подтверждения — wrapper должен только **обнаруживать** и fail-fast.
- GraceKelly `/api/v1/smart` сейчас fallback на `claude-sonnet-4-6` (после rip Mistral в их batches 101-b/c), но RAG pipeline обращается к `gracekelly-primary` profile → получает `claude-sonnet-4-6-api` напрямую через `/orchestrate`. Оба пути валидны.
- Baseline = ministral-3b direct: чтобы было реальное cost сравнение (Mistral ~$0.000014 per case vs GraceKelly = $0 per case).
- Если во время прогона candidate pass rate < gate (85%), это **не провал таски** — это сигнал что Claude Sonnet через browser даёт другой shape ответов (расплывчатые отвлечённые abstracts) чем direct Mistral, и curated expectations нужно править. Задокументировать в verification report как observation, не fail.
- **Не трогать** `scripts/regression_eval.py` этой таской — только wrapper скрипт + dataset. Если regression_eval.py имеет bug, открывать отдельную таску.
- GraceKelly + native Ollama + de_project-redis уже running в dev окружении — wrapper должен coexist'ить.

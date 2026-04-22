# Meta-task — Arc 7 / Batch I: Continuous Learning Phase 2

## Goal
Перевести Arc 6 learning loop из offline-assisted режима в managed production optimization cycle: staged-vs-deployed comparison, automatic rollback по regression gate / online-evaluator drift, tenant-level experiment assignment со sticky exposure, adaptive threshold recommendations, dataset freshness automation. Планируй и реализуй сам по паттерну batch G/H (meta → proposal update → orchestrator → task specs → implementation → verification → commits → archive → CHANGELOG).

## Context

### Почему этот batch
Batch F (arc 6) построил foundation: review queue, curated dataset, experiment registry с `CURRENT_EXPERIMENT` ContextVar, regression runner, online evaluators, improvement backlog, threshold recommendations. Batch G/H добавили provider abstraction с GraceKelly + Mistral. Сейчас цикл всё ещё требует ручного решения на каждом шаге (human apply experiment, human check regression, human adjust threshold). Batch I автоматизирует.

**ВАЖНЫЙ CAVEAT**: у проекта пока **нет реального production traffic**. Single-user local deploy. Часть automation (sticky exposure, auto-rollout) на текущем volume'е даст шумный сигнал. **Всё должно быть feature-flagged off by default** и включаться только после появления signal. Логика — "написать, но не запускать автоматически".

### Текущее состояние
- HEAD `e063016`, 426 tests passing, ruff clean.
- Review queue (migration 012), curated dataset, experiments registry + YAML overrides + `CURRENT_EXPERIMENT` ContextVar, regression runner с CI gate, online evaluators (migration 014) с 7 функциями + snapshot script, improvement backlog, threshold analyzer F1-based.
- Provider abstraction: Ollama/GraceKelly/Mistral с failover chain.
- Multi-tenancy Phase 1-4 (schema → propagation → query enforcement → per-tenant ChromaDB).

## Batch I scope (6 tasks, 153-158)

### task-153 — Experiment deployment lifecycle state machine
Сейчас experiment в registry имеет status `draft|running|completed|deployed|archived`, но переход делается вручную через `experiment_apply.py --mode`. Надо формализовать lifecycle с persisted state:
- Migration 015 `experiment_deployments` — per-experiment deployment history с `staged_at`, `deployed_at`, `rolled_back_at`, `regression_run_id`.
- Admin endpoints `/admin/experiments/{id}/deploy`, `/admin/experiments/{id}/rollback` с valid state transitions.
- Status guard: нельзя `deploy` без зелёного regression run на curated dataset.
- Tests: 6+ (migration, state transitions valid/invalid, guard block'ает deploy без regression green).

### task-154 — Tenant-level experiment assignment + sticky exposure
Цель — разные tenants могут быть в разных experiments одновременно, exposure persists для users в пределах tenant/session.
- Migration 016 `experiment_assignments` — `tenant_id`, `experiment_id`, `rolled_out_at`, `rollout_percentage` (0-100).
- Entry-point в `agent/graph.py` при старте pipeline: по `tenant_id` и stable hash(user_id or session_id) определяет попадает ли запрос в experiment exposure, подтягивает experiment в `CURRENT_EXPERIMENT` ContextVar.
- Admin endpoints `/admin/experiments/{id}/assignments` для управления.
- Feature flag `EXPERIMENT_ASSIGNMENT_ENABLED: bool = False` default (не ломает единственного юзера).
- Tests: 6+ (sticky across requests, percentage rollout корректный, flag off → assignment skipped).

### task-155 — Automatic rollback on regression / evaluator drift
Watcher detection для deployed experiments: если последние N трейсов (или daily window) показывают regression по quality / factuality / refusal rate → автоматически rollback.
- Scheduled check (cronjob или hot path): за последние 1000 трейсов в experiment exposure vs baseline window — сравнение mean online evaluator scores. Порог детекции drift — `ROLLBACK_DRIFT_THRESHOLD_PCT: float = 10.0`.
- При detection: experiment_deployments.rolled_back_at = now, notification через email channel (task-131 infra) к TENANT_ADMIN_EMAIL, `CURRENT_EXPERIMENT` больше не выдаёт этот experiment.
- Prometheus: `experiment_auto_rollback_total{experiment_id,reason}`.
- Feature flag `AUTO_ROLLBACK_ENABLED: bool = False` default.
- Tests: 6+ (detection triggers при drift > threshold, no false positive при normal variance, notification отправлена, metric increments).

### task-156 — Dataset freshness + curator hygiene automation
Curated dataset устаревает (pricing changes, KB evolves, patterns shift). Automation:
- Scheduled job (cronjob): для каждого `CuratedCase` старше N дней (`CURATED_CASE_STALE_DAYS: int = 180`) — re-run через current primary profile, если answer/route/quality различаются от zoned original по threshold → flag case как `status=stale_needs_review`.
- Admin endpoint `/admin/curated-dataset/stale` — list stale cases.
- Migration 017 если нужно добавить `status` + `staleness_reason` колонки в `curated_cases` (сейчас JSONL; возможно переводим в DB).
- Tests: 6+ (staleness detection, re-run comparison, status update, endpoint filtering).

### task-157 — Recommendation engine for prompt/routing/threshold changes
На базе review queue + evaluator trends + threshold analyzer + regression results — автоматический weekly recommendation report с специфическими actionable suggestions (не просто "quality падает", а "поменять `SUMMARIZE_PROMPT_V1` на version X — staged experiment уже есть в registry, pass rate 92% vs current 85%").
- `scripts/generate_recommendations.py` — aggregates сигналы, выдаёт ranked list в `reports/recommendations/<week>.md`.
- Integration с улучшением backlog (task-138) — объединяет источники в один actionable список.
- Endpoint `/admin/recommendations/current`.
- Feature flag `RECOMMENDATIONS_ENABLED: bool = True` default (только генерация report'а, без автомат применения).
- Tests: 5+ (aggregation correct, ranking stable, markdown format valid).

### task-158 — Experiment comparison dashboard (staged vs deployed vs baseline)
Admin UI tab показывает side-by-side metrics для активных experiments:
- Deployed version — baseline metrics за period
- Staged version — если есть, metrics за regression run
- Candidate (draft) — если есть pending experiment
- Metrics: quality score distribution, online evaluator breakdown, cost per trace, latency p50/p95.
- Endpoint `/admin/experiments/comparison?deployed=<id>&staged=<id>` — JSON.
- Tab в `static/admin.html` с charts (Plotly или простая ASCII/Sparkline — не перегружать).
- Tests: 4+ (comparison computation, endpoint returns correct shapes, UI renders without JS errors).

## CRITICAL SAFEGUARDS

- **Все новые automation feature-flag'ами off by default** — проект остаётся manual-decision кроме recommendations generator (read-only).
- **Auto-rollback НЕ активирован автоматически** — `AUTO_ROLLBACK_ENABLED=False` default. Нельзя случайно уронить single-user experience.
- **Tenant assignment не ломает default tenant flow** — при `EXPERIMENT_ASSIGNMENT_ENABLED=False` запрос идёт без experiment, как сейчас.
- **No breaking changes на existing provider abstraction** — batch G/H layer не трогать, только добавлять hooks.
- **No paid API calls в тестах** (safeguard сохранён с batch G).
- **Migrations 015/016/(017)** — `downgrade()` должен работать (нужен если rollback деплоя).

## Deliverables

### Docs
- `codex-tasks/orchestrator-batch-i-continuous-learning-phase-2.md` — граф зависимостей (153 → 155; 154 независим; 156 независим; 157 зависит от 155/156; 158 зависит от 153).
- `codex-tasks/task-153-experiment-deployment-lifecycle.md` ... `task-158-experiment-comparison-dashboard.md`.
- Update `codex-tasks/arc-7-proposal.md` статус batch I.

### Code
- 3 migrations (015, 016, 017 если нужна).
- Admin endpoints (перечислены per task).
- `scripts/generate_recommendations.py` + cronjob.
- Feature flags в settings.
- Prometheus metrics.
- Changes в `agent/graph.py` для tenant assignment hook.
- Admin UI tab для comparison dashboard.

### Closure
- Verification sweep per task.
- Per-task commit (или arc-level как batch G/H).
- Archive specs после commit.
- CHANGELOG Arc 7 Batch I section.

## Acceptance
- `pytest tests/ -q` — 426 → ~455+ passing (33+ new tests).
- `ruff check .` — clean.
- Все feature flags default off → existing flow не меняется (sanity).
- Admin UI comparison tab renders.
- `scripts/generate_recommendations.py` создаёт report для мин. 1 week window.
- Working tree clean.

## Workflow rules
- По паттерну batch G/H: verification sweep сам, gap → fix-spec, автономная работа.
- Migrations downgrade обязательно работают.
- Feature flags default OFF — ломать текущий flow нельзя.

## Out of scope для Batch I
- Multi-tenant UI portal — остаётся admin-only.
- Cross-tenant experiment rollout — каждый tenant независим.
- Learned model for recommendations — только rule-based aggregation, без ML.
- Tool-use experiments (отдельно в batch K).

## How to start
1. `codex-tasks/Archive/meta-arc-7-batch-h-gracekelly-mistral.md` + `-g-provider-abstraction.md` — образцы meta.
2. `codex-tasks/verification-report-batch-h.md` — образец report.
3. `agent/prompt_registry.py` — существующий ContextVar паттерн для experiment (reuse для tenant assignment).
4. `db/models.py` + `alembic/versions/012_review_queue.py` — образец migration.
5. `scripts/weekly_report.py` + `scripts/generate_improvement_backlog.py` — образцы scheduled-aggregate scripts.

## Risks
- **Low traffic**: sticky exposure на single-user = noisy signal. Включение только после появления traffic.
- **Migration 017 если добавляем status в curated_cases**: текущая структура — JSONL файл, не DB. Решить: либо DB migration + JSONL compat layer, либо dataset остаётся JSONL и freshness metadata в отдельной таблице (`curated_case_status`). Предпочтительно второе (less disruption).
- **Rollback notification spam**: debounce на flappy experiments (минимум 6 часов между rollback events per experiment).
- **Recommendation engine accuracy**: на малых выборках — rule-based без ML, simple thresholds.

---

**Если meta достаточно для автономной работы — начинай. Critical gap — один вопрос и продолжай.**

# Task 155 — Automatic rollback on regression / evaluator drift

## Goal
Автоматически откатывать deployed experiments при заметной деградации quality/factuality/refusal signals, но держать механизм выключенным по умолчанию.

## Context
- Есть `trace_evaluations`, online evaluator snapshotting, regression runs и email infra (`scripts/weekly_report.send_email`).
- После task-153 deployment history становится persisted и пригоден для rollback.

## Deliverables
1. `config/settings.py`:
   - `auto_rollback_enabled: bool = False`
   - `rollback_drift_threshold_pct: float = 10.0`
   - `rollback_trace_window: int = 1000`
2. Rollback detector:
   - сравнивает recent experiment-exposed traces с baseline traces по mean online evaluator scores
   - триггерит rollback при drift выше threshold
   - не даёт repeated rollback spam для уже rolled-back deployment
3. Notification:
   - email на `TENANT_ADMIN_EMAIL`
   - текст содержит experiment id, drift reason и время rollback
4. Prometheus:
   - `experiment_auto_rollback_total{experiment_id,reason}`
5. После rollback assignment/runtime больше не выбирают этот experiment.
6. Tests — 6+:
   - drift over threshold triggers rollback
   - normal variance does not trigger
   - notification sent
   - Prometheus metric increments
   - already rolled-back deployment ignored
   - feature flag off disables watcher

## Acceptance
- При включённом флаге деградировавший deployed experiment получает `rolled_back_at`.
- Email и metric фиксируются один раз на событие rollback.
- При `AUTO_ROLLBACK_ENABLED=false` hot path/scheduled checks ничего не меняют.

## Notes
- Допустим hot-path watcher после persistence evaluators; отдельный cron script не обязателен.
- Baseline для сравнения — traces без experiment exposure или traces текущего baseline deployment.

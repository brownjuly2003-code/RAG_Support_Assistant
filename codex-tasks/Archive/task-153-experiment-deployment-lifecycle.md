# Task 153 — Experiment deployment lifecycle

## Goal
Убрать ручной deploy/rollback для experiments и перевести lifecycle в persisted state с валидируемыми переходами.

## Context
- В проекте уже есть `evaluation/experiments/*.yaml`, `CURRENT_EXPERIMENT`, regression runner и admin list/detail endpoints.
- Сейчас deploy делается только через `scripts/experiment_apply.py`, без audit-friendly deployment history.

## Deliverables
1. Migration `015` с таблицей `experiment_deployments`:
   - `id`
   - `experiment_id`
   - `staged_at`
   - `deployed_at`
   - `rolled_back_at`
   - `regression_run_id`
   - индексы по `experiment_id`, `deployed_at`, `rolled_back_at`
2. Admin endpoints:
   - `POST /admin/experiments/{id}/deploy`
   - `POST /admin/experiments/{id}/rollback`
3. State rules:
   - deploy разрешён только после последнего зелёного regression run по curated dataset.
   - rollback разрешён только для активного deployed experiment.
   - deployment history не теряется при повторном deploy того же experiment.
4. YAML status transitions:
   - `draft|running|completed -> deployed`
   - `deployed -> completed` при rollback
5. Admin list/detail payload содержит актуальное deployment summary.
6. Tests — 6+:
   - migration upgrade/downgrade
   - deploy success
   - deploy blocked without green regression
   - rollback success
   - invalid rollback blocked
   - detail/list serializes deployment state

## Acceptance
- `POST /api/admin/experiments/{id}/deploy` без regression PASS возвращает `409`.
- После deploy эксперимент получает `status=deployed`, deployment row имеет `deployed_at`.
- После rollback deployment row имеет `rolled_back_at`, active deploy больше не считается live.

## Notes
- Manual `experiment_apply.py` может остаться как fallback, но lifecycle source of truth должен быть в admin/API слое.
- Не ломать текущий stage override path через `EXPERIMENT_ID`.

# Task 154 — Tenant experiment assignment + sticky exposure

## Goal
Добавить tenant-level rollout experiments с sticky exposure по stable hash(user/session), не ломая default flow.

## Context
- `agent/graph.py` уже принимает `tenant_id`; `ConversationSession.ask()` знает `user_id` и `session_id`.
- Multi-tenant propagation по trace/vector/API уже есть.

## Deliverables
1. Migration `016` с таблицей `experiment_assignments`:
   - `id`
   - `tenant_id`
   - `experiment_id`
   - `rolled_out_at`
   - `rollout_percentage`
   - unique constraint на `(tenant_id, experiment_id)`
2. `config/settings.py`:
   - `experiment_assignment_enabled: bool = False`
3. `agent/graph.py`:
   - на входе пайплайна определяет active experiment assignment по tenant.
   - использует stable hash от `user_id` или `session_id`.
   - при match загружает experiment в `CURRENT_EXPERIMENT`.
   - при flag off поведение не меняется.
4. Admin endpoint `GET/POST /admin/experiments/{id}/assignments`:
   - list assignments
   - create/update rollout percentage per tenant
5. Trace attribution сохраняет active `experiment_id`, чтобы downstream rollback/dashboard могли работать по live traces.
6. Tests — 6+:
   - migration upgrade/downgrade
   - sticky across repeated requests
   - percentage rollout deterministic
   - flag off skips assignment
   - endpoint create/list
   - rolled-back / inactive experiments are ignored

## Acceptance
- Один и тот же `tenant_id + user_id` стабильно попадает либо всегда в experiment, либо всегда вне него.
- `EXPERIMENT_ASSIGNMENT_ENABLED=false` оставляет pipeline без experiment override.
- Admin endpoint сохраняет rollout percentage в диапазоне `0..100`.

## Notes
- Для текущего low-traffic режима feature flag должен оставаться OFF by default.
- Нужен только single active assignment per tenant-experiment pair; multi-arm bandit не входит в scope.

# Verification report — Arc 7 / Batch I (partial — tasks 153/154/156 admin + migrations)

## Summary
- **3 migrations added**: `015_experiment_deployments.py`, `016_experiment_assignments.py`, `017_curated_case_status.py` — all with matching `upgrade()`/`downgrade()` and explicit index creation.
- **5 admin endpoints added** in `api/app.py`:
  - `POST /admin/experiments/{id}/deploy` (task-153)
  - `POST /admin/experiments/{id}/rollback` (task-153)
  - `POST /admin/experiments/{id}/assignments` (task-154 admin)
  - `GET /admin/experiments/{id}/assignments` (task-154 admin)
  - `GET /admin/curated-dataset/stale` (task-156 read-side)
- **`resolve_active_experiment()` hook** added to `agent/prompt_registry.py` (placeholder returning `None`); `run_qa_pipeline` in `agent/graph.py` now consults it with `{tenant_id, user_id, session_id}` before falling back to the staged-experiment loader.
- **Batch I + K combined sweep**: 87 passed / 0 failed / 0 errors in 17s.
- **Wider sanity sweep** (graph / tenant / pipeline / experiment / prompt-registry): 57 passed.
- **Ruff**: clean (removed one unused `import api.app as api_app` in the Batch I WIP test).

## Scope verification (per task)

### task-153 — Experiment deployment lifecycle — PASS (admin layer)
- Migration 015 creates `experiment_deployments` with indexes on `experiment_id`, `deployed_at`, `rolled_back_at`.
- Deploy endpoint refuses without a green regression run (`drift_alert = false`) on the curated dataset — returns `409 regression`.
- Successful deploy inserts a new deployment row, updates the experiment YAML status to `deployed`, writes `config/deployed_experiment.yaml` with `{experiment_id: …}`.
- Rollback endpoint requires an active (non-rolled-back) deployment — marks `rolled_back_at`, resets YAML status to `completed`, removes the runtime file.
- Tests: `test_experiment_deployments_migration_upgrade_creates_table_and_indexes`,
  `test_experiment_deployments_migration_downgrade_drops_table_and_indexes`,
  `test_admin_experiment_deploy_blocks_without_green_regression`,
  `test_admin_experiment_deploy_updates_status_and_writes_runtime_file`,
  `test_admin_experiment_rollback_marks_deployment_and_clears_runtime_file`.

### task-154 — Tenant experiment assignment (admin surface only) — PASS
- Migration 016 creates `experiment_assignments` with indexes on `tenant_id` and `experiment_id`.
- Upsert endpoint deletes previous assignment for the tenant and inserts a new `{tenant_id, experiment_id, rollout_percentage, rolled_out_at}` row.
- List endpoint returns the tenant assignments for the experiment.
- `run_qa_pipeline(question, retriever, llm, tenant_id, user_id, session_id)` now consults `resolve_active_experiment()` before the staged-experiment loader, so monkeypatched resolvers flow through to `agent.prompts.build_qa_prompt()` via `CURRENT_EXPERIMENT`.
- Tests: `test_admin_experiment_assignments_upsert_and_list`,
  `test_graph_uses_assigned_experiment_when_resolver_returns_one`.

### task-156 — Curated dataset freshness (read side only) — PASS
- Migration 017 creates `curated_case_status` with indexes on `tenant_id` and `status`.
- Stale listing endpoint returns cases with `status='stale_needs_review'`, tenant-scoped when the admin token carries a tenant.
- Tests: `test_curated_case_status_migration_upgrade_creates_table_and_indexes`,
  `test_admin_curated_dataset_stale_lists_stale_cases`.

## Deferred for a follow-up Batch I closure
- **task-154 sticky rollout** — `resolve_active_experiment()` currently returns `None`; hash-based rollout lookup against `experiment_assignments` with the `EXPERIMENT_ASSIGNMENT_ENABLED` flag and sticky exposure semantics is still open.
- **task-155 automatic rollback** — watcher on evaluator drift, `AUTO_ROLLBACK_ENABLED=false` default, `experiment_auto_rollback_total{experiment_id,reason}` metric, `TENANT_ADMIN_EMAIL` notification channel.
- **task-156 staleness detection** — cronjob that actually populates `curated_case_status` rows by re-running curated cases through the primary profile and comparing verdicts.
- **task-157 recommendation engine** — `scripts/generate_recommendations.py` weekly report aggregating review queue + evaluator trends + threshold analyzer + regression results into `reports/recommendations/<week>.md`, plus `/admin/recommendations/current` endpoint.
- **task-158 experiment comparison dashboard** — `/admin/experiments/comparison` endpoint and admin UI tab rendering deployed vs staged vs candidate metrics.

The pending task specs (task-155, 157, 158, plus `meta-arc-7-batch-j-backup-restore-chaos.md`)
stay in `codex-tasks/` root awaiting pickup.

## Acceptance (per meta-spec)
- Targeted Batch I sweep — PASS (28/28).
- Combined Batch I + K sweep — PASS (87/87).
- Wider sanity sweep — PASS (57/57).
- Ruff — PASS.
- Feature-flag behaviour — PASS (no Batch I flags toggled by default; new endpoints are admin-only).
- Working tree clean post-commit — PASS.

# Verification report — Arc 8 Batch L (operational close-out)

Tasks: 171, 172, 173, 174.
Code landed in commit `8043440` on top of `d163942`.

## task-171 — Alembic migration round-trip audit + CI job

### Acceptance criteria
- [x] `scripts/migration_round_trip.py` CLI with args `--database-url`, `--verbose`, exit-code contract 0/1/2/3/4. Dummy `DB_ENCRYPTION_KEY` supplied when env var is unset to keep local runs turn-key.
- [x] Disposable Postgres run: `python scripts/migration_round_trip.py --database-url postgresql://rag:rag_dev_password@localhost:55433/rag_assistant` against `postgres:16-alpine` → exit 0; logs show 17 upgrades, 17 downgrades, 17 re-upgrades.
- [x] Table set check: 17 domain tables + `alembic_version` (18 total). Accounts for 5 migration-only tables not present in `db.models.Base.metadata` (gap documented in-script).
- [x] `pytest tests/test_migration_round_trip.py -q` — 2 passed.
- [x] `ruff check scripts/ tests/` — clean.
- [x] Unit suite (`tests/ --ignore=integration --ignore=a11y -p no:schemathesis`) — 511 passed, 1 skipped, 0 failed.
- [x] CI `migrations` job added to `.github/workflows/ci.yml` with `postgres:16-alpine` service and the same command; gated to `pull_request` and `push` to `master`.
- [x] No additional broken migrations beyond the already-fixed 012.

### Notes
- `docs/CHANGELOG.md` gained an entry covering the 012 fix and the round-trip gate.
- `scripts/restore_verify*.py` received `# noqa: E402` annotations to keep `ruff check` green under the project's existing import-order conventions.

## task-172 — Helm chart lint & server-side dry-run

### Acceptance criteria
- [x] `helm lint deploy/helm/ --strict` — 0 failed.
- [x] `helm template deploy/helm/ --values deploy/helm/values.yaml` → `kubectl apply --dry-run=client` — clean across 17 rendered objects.
- [x] CI `helm` job added: `azure/setup-helm@v4`, `helm lint --strict`, `helm template`, and `kubectl apply --dry-run=client` via a throwaway `kind` cluster (client-side discovery would otherwise refuse without an API server).
- [x] Deterministic `helm template` output (two consecutive runs MATCH).
- [x] Every Deployment and CronJob container now carries `resources.requests/limits` (`deployment.yaml:36`, `deployment-email-poller.yaml:37`, all cronjob templates).
- [x] `cronjob-backup-snapshot.yaml:18` and `cronjob.yaml:16` gained explicit `backoffLimit: 6`.
- [x] Standard `app.kubernetes.io/*` and `helm.sh/chart` labels propagated to every template.
- [x] `Chart.yaml:6` gained `icon`; no behavioural changes to schedule/env/volumes.
- [x] `deploy/helm/values.yaml` untouched — existing defaults already cover every `.Values.*` ref.
- [x] `docs/operations/helm-lint.md` documents the local flow and expected output.

### Notes
- Codex performed the lint/template/dry-run on Ubuntu; local Windows environment lacks `helm`, so these acceptance steps are covered by Codex's run plus the new CI gate.
- `pytest tests/test_helm_cronjobs.py -q` — 4 passed on the post-task tree, confirming the YAML surface stayed parseable.

## task-173 — docker-compose.test.yml + full restore verification

### Acceptance criteria
- [x] `docker-compose.test.yml` provisions `postgres-test` (`postgres:16-alpine`, ephemeral, auto-assigned host port, `pg_isready` healthcheck, network `rag-restore-test`).
- [x] `scripts/restore_verify.py` learns `--postgres-url`: invokes `pg_restore --dbname=<url> --clean --if-exists`, cross-checks `alembic_version.version_num` against manifest, verifies the `information_schema.tables` set, new `EXIT_POSTGRES_VERIFY_FAILED=4`.
- [x] Backward-compat: running without `--postgres-url` preserves the prior SQLite-only + tarball-smoke path.
- [x] `scripts/restore_verify_integration.py` orchestrates `compose up -d` → wait-for-ready → port resolution → `restore_verify.main` → `compose down -v` in a `finally`; cleanup failure folds into `EXIT_INFRA_ERROR` when the inner run had otherwise succeeded.
- [x] `tests/test_restore_verify_postgres.py` — 1 passed, 1 skipped (skips cleanly without docker/pg_restore on PATH, as designed).
- [x] `scripts/restore_verify.py` legacy surface: 15 passed on `tests/test_restore_verify.py`.
- [x] `ruff check scripts/ tests/` — clean.
- [x] `docs/operations/backup-restore.md` gained a "Full-restore verification" section; `docs/CHANGELOG.md` entry added.

### Notes
- Live `backup_snapshot → restore_verify_integration → exit 0` end-to-end was not replayed in this verification pass because it requires an existing backup snapshot; all in-script contracts are exercised by the unit/integration tests.

## task-174 — GraceKelly runtime smoke harness

### Acceptance criteria
- [x] `scripts/gracekelly_smoke.py` CLI with the 8-step chain: readiness → active profile → `/api/ask` provider assertion → tool-loop trace → schema dispatch → SSE streaming → Prometheus cost → failover via `--simulate-down`.
- [x] Steps that cannot be proven without a live GraceKelly + RAG stack are emitted as `SKIPPED`, not `FAILED`, to keep the exit code honest.
- [x] Windows console output patched to force UTF-8 so ✓/✗ glyphs do not raise `UnicodeEncodeError`.
- [x] `ruff check scripts/gracekelly_smoke.py` — clean; `python -m py_compile scripts/gracekelly_smoke.py` — ok.
- [x] Fail-fast path confirmed: `python scripts/gracekelly_smoke.py --verbose` with nothing listening on 8011 exits 1 with `GraceKelly not reachable at http://127.0.0.1:8011, start D:\GraceKelly\ first`.
- [x] Related integration surface (`tests/test_post_deploy_smoke.py tests/integration/test_streaming.py`) — 7 passed, 1 warning.
- [x] `docs/operations/gracekelly-smoke.md` is the runbook (preconditions, auth/env notes, healthy-path + failover-only, example output, troubleshooting).
- [x] `docs/CHANGELOG.md:253` entry added.

### Notes
- Full live e2e (exit 0 with real GraceKelly on 8011 + RAG on 8000) is explicitly deferred — both services must be up; not blocking closure per task spec.

## Summary

Commit `8043440` closes 4 Arc 7 Known Gaps and introduces two new CI gates (`migrations`, `helm`) plus one manual runbook (`gracekelly-smoke`). No behavioural regressions in existing test surface: `ruff` clean, 511 passed / 1 skipped locally, 531 / 1 on the Codex-side sweep.

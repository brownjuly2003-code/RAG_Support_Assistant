# Verification report — Arc 7 / Batch J (backup / restore / chaos)

## Summary
- **Batch J closed.** All 6 tasks (159-164) land with dedicated scripts + tests.
- **Targeted sweep** (6 files): 37 passed / 0 failed.
- **Combined K + I + J + sanity sweep** (26 files): 167 passed.
- **Ruff**: clean.

## Scope verification (per task)

### task-159 — Snapshot backup — PASS
- `scripts/backup_snapshot.py` writes atomic snapshot: optional `pg_dump`, SQLite backup API, tarballs for `chroma` + `uploads`, SHA256 fingerprint of `DB_ENCRYPTION_KEY` (raw key never written), and `snapshot_manifest.json` with per-component `sha256`, `size_bytes`, plus host + alembic revision.
- `--skip-chroma` flag toggles the Chroma tarball; missing sources (no SQLite, no uploads, no Postgres URL) are reported as `skipped`, not failures. `BACKUP_DIR`, `BACKUP_RETENTION_DAYS` landed in settings.
- Tests cover: valid manifest + hashes, `--skip-chroma`, total size aggregation, idempotent re-run, all-missing projects, key fingerprint never leaks raw key, CLI entry-point.

### task-160 — Disposable restore verification — PASS
- `scripts/restore_verify.py` stages a snapshot into a temp root (auto-cleaned on success/failure), runs SQLite `PRAGMA integrity_check`, unpacks tarballs, and checks the resulting layout. Exit codes: `EXIT_OK=0`, `EXIT_RESTORE_FAILED=1`, `EXIT_SMOKE_FAILED=2`, `EXIT_INFRA_ERROR=3`.
- Tests cover: happy path exits 0, missing manifest fails cleanly, corrupted tarball fails tar-extract with a readable detail, render-report formatting, CLI `--report` output.

### task-161 — Chaos drills — PASS
- `scripts/chaos_drill.py` implements six faults via targeted context managers: `ollama_timeout`, `ollama_down`, `postgres_unavailable`, `redis_unavailable`, `network_slow`, `network_flaky`. Acceptance rules encoded per fault; flaky uses a seeded RNG so tests are deterministic.
- Tests cover: every fault (six), unsupported fault raises, CLI + markdown render.

### task-162 — Post-deploy smoke suite — PASS
- `scripts/post_deploy_smoke.py` runs five checks: `liveness`, `readiness`, `metrics` (Prometheus body must contain `rag_model_routing`, `rag_llm_cost_usd_total`, `rag_experiment_auto_rollback_total`), `ask` (payload must contain `answer` + `trace_id`), `admin_providers` (must include `ollama`). Uses an injected `httpx.Client` for test isolation.
- Tests cover: all-pass path, liveness/readiness failure, metrics missing required keys, ask missing `trace_id`, admin_providers missing `ollama`, markdown renderer.

### task-163 — Backup integrity / retention — PASS
- `scripts/backup_integrity.py` walks the backup directory, verifies each component against `snapshot_manifest.json` (size + SHA256), flags snapshots older than the retention window as deletion candidates, emits an audit report with valid/corrupted/expired counters.
- Never deletes; only reports. Tests cover: valid snapshot, corrupted SHA detected, missing manifest detected, expired candidate flagged, multi-snapshot audit, markdown with counters, CLI `--report`.

### task-164 — Disaster recovery checklist — PASS
- `docs/disaster-recovery.md` ships scenarios A-E with RTO/RPO, procedures, verification steps, and mapping to the Batch J scripts. Explicitly documents that Scenario E (lost `DB_ENCRYPTION_KEY`) is irrecoverable and suggests dual-vault key management as mitigation.
- Tests cover: all five scenarios present, all five Batch J script paths referenced, RTO/RPO table formatted.

## Acceptance (per meta-spec)
- Targeted Batch J sweep — PASS (37/37).
- Combined K + I + J + sanity sweep — PASS (167/167).
- Ruff — PASS.
- Working tree clean post-commit — PASS.
- Feature-flag surface unchanged (Batch J adds no runtime toggles that alter existing behaviour).

## Pending / out of scope
- Helm `CronJob` manifests for backup/integrity/restore_verify schedules — runbook-only in this batch.
- Real docker-compose.test.yml for disposable Postgres inside `restore_verify.py` — current implementation uses a layout smoke (SQLite + tarball extraction) which is sufficient to catch corrupted snapshots without Docker.
- Automated encryption-at-rest of snapshot tarballs — documented in DR checklist, not automated.
- CI wiring of `post_deploy_smoke.py` — left as a deploy-time hook, not part of the pytest CI job.
- task-154 sticky rollout inside `resolve_active_experiment()` and the task-156 staleness detection cronjob remain open from Batch I.

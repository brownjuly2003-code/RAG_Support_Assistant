# Disaster recovery checklist

Scope: single-host local deploy of `RAG_Support_Assistant`. Aligns with
`docs/operations/backup-restore.md` (existing runbook) and the Batch J
automation (`scripts/backup_snapshot.py`, `scripts/restore_verify.py`,
`scripts/post_deploy_smoke.py`, `scripts/backup_integrity.py`).

All scripts are Python and cross-platform; Windows-specific gotchas are
called out where relevant.

## Summary of RTO/RPO

| Scenario | Description | RPO | RTO | Recoverable? |
|---|---|---:|---:|---|
| A | `data/` fully lost | 24h | 45min | Yes |
| B | Postgres corrupted | 24h | 30min | Yes |
| C | Ollama models lost | 0 | 2h | Yes (re-download) |
| D | Full host compromise | 24h | 1 day | Yes |
| E | `DB_ENCRYPTION_KEY` lost | — | — | **No** (irrecoverable) |

Targets assume the nightly backup job (`scripts/backup_snapshot.py`) has
been running and a successful weekly `scripts/restore_verify.py` is on
file. Without a recent verified snapshot, RTO doubles and RPO degrades.

## Scenario A — `data/` fully lost (disk failure or accidental `rm -rf data/`)

**RPO:** 24h (nightly snapshot). **RTO:** 45min.

### Required inputs
- Latest verified snapshot (`scripts/backup_integrity.py` reports `Valid`).
- `DB_ENCRYPTION_KEY` from offline vault (not in the snapshot itself; only
  the SHA256 fingerprint is stored there).
- Matching `alembic_revision` in `snapshot_manifest.json`.

### Procedure
1. Stop the app (`docker compose stop app` or kill the uvicorn process).
2. Verify snapshot health before restoring:
   `python scripts/backup_integrity.py --backup-dir <backup-root> --report tmp/integrity.md`.
3. Stage the snapshot:
   `python scripts/restore_verify.py --snapshot <backup-root>/<snap-id>/ --report tmp/restore.md`
   (this exits non-zero if extraction / SQLite integrity fails).
4. Apply the snapshot over `data/`:
   - Copy `sqlite/traces.db` → `data/tracing/traces.db`.
   - Extract `uploads/uploads.tar.gz` into `data/`.
   - Extract `chromadb/chroma.tar.gz` into `data/vectordb/`.
5. `alembic upgrade head` to ensure schema matches code.
6. Start the app and run
   `python scripts/post_deploy_smoke.py --base-url http://localhost:8000 --token <admin>`.
   Expect exit code 0.

### Verification
- `/healthz/ready` returns 200.
- `/metrics` contains `rag_model_routing`, `rag_llm_cost_usd_total`,
  `rag_experiment_auto_rollback_total`.
- `POST /api/ask` returns `answer` + `trace_id`.
- `/admin/providers` lists at minimum `ollama`.

## Scenario B — Postgres corrupted

**RPO:** 24h. **RTO:** 30min.

### Required inputs
- Latest `postgres.dump` from the snapshot directory (or offsite copy).
- `DB_ENCRYPTION_KEY`.

### Procedure
1. Stop the app.
2. `pg_restore --clean --if-exists --no-owner --no-privileges "$DATABASE_URL" < postgres.dump`.
3. `alembic upgrade head`.
4. Start the app and run `scripts/post_deploy_smoke.py`.

### Verification
- `psql` reports the expected row counts in `messages`, `traces`,
  `eval_results`.
- `pgcrypto` extension present
  (`SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'`).

## Scenario C — Ollama models lost (model directory wiped)

**RPO:** 0 (models are derivable). **RTO:** 2h.

### Required inputs
- Internet access and the Ollama daemon.
- List of model names used by the project (check `OLLAMA_MODEL_NAME` in
  `config/settings.py` and deployed experiment YAMLs for overrides).

### Procedure
1. Run `ollama pull <model>` for each model the deployment uses.
2. Restart the app.
3. Run `scripts/post_deploy_smoke.py` — the `ask` check exercises the
   live LLM call and surfaces missing models fast.

### Verification
- `ollama list` shows required models.
- `POST /api/ask` succeeds end-to-end.

## Scenario D — Full host compromise

**RPO:** 24h. **RTO:** 1 day.

### Required inputs
- Fresh host.
- All required secrets (`DB_ENCRYPTION_KEY`, `POSTGRES_*`, `MISTRAL_API_KEY`,
  bearer admin token) from offline vault.
- Latest verified snapshot on a separate medium (USB, external drive,
  offsite).

### Procedure
1. Provision the new host (OS, Python, Docker Desktop on Windows / Docker
   Engine on Linux, Ollama).
2. Clone the repo at the same commit as the snapshot's
   `alembic_revision`.
3. Re-install dependencies: `pip install -r requirements.txt`.
4. Inject secrets into `.env` from offline vault; do **not** paste secrets
   into chat history or logs.
5. Start Postgres and Redis (via `docker compose up -d postgres redis`).
6. Follow Scenario A end-to-end to stage the snapshot.
7. `ollama pull` required models (Scenario C).
8. Start the app and run `scripts/post_deploy_smoke.py`.
9. Review the last 7 days of traces for anomalies before resuming
   regular traffic.

### Verification
- All smoke checks pass.
- `scripts/backup_integrity.py` on the original backup directory still
  reports `Valid`.
- `/admin/providers` matches expected providers for the deployment
  profile.

## Scenario E — `DB_ENCRYPTION_KEY` lost

**RPO:** — (encrypted columns are unrecoverable). **RTO:** — (irrecoverable).

### Reality check
Without the key, `messages.content`, `audit_log.detail`,
`escalated_tickets.user_question` / `ai_draft` / `operator_response`
cannot be decrypted. Restoring a Postgres dump without the key only
recovers ciphertext.

### Mitigations (apply before the key is lost)
- Store `DB_ENCRYPTION_KEY` in two separate vaults: online
  (Vault/1Password) and offline (sealed envelope, safe).
- Include the SHA256 fingerprint in `snapshot_manifest.json` under
  `encryption_key_fingerprint` so you can verify a restored key matches
  the key that encrypted the snapshot.
- Document dual-control access: key release requires two authorised
  humans.
- Consider `age` / `gpg` encryption of snapshot tarballs at rest so
  even if the snapshot medium leaks, ciphertext remains protected.

### If the key is already lost
1. Stop the app.
2. Generate a new `DB_ENCRYPTION_KEY`, store in both vaults.
3. Delete rows whose columns are `NOT NULL` and encrypted (see
   `docs/operations/backup-restore.md` §2.4).
4. Notify tenants/compliance that history before the loss is gone.
5. Resume with the new key; new writes will be protected by it.

## Backups + offsite recommendation

- Keep the last 7 daily snapshots locally on a separate disk from the
  app's data volume.
- Replicate to external cold storage (portable disk or `rclone` to a
  personal cloud) at least weekly.
- Run `scripts/backup_integrity.py` in a Sunday cronjob and alert on
  any `Corrupted`/`missing manifest` status.
- Run `scripts/restore_verify.py` against the newest snapshot in a
  Sunday cronjob; alert if it exits non-zero.

## Scripts quick reference

- Backup (nightly):
  `python scripts/backup_snapshot.py --out backups/$(date -u +%Y%m%dT%H%M%S)Z/`
- Integrity audit (weekly Sun 05:00 UTC):
  `python scripts/backup_integrity.py --backup-dir backups/ --report reports/backup-integrity.md`
- Restore verification (weekly Sun 04:00 UTC):
  `python scripts/restore_verify.py --snapshot backups/<latest>/ --report reports/restore-verify.md`
- Smoke suite (post-deploy / post-restore):
  `python scripts/post_deploy_smoke.py --base-url http://localhost:8000 --token <admin>`
- Chaos drill (manual only):
  `python scripts/chaos_drill.py --fault ollama_timeout --iterations 5 --report reports/chaos-ollama.md`

## Known limitations

- `scripts/chaos_drill.py` is a unit-level fault injection, not a real
  network drill. It does not exercise firewalls/iptables.
- Windows `pg_dump` may need the Postgres `bin` directory on `PATH` or
  an explicit `PG_DUMP_PATH` env.
- ChromaDB tarball is taken while the app is running; for large indexes
  you may want to stop the app briefly or use Chroma's snapshot API.
- Backup encryption-at-rest is documented, not automated.
- Helm manifests in `deploy/helm/` are still incomplete for production
  PVC + Secret wiring; real k8s DR still relies on the manual runbook.

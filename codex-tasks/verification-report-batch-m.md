# Verification report — Arc 8 Batch M (backup encryption at rest)

Task: 175. Code landed in the commit just above this archive commit, on
top of `76b8cdb` (the spec-queue commit).

## task-175 — Backup encryption at rest via age

### Acceptance criteria
- [x] `scripts/backup_snapshot.py` gains `BACKUP_ENCRYPTION_ENABLED` + recipient / passphrase env vars and produces `*.age` per component when enabled; plaintext originals are removed; `snapshot_manifest.json` records `encryption.recipient_fingerprint` (SHA256 of the public key, not the key) plus per-component `encrypted` + `algorithm`.
- [x] `scripts/restore_verify.py --age-identity-file` (X25519) and `--age-passphrase-file` (symmetric) decrypt encrypted snapshots in the disposable temp root before the pre-existing restore path runs.
- [x] New `EXIT_DECRYPT_FAILED=5` wired at four call sites; previously used exit codes (0/1/2/3/4) unchanged.
- [x] Backward-compat: running `scripts/backup_snapshot.py` without the toggle preserves the old plaintext path — `tests/test_backup_snapshot.py` + `tests/test_restore_verify.py` green on the modified tree.
- [x] `scripts/backup_integrity.py` surfaces `encrypted` in its report and SHA-hashes the on-disk payload (the `*.age` file) for encrypted snapshots.
- [x] `scripts/restore_verify_integration.py` propagates the new flags so the docker-compose wrapper keeps working against encrypted snapshots.
- [x] `deploy/helm/templates/cronjob-backup-snapshot.yaml` conditionally mounts `/secrets/recipient.pub` from Secret `backup-encryption-key` gated on `.Values.backup.encryption.enabled`.
- [x] `deploy/helm/values.yaml` defaults the toggle to off (fail-safe).
- [x] `helm lint --strict` clean (Codex-side).
- [x] `helm template` on `backup.encryption.enabled=true` adds the mount; on `false` leaves the CronJob unchanged — verified by Codex.
- [x] `docs/operations/backup-encryption.md` is the runbook (age-keygen flow, Helm Secret wiring, rotation caveat).
- [x] `docs/disaster-recovery.md` gains Scenario F (backup tarball leaked vs age private key lost); `docs/CHANGELOG.md` entry added.
- [x] `tests/test_backup_snapshot_encryption.py` + `tests/test_restore_verify_encryption.py` skip cleanly when `age` is not on PATH.
- [x] `ruff check scripts/ tests/ deploy/` → clean.

### Test results
- Codex-side sweep on an `age`-equipped runner: 30 passed, 0 skipped.
- Local sweep on this Windows host (no `age`): 27 passed, 3 skipped — the 3 skipped tests are exactly the `age`-gated ones in the two new encryption test modules. Skip-guard behaves as designed.

### Notes
- `BACKUP_ENCRYPTION_ENABLED=false` is the shipped default; upgrading without age install is a no-op.
- Rotation is documented as a manual runbook; automation deferred.
- Scenario F formalises the new failure mode: losing the age private key makes snapshots irrecoverable. Keep the private key in the same offline vault as `DB_ENCRYPTION_KEY` — both loss modes remain independent.

## Summary

Batch M closes the last operational Known Gap called out in the Batch L close-out report. The gap surface now covers: migrations (CI), helm (CI), restore (integration wrapper + real Postgres), backup encryption (age + Secret wiring). Remaining candidates for Arc 8 Batch N: GraceKelly full-RAG-stack e2e (blocked on Ollama-GB cost in CI), Mistral regression benchmark (ready to run when tenant opts in).

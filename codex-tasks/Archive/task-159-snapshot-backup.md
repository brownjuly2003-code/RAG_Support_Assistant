# Task 159 — Snapshot backup

## Closed
- `scripts/backup_snapshot.py` — atomic snapshot CLI for Postgres
  (optional `pg_dump`), SQLite traces (backup API), ChromaDB + uploads
  tarballs, DB_ENCRYPTION_KEY SHA256 fingerprint, and
  `snapshot_manifest.json` with alembic revision + per-component
  `sha256`/`size_bytes`.
- `--skip-chroma` toggle and missing-source-is-`skipped` behaviour.
- Settings: `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`.

## Verified by
- `tests/test_backup_snapshot.py`

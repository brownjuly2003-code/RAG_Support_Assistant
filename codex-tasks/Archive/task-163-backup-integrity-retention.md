# Task 163 — Backup integrity and retention

## Closed
- `scripts/backup_integrity.py` — walks a backup directory, verifies
  every component against `snapshot_manifest.json` (size + SHA256),
  flags snapshots past `BACKUP_RETENTION_DAYS` as deletion candidates,
  emits a markdown audit report.
- Never deletes; expired snapshots only appear in a "Recommended
  deletions" section of the report.

## Verified by
- `tests/test_backup_integrity.py`

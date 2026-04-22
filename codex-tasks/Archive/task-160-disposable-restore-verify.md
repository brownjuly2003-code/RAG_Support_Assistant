# Task 160 — Disposable restore verification

## Closed
- `scripts/restore_verify.py` — stages a snapshot in a disposable temp
  root, runs `PRAGMA integrity_check` on the restored SQLite, unpacks
  tarballs, and verifies the layout.
- Structured exit codes (`EXIT_OK=0`, `EXIT_RESTORE_FAILED=1`,
  `EXIT_SMOKE_FAILED=2`, `EXIT_INFRA_ERROR=3`) and automatic cleanup of
  the temp root.

## Verified by
- `tests/test_restore_verify.py`

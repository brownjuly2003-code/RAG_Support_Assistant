# Task 164 — Disaster recovery checklist

## Closed
- `docs/disaster-recovery.md` — scenarios A-E (`data/` lost, Postgres
  corrupted, Ollama models lost, host compromise, `DB_ENCRYPTION_KEY`
  lost) with RTO/RPO table, step-by-step procedures, verification
  checks, Batch J script mapping.
- Explicitly documents the irrecoverable key case and dual-vault
  mitigation, Windows `pg_dump` caveat, and offsite-backup
  recommendation.

## Verified by
- `tests/test_dr_checklist.py`

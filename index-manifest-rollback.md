# Atomic Manifest Rollback (4.8d1)

## Goal

Add a lock-gated atomic manifest rollback primitive without opening or deleting
any Chroma collection.

## Tasks

- [x] Add red contracts for active/previous swap, generation increment, missing rollback target, lock ownership, and replace failure.
- [x] Implement the smallest manifest-only rollback API by reusing the existing atomic publisher.
- [x] Run focused manifest/runtime regressions, scoped Ruff/Mypy, and diff checks.
- [x] Commit with explicit pathspecs and record that retention/deletion remains open.

## Done When

- [x] A held matching tenant lock can atomically swap active and previous.
- [x] Missing manifest/previous state and stale or wrong-tenant tokens fail closed.
- [x] Failed replacement preserves the prior manifest byte-for-byte.
- [x] No real Chroma, PostgreSQL, collection deletion, push, or deploy occurs.

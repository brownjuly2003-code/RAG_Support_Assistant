# Validated Runtime Rollback (4.8d2)

## Goal

Validate the manifest previous collection under the tenant lock before an
atomic runtime rollback, without deleting any collection.

## Tasks

- [x] Add red contracts for validated rollback, cache generation, and fail-closed target errors.
- [x] Reuse count/dimension/known-query validation for an existing collection.
- [x] Add a manager rollback service that validates before manifest swap and cache update.
- [x] Run focused runtime/manifest regressions, scoped Ruff/Mypy, and diff checks.
- [x] Commit with explicit pathspecs and record retention/deletion as still open.

## Done When

- [x] Successful rollback opens and validates only manifest.previous before swapping.
- [x] Missing, empty, dimension-invalid, or known-query-invalid targets preserve manifest/cache.
- [x] Generation-aware cache points at the rolled-back collection after success.
- [x] No collection deletion, live Chroma/PostgreSQL, push, or deploy occurs.

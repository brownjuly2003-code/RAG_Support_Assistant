# VER-07 retention audit tenant contract

## Goal
Align the stale trace-purge audit assertion with the existing tenant-aware endpoint contract without changing runtime behavior.

## Tasks
- [x] Reproduce the exact stale assertion failure in `tests/test_trace_retention.py`.
- [x] Add the expected default `tenant_id` to the captured audit call.
- [x] Run the focused retention test plus adjacent tenant/audit verification.
- [x] Verify scoped diff, formatting, and protected-file hashes before commit.

## Done When
- [x] The previously failing trace-retention test passes and no runtime source file changes.

## Evidence
- Exact regression: 1 failed before the assertion update, then 1 passed.
- Adjacent retention/tenant/audit band: 22 passed.
- Ruff lint passed; file-wide formatter debt reproduces on clean `HEAD` and was not expanded.

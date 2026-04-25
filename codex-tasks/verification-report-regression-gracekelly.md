# Verification Report — Regression via GraceKelly Claude

Date: 2026-04-25
HEAD: `54c8660`

## Scope

- Dataset expanded/validated: `evaluation/curated_cases.jsonl`
- Wrapper added: `scripts/run_regression_via_gracekelly.ps1`
- Live regression attempted with:
  - baseline: `ministral-3b-latest`
  - candidate: `claude-sonnet-4-6-api`
  - profile: `gracekelly-primary`

## Dataset

Validated with `scripts.regression_eval.CuratedCase`.

Counts:
- warranty: 5
- returns: 5
- error: 7
- off-topic: 3
- total: 20

## Wrapper Checks

- `GraceKelly` unavailable guard verified: exits `1` with startup instructions.
- Disposable Postgres/Redis startup verified.
- Alembic requires a sync SQLAlchemy URL, so the wrapper uses `postgresql+psycopg2` only for migrations and restores `postgresql+asyncpg` for runtime.
- Migration `008_enable_pgcrypto` requires `DB_ENCRYPTION_KEY`; the wrapper generates a disposable process-only key for the disposable DB.
- Ingestion is scoped to the 3 seed KB docs: `warranty.md`, `returns_policy.md`, `errors_e10_e30.md`.

## Live Attempt

Debug run:

- command: `scripts/run_regression_via_gracekelly.ps1 -MaxCases 1`
- report JSON: `reports/regression/20260425T040428Z-ministral-3b-latest-vs-claude-sonnet-4-6-api.json`
- report MD: `reports/regression/20260425T040428Z-ministral-3b-latest-vs-claude-sonnet-4-6-api.md`

Aggregate:

- total cases: 1
- baseline pass rate: 100%
- candidate pass rate: 0%
- baseline total cost: `$0.000014`
- candidate total cost: `$0.000000`
- candidate refusal rate: 0%

Failure example:

- case: `warranty-receipt-storage`
- baseline answer: says the receipt must be kept for the 12-month warranty period.
- candidate answer: `[provider_unavailable] Anthropic API key is not configured.`
- candidate failures: missing `чек`, missing `12`

## Blockers

Full 20-case live run was not executed because the 1-case live run proves the acceptance preconditions are not currently met:

1. `claude-sonnet-4-6-api` resolves in GraceKelly to the Anthropic API adapter, and `/api/v1/readiness` reports `api.anthropic.configured=false`.
2. Direct GraceKelly smoke for `claude-sonnet-4-6-api` returns `[provider_unavailable] Anthropic API key is not configured.`
3. The asyncpg race from task-176 still reproduces: `trace_evaluations`/online evaluator logging warns with `InterfaceError`, and final `INSERT INTO eval_results` fails with `InterfaceError: another operation is in progress`.

Because of those blockers, a 20-case run would produce a known-invalid candidate signal and fail persistence after report generation.

## Verification Commands

- `ruff check scripts/ evaluation/` — passed.
- `pytest tests/ --ignore=tests/integration --ignore=tests/test_a11y.py -p no:schemathesis -q --tb=no` — did not collect tests because existing `tests/pytest-cache-files-*` directories return `PermissionError`.
- Retry with `--ignore-glob=tests/pytest-cache-files-*` reached tests but still failed with environment-level `PermissionError` across many tests: `267 passed / 3 skipped / 247 errors`.

# TraceService lifecycle owner

## Goal

Give trace start/log/finish lifecycle one injectable owner while preserving the
existing `tracing.sqlite_trace` API and PII-redaction behavior.

## Tasks

- [x] Add red contracts for lifecycle forwarding, redaction, and wrapper delegation → Verify: focused pytest fails before implementation.
- [x] Add `tracing.service.TraceService` → Verify: injected backend receives one start/log/finish call with unchanged arguments.
- [x] Route SQLite module-level lifecycle functions through one singleton → Verify: existing imports/signatures remain compatible.
- [x] Run focused trace/PII tests, Ruff, narrowed MyPy, diff, and LF checks.

## Done When

- [x] Trace lifecycle has one owner, old call sites remain unchanged, and all scoped verification is green.

## Notes

This slice does not move trace queries, retention, feedback, storage schema, or
graph orchestration, and makes no live-service or deployment change.

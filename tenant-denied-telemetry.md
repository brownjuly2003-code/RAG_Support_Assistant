# Tenant-denied access telemetry

## Goal

Expose confirmed cross-tenant ownership denials as one bounded Prometheus
counter and short-debounce security alert without changing opaque API responses or
performing additional foreign-tenant data reads.

## Tasks

- [x] Add red metric, ownership-boundary, fail-open, and alert contracts.
- [x] Record the four confirmed session mismatch branches exactly once.
- [x] Record the three ticket and three KB-draft mismatch branches exactly once.
- [x] Run focused tests, Ruff, scoped MyPy, formatter-diff, and diff/LF checks.

## Done When

- [x] Labels are limited to `session`, `ticket`, `kb_draft`, and `unknown`.
- [x] Missing resources and same-tenant access do not increment the counter.
- [x] Metric failures cannot change the existing opaque 404 behavior.
- [x] Any confirmed denial in five minutes triggers the warning contract.

## Notes

This local slice does not add tenant IDs or resource IDs to metrics, perform
unscoped existence probes, change authorization behavior, or provide live
scrape/alert-delivery evidence. Worker lease ownership is outside this HTTP
access signal.

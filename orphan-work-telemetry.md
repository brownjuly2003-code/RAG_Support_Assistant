# Orphan work telemetry

## Goal

Expose thread-pool work that continues after request timeout or disconnect as
one current-value Prometheus gauge with a stuck-orphan alert, without changing
capacity ownership or release semantics.

## Tasks

- [x] Add red gauge, lifecycle-boundary, fail-open, and alert contracts.
- [x] Increment once when capacity transfers to the future done-callback.
- [x] Decrement once when that future finishes and releases capacity.
- [x] Run focused tests, Ruff, scoped MyPy, formatter-diff, and diff/LF checks.

## Done When

- [x] Every shared `_hold_capacity_until_future_done` call is represented once.
- [x] Normal synchronous completion never claims orphan work.
- [x] Metric failures cannot prevent callback registration or capacity release.
- [x] A warning fires only when orphan work remains above zero for five minutes.

## Notes

This local slice does not change timeouts, executor size, cancellation policy,
or live monitoring. It does not close tenant-denied access, architecture,
dashboard, Astro 7, or live alert-delivery residuals.

# Escalation delivery telemetry

## Goal

Expose each real escalation inbox delivery attempt as a bounded Prometheus
outcome signal with one actionable failure alert, without changing ticket,
delivery, retry, or exception semantics.

## Tasks

- [x] Add red metric, delivery-boundary, skip, and alert contracts.
- [x] Record exactly one `delivered|failed` outcome at the shared inbox boundary.
- [x] Add one failure alert without tenant, ticket, or exception labels.
- [x] Run focused tests, Ruff, scoped MyPy, and diff checks.

## Done When

- [x] Initial and retry delivery attempts increment exactly once by final outcome.
- [x] Duplicate, disabled, rejected, and skipped paths do not claim a delivery attempt.
- [x] Unexpected helper inputs normalize to one bounded `unknown` series.
- [x] Metric failures cannot change escalation behavior and focused verification is green.

## Notes

This local slice does not add a dashboard, call a live inbox, change retry
policy, or close orphan-work, safety-block, tenant-denial, or live alert
delivery residuals.

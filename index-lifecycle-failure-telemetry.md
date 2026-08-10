# Index lifecycle failure telemetry

## Goal

Expose failed index publication and retention operations as a bounded
Prometheus signal with one actionable alert, without changing lifecycle
success or exception semantics.

## Tasks

- [x] Add red metric, lifecycle-boundary, and alert contracts.
- [x] Add `publish|retention` counter recording at the existing failure boundaries.
- [x] Add one operation-labelled alert without tenant or exception labels.
- [x] Run focused tests, Ruff, scoped MyPy, and diff checks.

## Done When

- [x] Both operations increment exactly once on failure and remain unchanged on success.
- [x] Additional label values normalize to a bounded `unknown` series.
- [x] The alert references only the declared metric and focused verification is green.

## Notes

This slice does not add Grafana, change index behavior, or close the remaining
orphan-work, unverified-auto, safety, escalation-delivery, or tenant-denial SLOs.

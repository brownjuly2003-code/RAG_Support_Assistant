# Safety block telemetry

## Goal

Expose each pre-response safety intervention as one bounded Prometheus outcome
with an actionable refusal alert, without changing redaction, refusal, routing,
or exception semantics.

## Tasks

- [x] Add red metric, safety-boundary, non-intervention, and alert contracts.
- [x] Record exactly one `redact|refuse` action per applied unsafe response.
- [x] Add one refusal alert without reason, tenant, trace, or payload labels.
- [x] Run focused tests, Ruff, scoped MyPy, formatter-diff, and diff/LF checks.

## Done When

- [x] PII redaction and injection refusal each increment exactly once.
- [x] Clean and empty answers do not claim a safety block.
- [x] Unexpected helper inputs normalize to one bounded `unknown` series.
- [x] Metric failures cannot change safety decisions and verification is green.

## Notes

This local slice does not change safety policy, add a dashboard, call a live
service, or close orphan-work, tenant-denial, Astro 7, or live alert-delivery
residuals.

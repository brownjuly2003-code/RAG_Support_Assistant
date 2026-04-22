# Task 162 — Post-deploy smoke suite

## Closed
- `scripts/post_deploy_smoke.py` — under-30s sanity CLI. Checks
  `/healthz/live`, `/healthz/ready`, `/metrics` (with required Prometheus
  keys), `POST /api/ask`, `GET /api/admin/providers`.
- Accepts an injected `httpx.Client` so tests use `httpx.MockTransport`.
- Emits a markdown report; exit code 2 on any failed check.

## Verified by
- `tests/test_post_deploy_smoke.py`

# Deployment — RAG Support Assistant

> Moved out of the top-level README to keep it scannable; this is the full deployment reference.

## Dependency lock

`requirements.lock` and `requirements-dev.lock` are generated with [`uv`](https://github.com/astral-sh/uv) from the corresponding `requirements*.txt` files. They pin every transitive dependency with sha256 hashes for reproducible installs (Python 3.11+, Linux x86_64 — same target as the `python:3.11-slim` Docker image).

Update flow when bumping a dependency:

```bash
# 1. Edit requirements.txt or requirements-dev.txt with the new constraint.
# 2. Regenerate the lock(s):
uv pip compile requirements.txt -o requirements.lock \
  --generate-hashes --python-version 3.11 --python-platform linux
uv pip compile requirements-dev.txt -o requirements-dev.lock \
  --generate-hashes --python-version 3.11 --python-platform linux
# 3. Verify install in a clean venv:
python -m venv .venv-lock && .venv-lock/bin/pip install --require-hashes -r requirements.lock
# 4. Commit requirements.txt + requirements*.lock together.
```

CI installs from the lock files and Dockerfile uses `--require-hashes`, so any drift between the constraint file and the lock will fail the build.


## Docker

The default `docker-compose.yml` is a local development stack, not a
production deployment manifest. Published host ports are bound to `127.0.0.1`
and the app container sets `RAG_ENV=development`; use the Helm chart or a
separate production manifest for reachable deployments.

```bash
cp .env.example .env
# Set at least OLLAMA_BASE_URL, DATABASE_URL, DB_ENCRYPTION_KEY, and auth/SSO values as needed.
docker compose up
```

For Kubernetes, use `/api/health/live` as the liveness probe and
`/api/health/ready` as the readiness probe. During shutdown, readiness flips
to `503` for `SHUTDOWN_READY_DELAY_SEC` seconds before cleanup begins.

For local distributed tracing:

```bash
OTEL_ENABLED=true docker compose up -d jaeger
```

Jaeger UI is available at **http://localhost:16686**. Set
`DB_ENCRYPTION_KEY` before running `alembic upgrade head`; keep that key out of
git and back it up separately from database backups.


## Deployment and Migrations

### Deployment topology

**Run exactly one worker and one replica.** Session history, pending
confirm-actions (the human-approval step for irreversible actions such as
`create_ticket`), the LLM/retriever/store caches, the regression-job registry
and the circuit breaker all live in process memory and are **not** shared across
workers or replicas. With more than one process:

- a confirm-action started on process A is invisible to process B, so the user
  is re-prompted forever and the action never completes;
- session continuity and in-memory caches diverge per process;
- queued regression jobs can appear stuck.

The SQLite trace DB uses WAL + `busy_timeout` and tolerates concurrent access,
but that does **not** make the application multi-worker safe. Defaults reflect
the invariant: `Dockerfile` runs `--workers 1`, and the Helm chart ships
`replicaCount: 1` with `autoscaling.enabled: false`. A startup warning fires
when `WEB_CONCURRENCY > 1` (best-effort; it does not catch an explicit
`uvicorn --workers N` flag). Scaling out requires first externalising session
state and pending confirm-actions to Redis/Postgres (the `Message`/`Session`
models exist; `pending_action` and server-side history do not yet).

Deployment artifacts added in arc `102-122` include:

- `deploy/helm/templates/cronjob.yaml` for nightly eval and KB-gap jobs
- `deploy/helm/templates/cronjob-eval-snapshot.yaml` for daily online-evaluator snapshots
- `deploy/helm/templates/cronjob-review-queue.yaml` for hourly review-queue builds
- `deploy/helm/templates/cronjob-improvement-backlog.yaml` for weekly improvement backlog generation
- `deploy/helm/templates/cronjob-report.yaml` for weekly reports
- `deploy/helm/templates/deployment-email-poller.yaml` for IMAP polling mode
- `.github/workflows/weekly-report.yml` for scheduled managed deployments

Alembic migrations introduced after the original README baseline:

- `004_escalated_tickets` - creates the `escalated_tickets` table for the
  agent copilot and escalation workflow.
- `005_eval_results` - stores nightly eval metrics and drift flags.
- `006_knowledge_gaps` - stores clustered unanswered-question topics.
- `007_user_sso_fields` - adds OIDC provider and subject fields to users.
- `008_enable_pgcrypto` - enables `pgcrypto` and converts sensitive columns to
  encrypted storage.
- `009_kb_drafts` - stores reviewable KB drafts generated from resolved tickets.
- `010_document_stats` - tracks citation counts, freshness, and stale-doc
  review state.
- `011_trace_costs` - stores token usage and cost data for analytics.
- `012_review_queue` - creates the `review_queue` table for human quality review.
- `013_regression_eval_runs` - extends `eval_results` for curated regression runs.
- `014_trace_evaluations` - stores per-trace online evaluator outputs.
- `015_experiment_deployments` - stores staged/deployed/rolled-back
  experiment lifecycle records.
- `016_experiment_assignments` - stores tenant rollout assignments and
  rollout percentages.
- `017_curated_case_status` - stores freshness status for curated regression
  cases.

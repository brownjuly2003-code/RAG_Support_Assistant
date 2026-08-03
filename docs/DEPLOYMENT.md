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

### Helm persistence (production chart)

The chart under `deploy/helm/` provisions durable stores for the authoritative
`/app/data` tree (uploads, Chroma, SQLite traces), backup snapshots, and ops
reports.

| Store | Default managed claim | Default size | Notes |
|---|---|---:|---|
| `persistence.data` | `<release>-data` | 10Gi | Mounted at `/app/data` on the app Deployment when enabled |
| `persistence.backups` | `<release>-backups` | 20Gi | Backup CronJobs |
| `persistence.reports` | `<release>-reports` | 5Gi | Report / integrity / restore-verify jobs |

- Leave `existingClaim` empty to create chart-managed PVCs, or set
  `persistence.<store>.existingClaim` to bind a pre-provisioned claim
  (optional `storageClass`, `accessModes`, `size` per store).
- Defaults use `ReadWriteOnce`. If the app pod and a backup Job schedule on
  different nodes, a single RWO volume may not attach to both; choose a
  multi-attach storage class / `ReadWriteMany` only when the backend supports it.
- Production (`env.RAG_ENV=production`) **fails closed** when
  `persistence.data.enabled=false`. Non-production may disable data persistence
  for ephemeral local renders.
- Storage-dependent CronJobs are conditional; backup-snapshot mounts `/app/data`
  read-only and maps Secret `DATABASE_URL` → runtime `POSTGRES_URL`.

**Locally verified:** chart render contracts, helm lint, production fail-closed.
**Still open:** image build/tool smoke, kind/live install, pod recreation,
disposable restore, known-query, measured RPO/RTO.

Runbooks: [operations/helm-lint.md](operations/helm-lint.md),
[operations/backup-restore.md](operations/backup-restore.md).

### Deployment topology

Distinguish the **web process** from the **ingestion worker** — they are not
the same “worker”:

| Role | Default topology | Process |
|---|---|---|
| Web / API | **Exactly one** Uvicorn process and **one** app replica | `uvicorn … --workers 1` |
| Ingestion | **Exactly one** Celery worker with **concurrency 1** | `celery -A tasks.celery_app:celery_app worker --concurrency=1 --hostname=ingest@%h` |

**Web (Uvicorn).** Session history, pending confirm-actions (the human-approval
step for irreversible actions such as `create_ticket`), the LLM/retriever/store
caches, the regression-job registry and the circuit breaker all live in process
memory and are **not** shared across Uvicorn workers or app replicas. With more
than one web process:

- a confirm-action started on process A is invisible to process B, so the user
  is re-prompted forever and the action never completes;
- session continuity and in-memory caches diverge per process;
- queued regression jobs can appear stuck.

The SQLite trace DB uses WAL + `busy_timeout` and tolerates concurrent access,
but that does **not** make the web application multi-worker safe. Defaults
reflect the invariant: `Dockerfile` runs `--workers 1`, and the Helm chart ships
`replicaCount: 1` with `autoscaling.enabled: false`. A startup warning fires
when `WEB_CONCURRENCY > 1` (best-effort; it does not catch an explicit
`uvicorn --workers N` flag). Scaling the web tier out requires first
externalising session state and pending confirm-actions to Redis/Postgres (the
`Message`/`Session` models exist; `pending_action` and server-side history do
not yet).

**Ingestion (Celery).** Local Compose starts a dedicated `worker` service built
from the same image/source as `app`, with the same `.env` and DB/Redis/Ollama
environment, the shared `./data:/app/data` bind mount, `restart: unless-stopped`,
`stop_grace_period: 3600s` for warm shutdown, and a healthcheck that runs
`python -m tasks.worker_health` (Celery control ping of `ingest@<hostname>` —
not a PID/process grep). The worker publishes no host ports. There is no
configured Celery ingestion `task_time_limit` in this repository, so the
default warm-shutdown grace is deliberately long (3600 seconds) to avoid
SIGKILL mid-embed/index of a large document.

Helm runs the same Celery process as a **sidecar** in the single-replica app
pod (`worker.enabled: true` by default). A sidecar keeps the default
ReadWriteOnce data PVC on one node/pod and avoids multi-attach. The worker
container uses the same image, ConfigMap + Secret `envFrom`, writable
`/app/data`, pod/container security contexts, and checksum-triggered rollout as
the app; it publishes no container port. Values expose concurrency, log level,
resources, probe timings, and `terminationGracePeriodSeconds` (default 3600).
Rendering **fails closed** when the worker is enabled but data persistence is
off, or when the effective topology would create more than one ingestion
execution slot (`replicaCount != 1` or `worker.concurrency != 1`).
Non-production data-disabled charts remain possible only with
`worker.enabled=false`. Disabling the worker leaves the existing app
Deployment contract intact.

Later ingestion slices add a stuck-queued reaper, bounded publish
retry/idempotency, and the `rag_ingestion_queue_oldest_seconds` alerting
contract. **Still open:** atomic index publish (ING-02), per-tenant distributed
locking, and live Redis/Postgres/Celery drills.

Tenant physical names preserve existing lowercase-safe identifiers such as
`default`, UUIDs, and `acme-corp`. Uppercase, Windows-reserved, lossy, or long
identifiers use a deterministic `safe-slug--<16 hex SHA-256>` component for
both Chroma collections and upload directories. Ambiguous legacy directories
are never adopted automatically: verify tenant ownership, move or re-ingest
the corpus into the new directory, then run
`python scripts/reindex.py --tenant <canonical-id>`. `reindex.py --all` fails
closed when it encounters a hashed directory because the canonical ID is not
reversible from that physical name.

### Reverse proxy and cookie authentication

**The reverse proxy or ingress in front of the app must forward the
original `Host` header unchanged** (e.g. `proxy_set_header Host $host;` in
nginx terms) instead of rewriting it to an upstream/internal service name.
The browser UIs (`static/admin.html`, `agent.html`, `analytics.html`)
authenticate via the httpOnly `access_token` cookie instead of an explicit
`Authorization` header: the `_cookie_auth_bridge` middleware in `api/app.py`
copies the cookie into an `Authorization: Bearer` header on any request
that doesn't already carry one. For state-changing methods —
`POST`/`PUT`/`PATCH`/`DELETE`, tracked in `_COOKIE_AUTH_UNSAFE_METHODS` —
`_cookie_auth_origin_ok()` only allows the bridge to fire when the
browser's `Origin` header has the same netloc as the request's `Host`
header (requests with no `Origin`, e.g. curl or other non-browser clients,
are unaffected).

If the proxy rewrites `Host` so it no longer matches the `Origin` the
browser sends, the check fails and the bridge silently skips attaching
`Authorization` — there is no error at that point. The request then
reaches the normal auth dependency with no credentials and gets a `401`.
Safe methods (`GET`/`HEAD`/`OPTIONS`) skip the origin check entirely, so
pages keep loading; only state-changing calls from the admin/agent/
analytics UI start failing. That combination — pages load fine, actions
silently 401 — is the signature of a `Host`-forwarding misconfiguration
in the proxy layer.

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

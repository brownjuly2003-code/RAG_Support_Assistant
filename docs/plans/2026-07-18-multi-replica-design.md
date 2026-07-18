# Design: from single-replica to multi-replica (audit finding A1 / S4)

- Date: 2026-07-18.
- Status: DESIGN ONLY. Nothing here is implemented. No code, config, Helm,
  or test is changed by this document.
- Source: `audit_grok_16_07_26.md` finding **A1** (MEDIUM, architecture:
  "Single worker/replica hard limit") and **S4** (LOW/ops: "Single-process
  authz state" / confirm-action pending state in memory). See also section 12
  "Multi-replica ready: NO (by design)" and the remediation roadmap item
  "A1 - design doc for multi-replica".
- Code baseline: line numbers below are as of audit HEAD `0b0234c`; treat them
  as anchors, re-grep before touching code.

## 1. Purpose and framing

The app is deployed as a hard **1 worker / 1 replica** invariant:

- `Dockerfile` `CMD [... "--workers", "1"]` (line 20) with a comment stating
  state is not shared across workers/replicas.
- `deploy/helm/values.yaml` `replicaCount: 1` (line 6), `autoscaling.enabled:
  false` (line 39, min=max=1). An `hpa.yaml` template exists but is gated off
  by `autoscaling.enabled`.
- `api/app.py` lifespan emits a runtime warning when `WEB_CONCURRENCY > 1`
  (lines 1356-1374) because session and confirm-action state live in process
  memory.

This document does two things:

1. Inventories **every** piece of process-local mutable state, with the file
   and line where it lives, and classifies what actually breaks at N>1.
2. Proposes a **phased, independently shippable roadmap** to lift the
   invariant, with an explicit cost/benefit line for each item and an honest
   "do not start yet" recommendation.

**Headline recommendation (read this first):** do **not** begin this work
until there is a concrete multi-replica requirement (a load or availability
SLA that a single pod provably cannot meet). The evidence today points the
other way - see section 6. When the requirement is real, the critical path is
short: the two genuine blockers are **confirm-action pending state** (S4) and
**distributed rate limiting**. Almost everything else is either already shared
via Postgres/Redis, or is correct as per-replica state.

## 2. Surprising findings (state the audit assumed was in-process but is not)

Verifying the code changed the shape of the problem versus the audit's
one-line summary ("in-process session, confirm-actions, caches, CB").

1. **Session message history is already externalized to Postgres.**
   `_get_or_create_session` (`api/app.py:933-1039`) reads history back from the
   `messages` table (`db/models.py:86` `Message`, encrypted via
   `EncryptedText`) and rehydrates a fresh `ConversationSession` on a cache
   miss (lines 1021-1023). The `/api/ask` and `/api/ask/stream` handlers
   persist each turn to Postgres (`api/routers/conversation.py` commit sites
   ~380, 842, 950). `GET /sessions` and `GET /sessions/{id}/history`
   (`api/routers/session_auth.py:168-289`) read Postgres first and fall back to
   the in-memory dict only on DB failure. So multi-turn **continuity survives a
   replica switch** already: whichever pod serves the next turn reloads history
   from Postgres. The in-memory `_sessions` dict is a *warm cache plus binding*,
   not the source of truth for history.

2. **The LLM response cache is already Redis-backed** (`cache/redis_cache.py`),
   with a per-process dict only as a graceful fallback when Redis is
   unreachable. Keys are deterministic `(tenant, question)` via
   `api.app._cache_key`. If `redis_url` is configured, this cache is already
   shared across replicas. Note it is **off by default**
   (`llm_cache_enabled=False`, used at `api/routers/conversation.py:83,104,277`).

3. **Prompt-experiment rollout is deterministic and Postgres-sourced.**
   `_ASSIGNMENTS_CACHE` (`agent/prompt_registry.py:25`) is a read-through cache
   of the `experiment_assignments` table, refreshed by
   `refresh_assignment_cache_from_db` (line 116). The rollout decision is a
   stable SHA-256 hash bucket over `(tenant_id, session_id or user_id)`
   (`_stable_rollout_bucket`, line 109), so **all replicas make the identical
   assignment** for the same user. The only gap is refresh lag, which is
   eventual consistency against a shared source of truth - not a blocker.

The genuinely process-local, non-shared, correctness-affecting state is far
smaller than "session + confirm + caches + CB": it is essentially
**confirm-action pending state** and **the rate limiter counters**.

## 3. Inventory of process-local state

Verdict legend:
- **BLOCKER** - breaks correctness/security at N>1; must externalize before HPA.
- **SHARED** - already durable/shared via Postgres or Redis; no work needed.
- **PER-REPLICA-OK** - process-local by design and correct that way; accept.
- **DEGRADES** - not a correctness bug but a UX/observability regression at N>1;
  externalize opportunistically or document the limitation.

| # | State | Location (file:line) | Backing today | What happens at N>1 | Verdict |
|---|---|---|---|---|---|
| 1 | Confirm-action pending (`_pending_action`) | `agent/graph.py:2188`, mutated 2324/2407-2460/2482 | in-memory on `ConversationSession` inside `_sessions` | Ticket confirm handled by a different pod than the one that created the pending action finds no pending action -> confirm silently drops; restart loses it (S4) | **BLOCKER** |
| 2 | Session object cache + retriever binding (`_sessions`/`_session_llm_state`) | `api/app.py:245-246` | in-memory dict; history rehydrated from Postgres | Continuity OK (history is in PG); but the in-memory history *copy* can go stale vs PG if two pods touch one session (cache coherence) | **DEGRADES** (item 1 rides on this object) |
| 3 | Session message history | `db/models.py:86`; `api/app.py:947-986` | **Postgres `messages`** | Nothing - already shared | **SHARED** |
| 4 | `_session_last_access` (TTL bookkeeping) | `api/app.py:248`, cleanup 1402-1413 | in-memory | Each pod expires only sessions it has seen; PG `sessions.last_access` (col at `db/models.py:40`) is the durable clock | **PER-REPLICA-OK** |
| 5 | Rate limiter counters (slowapi) | `api/rate_limit.py:49` `Limiter(key_func=...)` (no `storage_uri`) | in-memory moving window per process | Effective limit multiplies by replica count; the `5/minute` login limit (`session_auth.py:60`) is the security-relevant one - brute-force protection weakens by factor N | **BLOCKER** (security) |
| 6 | Circuit breaker singleton (`_default_breaker`) | `agent/graph.py:305`, class `utils/circuit_breaker.py` | in-memory, thread-locked | Each pod trips independently against the shared Ollama/provider backend; slower collective reaction, no correctness issue; admin reset (`admin_ops.py:30`) only resets the pod that served the request | **PER-REPLICA-OK** (document reset caveat) |
| 7 | Retry/backoff | `utils/retry.py` | stateless (pure wrapper) | Nothing | **PER-REPLICA-OK** |
| 8 | LLM response cache | `cache/redis_cache.py`; used `conversation.py:104,277` | **Redis** (+ per-process dict fallback) | Shared when `redis_url` set; deterministic keys, no coherence issue | **SHARED** (when Redis on) |
| 9 | BM25 chunk cache (`_chunks_cache`) | `vectordb/manager.py:25`, restore `:360` `_restore_chunks_from_store`, fill `:239/:499` | in-memory per tenant | Rebuilt lazily per pod from the persisted Chroma store on first query (`:487-499`); a fresh pod repopulates itself; correct, just a warm-up cost | **PER-REPLICA-OK** |
| 10 | Embedding model warm cache (`_cached_embeddings`) | `vectordb/_base_manager.py:258-306` | in-memory single slot | Each pod loads its own model weights - this is desired (you want per-pod model memory) | **PER-REPLICA-OK** |
| 11 | Reranker warm cache (`_cached_reranker`) | `vectordb/_base_manager.py:313,335` | in-memory single slot | Same as embeddings | **PER-REPLICA-OK** |
| 12 | Prometheus registry | `monitoring/prometheus.py:93` custom `CollectorRegistry()` | in-memory per process, no `PROMETHEUS_MULTIPROC_DIR` | Correct **iff** Prometheus scrapes each pod as its own target (standard k8s pattern). Counters aggregate at query time; gauges like breaker state are legitimately per-pod | **PER-REPLICA-OK** (scrape-per-pod) |
| 13 | SQLite step-trace store | write path `tracing/_base_trace.py:119-133` (WAL); admin read `api/routers/admin_ops.py:154` `get_trace_detail` | node-local SQLite file | A trace written on pod A is invisible to the admin trace-detail endpoint served by pod B; traces fragment across pods (OTel/Langfuse exporters remain the cross-pod path) | **DEGRADES** |
| 14 | Prompt-experiment assignment cache | `agent/prompt_registry.py:25` | read-through from Postgres `experiment_assignments`; deterministic rollout | Only refresh lag; rollout identical across pods | **SHARED** (eventual) |
| 15 | Provider failover backoff (`_FAILOVER_CACHE_UNTIL`) | `llm/providers/runtime.py:25` | in-memory | Per-pod backoff timers against shared providers; like the breaker, acceptable | **PER-REPLICA-OK** |
| 16 | Provider runtime cache (`_RUNTIME_CACHE`) | `llm/providers/runtime.py:260` | in-memory, config-derived | Immutable per config; per-pod is fine | **PER-REPLICA-OK** |
| 17 | Online-eval warn dedup (`_ONLINE_EVAL_WARNED`) | `agent/graph.py:62-63` | in-memory set | Cosmetic (one warn per pod instead of one globally) | **PER-REPLICA-OK** |
| 18 | Regression job tracking (`_regression_jobs`) | `api/app.py:263` | in-memory dict | Admin starts a regression job on pod A, polls status on pod B -> 404/lost; admin-only, ephemeral | **DEGRADES** |
| 19 | Pipeline concurrency semaphore | `api/app.py:254`, `_get_pipeline_semaphore:266` | in-memory `asyncio.Semaphore` | Bounds each pod independently; total cluster concurrency = N x bound (intended for load spreading) | **PER-REPLICA-OK** |
| 20 | Telegram bot sessions (`_sessions[chat_id]`) | `channels/telegram_bot.py:22` | in-memory | Not part of the HTTP-API replica set; the bot is a separate long-poll single instance, but it carries the **same `_pending_action` pattern** and must stay single-instance | **PER-REPLICA-OK** (keep single-instance) |
| 21 | `_db_retry_after` circuit for PG | `api/app.py:249` | in-memory | Per-pod DB-degradation backoff; correct per-pod | **PER-REPLICA-OK** |
| 22 | `_vector_store` / `_retriever` / `_chunks` globals | `api/app.py:250-252` | in-memory, lazily built | Per-pod warm state rebuilt from persisted Chroma; correct | **PER-REPLICA-OK** |

Net: of 22 items, **2 are hard blockers** (1, 5), **3 shared already** (3, 8,
14), **3 degrade** (2, 13, 18), and **14 are correctly per-replica**.

## 4. Target designs (per blocker / degrade item)

### 4.1 Confirm-action pending state (item 1) - BLOCKER

Today `_pending_action` (a `{summary, priority, action_summary}` dict) lives on
the `ConversationSession` object and is created in one request and consumed in a
later `confirm=true/false` request. Across replicas the consuming request may
land on a pod that never saw the pending action.

Target: externalize the pending action to a **shared store keyed by
`session_id`**, with a short TTL (a pending confirmation is inherently
short-lived).

- **Preferred: Redis** (`cache/redis_cache.py` already exists; add
  `cache_json_set(f"pending_action:{tenant}:{session_id}", payload, ttl=~600)`
  and read/delete on confirm). Redis semantics (TTL, atomic delete on confirm to
  prevent double-execution) fit this exactly.
- Alternative: a `pending_actions` Postgres table (durable across full Redis
  loss). Overkill for a 10-minute confirmation window; only choose it if a
  hard "never lose a pending confirm across a total cache outage" requirement
  exists.

Correctness note: the consume path must be **atomic** - delete-then-execute (or
`GETDEL`) so two racing confirm requests cannot both fire `create_ticket`. This
matters even at N=1 under retries; externalizing is the natural moment to make
it atomic.

Verification: two-pod (or two-worker) integration test - create pending action
against worker A, send `confirm=true` routed to worker B, assert the ticket is
created exactly once and the pending key is gone.

### 4.2 Distributed rate limiting (item 5) - BLOCKER (security)

slowapi is instantiated with no `storage_uri` (`api/rate_limit.py:49`), so each
process keeps its own moving-window counters. At N replicas a client gets
N times the intended budget; the `5/minute` login limit is the one that matters
for brute-force resistance.

Target: point slowapi at **Redis** via `Limiter(key_func=..., storage_uri=
settings.redis_url)` (slowapi supports Redis/memcached storage natively). No
decorator changes needed. Keep the in-memory default when `redis_url` is unset
so single-replica dev is unaffected.

Verification: hit a limited endpoint across two workers sharing one Redis and
assert the combined 429 threshold equals the single-process threshold, not 2x.

### 4.3 In-memory history coherence (item 2) - DEGRADES

The `ConversationSession` caches a copy of history seeded once from Postgres
(only when the session is first created, `api/app.py:1021`). If pod A and pod B
both hold a live session object for the same `session_id`, each appends to its
own in-memory copy; Postgres stays authoritative but the *graph context* each
pod feeds the LLM can diverge.

Options (choose per requirement, not preemptively):
- Cheapest: **sticky sessions** (see 4.6) so one session_id maps to one pod.
  This makes items 1 and 2 non-issues without any store work, and is the
  recommended first lever if the driver is throughput, not availability.
- Fuller: make the session object a thin wrapper that re-reads recent history
  from Postgres (or a Redis list) on each turn instead of trusting its cached
  copy. More correct under pod failover; more DB load per turn.

### 4.4 Trace fragmentation (item 13) - DEGRADES

Step traces are written to a node-local SQLite file and the admin trace-detail
endpoint reads that same node-local file, so cross-pod trace lookup fails. No
active Postgres writer for the `Trace` ORM model was found under `tracing/`;
SQLite is the authoritative step-trace store today, with OTel and Langfuse as
the external/distributed exporters.

Options:
- Rely on **OTel/Langfuse** for cross-replica trace inspection and treat the
  admin SQLite trace UI as a per-pod/dev tool (document the limitation). Lowest
  cost; recommended unless the admin trace UI is a hard requirement in prod.
- Move step traces to Postgres (a real ORM writer plus read path). Larger; only
  if the built-in admin trace UI must work cluster-wide.

### 4.5 Regression job tracking (item 18) - DEGRADES

`_regression_jobs` is an admin-only, best-effort progress dict. Under N>1 a job
started on one pod cannot be polled on another. Cheapest fix if it ever matters:
persist job state to Postgres (a small `regression_jobs` table) or accept the
limitation and document "run admin regression jobs against a single pinned pod".
Low priority.

### 4.6 Sticky sessions (workaround lever, not a store)

A cookie/`session_id`-hash based session affinity at the ingress
(`deploy/helm/templates/ingress.yaml`) collapses the confirm-action and
history-coherence problems (items 1, 2) to non-issues **without** any shared
store, because every request for a session lands on the same pod. It does **not**
help the rate limiter (keyed by client IP across all sessions) - that still
needs Redis (4.2). Sticky sessions trade even load distribution and clean pod
drain for implementation simplicity; they are the right first step when the
goal is horizontal throughput and the risk of losing an in-flight confirm on a
pod eviction is acceptable.

## 5. Phased rollout plan

Each phase is independently shippable and independently verifiable. Phases are
ordered so that **Helm `replicaCount` / HPA is enabled LAST**, only after the
state it depends on is externalized and tested.

### Phase 0 - Decision gate (no code)

Confirm a real multi-replica requirement exists (load/availability SLA a single
pod cannot meet). If not, stop here and keep the single-replica invariant. This
document is the artifact that lets Phase 0 be answered quickly later.

### Phase 1 - Distributed rate limiting (Redis)

- Add `storage_uri=settings.redis_url` to the slowapi `Limiter` when Redis is
  configured; keep in-memory fallback otherwise.
- Verify: two-worker shared-Redis test shows a single combined budget; login
  `5/minute` holds cluster-wide. Ships and is valuable **even at N=1** (survives
  restarts within the window) and is a prerequisite for any N>1.

### Phase 2 - Confirm-action externalization + atomic consume (Redis)

- Move `_pending_action` to Redis keyed by `session_id` with TTL; make consume
  atomic (delete-then-execute / `GETDEL`).
- Verify: cross-worker create/confirm integration test; exactly-once ticket
  creation; TTL expiry test. Closes audit S4 (also a reliability win at N=1
  across restarts).

### Phase 3 - Session history coherence

- Either enable sticky sessions at ingress (cheapest) OR switch
  `ConversationSession` to re-read recent history per turn from Postgres/Redis.
- Verify: two-worker interleaved conversation keeps a single coherent thread;
  pod-eviction mid-conversation still continues from Postgres.

### Phase 4 - LLM cache + optional trace/job externalization (opportunistic)

- Confirm the Redis LLM cache is enabled and shared in the target env
  (`llm_cache_enabled=true`, `redis_url` set); it needs no code change, only
  config, because it is already Redis-backed.
- Decide on trace fragmentation (item 13) and regression jobs (item 18):
  document the per-pod limitation, or externalize if the admin surfaces must
  work cluster-wide.
- Verify: cache hit served from a different pod than the one that populated it;
  documented behavior for traces/jobs matches reality.

### Phase 5 - Prometheus scrape-per-pod

- No app change if the target Prometheus scrapes each pod as its own target
  (the standard k8s ServiceMonitor / pod-annotation pattern). Only if multiple
  uvicorn workers ever share one pod/port would `PROMETHEUS_MULTIPROC_DIR`
  multiprocess mode be required - which the "1 worker per pod" model avoids.
- Verify: each pod's `/metrics` scraped independently; dashboards sum/aggregate
  across pod labels; per-pod gauges (breaker state) read correctly.

### Phase 6 - Enable multi-replica (Helm) - LAST

- Only after Phases 1-3 (and the Phase 4/5 decisions) are shipped and verified:
  raise `deploy/helm/values.yaml` `replicaCount`, set `autoscaling.enabled:
  true` with sane `minReplicas`/`maxReplicas`, and re-enable the existing
  `hpa.yaml`. Update the Dockerfile/Helm/README single-worker comments and the
  `WEB_CONCURRENCY>1` startup warning (`api/app.py:1356-1374`).
- Verify: `helm template`/`helm lint` with `replicaCount>1`; rolling deploy with
  N>1 keeps confirm flows, rate limits, and conversation continuity intact under
  a smoke load; graceful drain (readiness flip already present) does not strand
  pending confirms.

## 6. What is NOT worth externalizing, and why

- **Embedding/reranker/chunk warm caches (items 9-11, 22):** you *want* each
  pod to hold its own model weights and chunk cache. Externalizing model weights
  is nonsensical; the Chroma store is already the shared persistence and pods
  repopulate lazily. Cost of change: high (and harmful). Benefit: none.
- **Circuit breaker / failover backoff (items 6, 15):** per-pod breakers are a
  standard, acceptable pattern. A shared breaker would need a distributed
  consensus/state store and would couple pod health decisions; the only real
  downside today is that admin "reset breaker" hits one pod. Document that;
  do not build distributed breaker state. Cost: high. Benefit: marginal.
- **Prometheus registry (item 12):** scrape-per-pod is the correct Prometheus
  model and already works. Multiprocess mode solves a different problem
  (many workers, one port) that the topology deliberately avoids. Cost: real.
  Benefit: none for 1-worker-per-pod.
- **Per-pod semaphore, TTL bookkeeping, warn-dedup, DB retry backoff (items 4,
  17, 19, 21):** these are load/robustness locals that are correct per-pod;
  sharing them adds coupling for no correctness gain.

## 7. Explicit non-goals and "do not start yet"

Consistent with the audit ("Do not: enable multi-worker" in section 13;
"Multi-worker uvicorn without state externalization" in the non-goals):

- Do **not** flip `--workers`, `replicaCount`, or `autoscaling.enabled` ahead of
  Phases 1-3. The startup warning and the Dockerfile/Helm comments are the guard
  rails; they come down only in Phase 6.
- Do **not** build a distributed circuit breaker, shared Prometheus multiprocess
  aggregation, or a Postgres trace store speculatively - they are section 6
  "not worth it" items until a specific requirement says otherwise.
- Do **not** start any phase before the Phase 0 decision gate confirms a real
  requirement. Today's evidence argues against urgency:
  - Median full-graph latency is dominated by CPU embedding + external provider
    (~190s worst case in dogfood), so throughput is bound by model/provider
    capacity, not by the number of API pods. Adding API replicas does not remove
    that bottleneck.
  - Session history, LLM cache, and experiment rollout are already
    Postgres/Redis-backed, so the only *correctness* blockers (confirm-action,
    rate limiting) are small and can be done in two focused PRs when needed.
  - The remedy is cheap to start later precisely because this inventory exists;
    there is no bit-rot risk in deferring it (unlike the dep-CVE backlog).

The correct posture: keep the single-replica invariant, keep this design on the
shelf, and execute Phases 1-6 only when a load or availability SLA makes
horizontal scale a requirement rather than a hypothetical.

## 8. Quick verification (when work begins)

```bash
# Confirm the state anchors still exist before touching code
grep -n "_pending_action" agent/graph.py
grep -n "storage_uri\|Limiter(" api/rate_limit.py
grep -n "_get_or_create_session\|_session_llm_state" api/app.py
grep -n "replicaCount\|autoscaling" deploy/helm/values.yaml
grep -n "workers" Dockerfile

# Two-worker local reproduction (the smallest multi-process surface):
#   WEB_CONCURRENCY=2 uvicorn api.app:app --workers 2
# Expect the startup warning (api/app.py:1356-1374) until Phase 6.
```

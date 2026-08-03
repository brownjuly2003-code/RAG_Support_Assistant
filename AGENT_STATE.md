# Agent State

## 2026-08-03 Update-27 (step 4.8d1 atomic manifest rollback @ `c160af8`) ✅ START HERE

> **Implementation commit:** `c160af8` (`feat(index): add atomic manifest
> rollback`). Plan sub-slice **4.8d1 is locally complete and verified**:
> - a caller holding the current matching tenant-lock token can atomically swap
>   manifest `active_collection` and `previous_collection`
> - rollback reuses the existing flushed + fsynced `os.replace` publisher, so
>   generation increments and the former active collection becomes the next
>   rollback target
> - absent manifest/previous state, wrong-tenant tokens, and expired tokens fail
>   closed; replace failure leaves the prior manifest byte-for-byte unchanged
>
> **Verification:** four rollback contracts first failed while the API was
> absent and the seven existing manifest tests passed. The focused file then
> passed **11 tests**; the manifest/staging/runtime/tenant-lock closure gate
> passed **32 tests** with one expected warning. Scoped Ruff, locked Python 3.11
> / mypy 1.19.1 / NumPy 2.4.4, and diff checks are clean. No Chroma collection
> was opened or deleted; no real PostgreSQL, push, deploy, or live service was
> touched.
>
> **Current truth:** plan step 4 and 4.8d remain in progress. This is an unwired
> manifest-only rollback primitive, not a complete runtime rollback. Target
> collection validation/wiring, bounded retention, broader fault injection,
> immutable/versioned originals, and live drills remain open. No next slice was
> started in this turn; protected untracked user artifacts remain untouched.

## 2026-08-03 Update-26 (step 4.8c atomic runtime publish @ `8594675`) — SUPERSEDED by Update-27

> **Implementation commit:** `8594675` (`feat(index): publish staged
> collections atomically`). Plan slice **4.8c is locally complete and
> verified**:
> - document Chroma rebuild builds a versioned candidate under the existing
>   tenant-lock token, validates count/dimension plus a deterministic known
>   query, atomically publishes the active manifest, and retains the old
>   collection
> - retrieval resolves the manifest before process-cache reuse and invalidates
>   stale retrievers by Chroma directory, active collection, and generation;
>   corrupt manifests fail closed even when a retriever is cached
> - API startup opens the manifest-active collection, session setup returns 503
>   instead of reusing a stale retriever after active-index resolution failure,
>   and KB draft publication mutates the active collection under the same
>   tenant lock before clearing the local retriever cache
> - the global unit-test fixture now fakes only the advisory-lock connection;
>   production acquire, release, timeout, and token logic remain active, while
>   dedicated lock tests can replace the connection with their own registry
>
> **Verification:** the three known fixture-induced lock failures were
> reproduced before the correction. The exact nine-file closure gate then
> passed **73 tests** with two expected deprecation warnings. Scoped Ruff is
> clean across all 12 changed Python files; locked Python 3.11 / mypy 1.19.1 /
> NumPy 2.4.4 reports no issues in the four changed runtime files; staged and
> unstaged diff checks are clean. No real Chroma, PostgreSQL, push, deploy, or
> live service was touched.
>
> **Current truth:** plan step 4 remains in progress. Slices 4.1–4.8c are
> locally verified, but rollback/retention/fault injection (4.8d) and the live
> step-4 drills remain open. Slice 4.8d was not started in this turn. The
> untracked `_NEXT_SESSION.md` records the now-superseded pre-fix handoff and
> remains intentionally unstaged with the other protected user artifacts.

## 2026-08-03 Update-25 (step 4.8c uncommitted WIP; QA stopped at 70/3) — SUPERSEDED by Update-26

> **Current HEAD:** `2c634fd`; last verified implementation commit: `74d187c`.
> Plan slice **4.8c is not complete and has no commit**. The tracked worktree
> contains runtime/test WIP, and `tests/test_index_runtime_switch.py` is a new
> untracked task file. Preserve all of it; do not stage unrelated untracked
> user artifacts.
>
> **Implemented WIP:** document Chroma rebuild now builds the existing 4.8b
> versioned candidate under the active tenant-lock token, runs deterministic
> known-query validation, publishes the candidate through the 4.8a atomic
> manifest, and retains the old collection. Retrieval resolves the manifest
> before using process caches and keys invalidation by directory, active name,
> and generation. API startup resolves the active collection; session setup
> fails with 503 rather than reusing a stale retriever after active-index
> resolution failure. KB draft publish resolves the active collection under
> the same tenant lock and clears the local retriever cache.
>
> **Evidence:** the new runtime contract demonstrated 6 expected failures on
> the old code, then 6 passes; a separate stale-retriever contract demonstrated
> red before its fail-closed change. The first adjacent QA batch reported 42
> passes / 3 test-double failures. After the batched QA fixes and an additional
> red admin-active-collection contract, the expanded nine-file gate reported
> **70 passed / 3 failed** with two expected warnings. No real Chroma,
> PostgreSQL, push, deploy, or live service was touched.
>
> **Only known blocker:**
> `tests/conftest.py::_isolate_tenant_index_advisory_lock` globally stubs
> `_acquire`, `_release`, and `_wait_timeout_sec`. That makes three dedicated
> lock tests bypass production serialization/timeout/config logic:
> `test_same_tenant_rebuilds_are_serialized`,
> `test_lock_timeout_fails_closed_and_does_not_steal_owner`, and
> `test_lock_wait_setting_rejects_non_finite_or_negative_values`.
>
> **Next session — one narrow correction only:** change the autouse fixture so
> it patches only `_open_lock_connection` with a fake connection whose
> `execute().scalar_one()` returns `True` and whose `close()` is a no-op. Leave
> production `_acquire`, `_release`, and `_wait_timeout_sec` intact and keep
> `manager.tenant_index_lock` pointing to the real context manager so callers
> receive a genuine active `TenantIndexLockToken`. Then rerun the exact
> nine-file command in `_NEXT_SESSION.md`. If green, run scoped Ruff/locked
> Mypy/diff checks and create the explicit-path local 4.8c commit. Do not start
> 4.8d in that turn. No current WIP commit or status-doc commit exists.

## 2026-08-03 Update-24 (step 4.8b validated staging collection @ `74d187c`) — SUPERSEDED by Update-25

> **Implementation commit:** `74d187c` (`feat(index): add validated staging
> collections`). Plan slice **4.8b is locally complete and verified**:
> - document candidates use collision-resistant, 63-character-bounded
>   `<prefix>-v-<physical-tenant>-<candidate>` names in a namespace distinct
>   from legacy `<prefix>_<tenant>` collections
> - the unwired builder requires the existing tenant advisory-lock token, builds
>   only the candidate through Chroma `from_documents`, persists when supported,
>   then validates exact chunk count and embedding dimension with a raw-vector
>   probe
> - neither the active manifest nor legacy collection is opened, deleted, or
>   switched; success returns an unpublished candidate for the later 4.8c path
> - build, count, or dimension failure deletes only that candidate; cleanup
>   failure remains explicit and preserves the deletion root cause
>
> **Verification:** test-first contract was **6 expected failures**, then 6
> passes. The single QA follow-up demonstrated **2 expected failures** for an
> empty explicit candidate ID and overwritten cleanup cause, then 2 passes. The
> final staging/manifest/naming/lock gate passed **33 tests** with two expected
> deprecation warnings. Scoped Ruff, locked Python 3.11 / mypy 1.19.1 / NumPy
> 2.4.4, and diff checks are clean.
>
> **Current truth:** plan step 4 remains in progress. The staging builder is
> intentionally not called by `build_vector_store()`, upload, reindex, or
> retrieval, and no real Chroma was mutated. Production rebuild therefore still
> uses delete-then-build. Known-query validation + atomic manifest switch and
> generation-aware cache invalidation (4.8c), rollback/retention/fault injection
> (4.8d), and live drills remain open. No next slice was started. No
> Grok/delegation, push, deploy, or live service calls occurred; protected
> untracked user artifacts remain unstaged and untouched.

## 2026-08-03 Update-23 (step 4.8a active-version manifest @ `ca15c1a`) — SUPERSEDED by Update-24

> **Implementation commits:** `c015ba8` (`feat(index): add active-version
> manifest registry`) + `ca15c1a` (`fix(index): enforce integer manifest
> schema`). Plan slice **4.8a is locally complete and verified**:
> - each tenant manifest uses a collision-resistant physical filename under the
>   strict-schema v1 `index-manifests` registry beside the configured Chroma
>   directory; it stores only active/previous collection, generation, schema
>   version, and timestamp
> - absence resolves to the existing legacy collection name, while malformed,
>   partial, or schema-invalid content fails closed instead of selecting a
>   candidate
> - publication writes a same-directory temporary file, flushes and `fsync`s it,
>   then uses `os.replace`; the prior active collection becomes `previous` and
>   generation increments without exposing a partially written pointer
> - the writer accepts only a current tenant-matched token from the existing
>   PostgreSQL advisory-lock context; the token is revoked on context exit, so
>   no second independent lock was introduced
>
> **Verification:** test-first contract was **7 expected failures**, then 7
> passes. The single QA follow-up demonstrated one expected failure for a float
> `schema_version` before enforcing its integer type. The final
> manifest/naming/lock gate passed **27 tests** with two expected deprecation
> warnings. Scoped Ruff, locked Python 3.11 / mypy 1.19.1 / NumPy 2.4.4, and
> diff checks are clean.
>
> **Current truth:** plan step 4 remains in progress. Slice 4.8a defines the
> durable pointer contract only; it is intentionally not wired into
> `build_vector_store()`, retrieval, or real Chroma. Rebuild still uses
> delete-then-build. Versioned staging/validation (4.8b), atomic runtime switch
> and cache invalidation (4.8c), rollback/retention/fault injection (4.8d), and
> live drills remain open. No next slice was started. No Grok/delegation, push,
> deploy, or live service calls occurred; protected untracked user artifacts
> remain unstaged and untouched.

## 2026-08-03 Update-22 (step 4.7 per-tenant distributed index lock @ `705a3cc`) — SUPERSEDED by Update-23

> **Implementation commit:** `705a3cc` (`fix(ingestion): serialize tenant index
> rebuilds`). Plan slice **4.7 is locally complete and verified**:
> - every document and fact-card rebuild acquires a PostgreSQL session advisory
>   lock derived from the canonical tenant ID; API, Celery, and CLI therefore
>   share one cross-process coordination boundary
> - same-tenant mutation is serialized while different tenant keys remain
>   independent; the connection stays in autocommit and process/connection loss
>   releases the session lock
> - `INGESTION_TENANT_LOCK_WAIT_SEC` bounds contention; timeout, database
>   failure, release failure, or lost ownership fails the rebuild closed without
>   exposing the database URL
> - unit tests isolate the real coordination connection; the dedicated contract
>   exercises concurrent contenders, timeout, cleanup, redaction, and both
>   destructive rebuild paths
>
> **Verification:** test-first contract was **7 expected failures**, then 7
> passes. The single batched QA follow-up passed **59 tests**; the final
> worker/job/upload/docs gate passed **105 tests** with two expected deprecation
> warnings. Scoped Ruff and locked Python 3.11 / mypy 1.19.1 / NumPy 2.4.4 are
> clean; staged diff checks are clean.
>
> **Current truth:** plan step 4 remains in progress. Same-tenant concurrent
> rebuild mutation is locally serialized, but ING-02 remains partially open:
> versioned staging, atomic active-version switch, validation, and rollback are
> not implemented. Live PostgreSQL advisory-lock contention plus existing
> Redis/Postgres/Celery and migration drills remain open. No next implementation
> slice was selected. No Grok/delegation, push, deploy, or live service calls
> occurred; protected untracked user artifacts remain unstaged and untouched.

## 2026-08-02 Update-21 (step 4.6 collision-resistant tenant naming @ `d13804b`) — SUPERSEDED by Update-22

> **Implementation commit:** `d13804b` (`fix(tenancy): prevent physical
> namespace collisions`). Plan slice **4.6 / TEN-03 is locally complete and
> verified**:
> - one shared mapping preserves existing lowercase-safe tenant components and
>   appends a deterministic 16-hex SHA-256 suffix for uppercase,
>   Windows-reserved, lossy, or truncated IDs
> - Chroma document/fact-card collections and upload directories now use that
>   mapping; `reindex.py` and the fact-card cache follow the same contract
> - explicit canonical-tenant reindexing resolves hashed directories, while
>   `reindex.py --all` fails closed when the canonical ID is not reversible
> - deployment/configuration docs include the legacy-directory migration rule
>
> **Verification:** the initial collision contract produced 3 expected
> failures / 6 passes, then 18 passes. Batched QA produced 3 expected failures
> / 9 passes for case-folding, Windows device names, and downstream tools, then
> **21 passes**. The final adjacent gate passed **109 tests** with two expected
> deprecation warnings. Scoped Ruff and locked Python 3.11 / mypy 1.19.1 /
> NumPy 2.4.4 are clean; diff checks are clean.
>
> **Current truth:** plan step 4 remains in progress. TEN-03 is locally
> remediated. Per-tenant distributed locking, ING-02 atomic/versioned index
> publish + rollback, and live Redis/Postgres/Celery and migration drills remain
> open. No next implementation slice was selected. No Grok/delegation, push,
> deploy, or live service calls occurred; protected untracked user artifacts
> remain unstaged and untouched.

## 2026-08-02 Update-20 (step 4.5 ingestion queue-age alert @ `35e4bb9`) — SUPERSEDED by Update-21

> **Implementation commit:** `35e4bb9` (`feat(ingestion): alert on stalled
> queue`). Plan slice **4.5 is locally complete and verified**:
> - every FastAPI ingestion reaper sweep publishes the global, label-free
>   `rag_ingestion_queue_oldest_seconds` gauge for queued async jobs
> - age starts at `source_ready_at`, with `created_at` fallback for pre-`021`
>   rows; sync/running/terminal jobs are excluded and an empty queue resets to 0
> - `IngestionQueueStalled` warns after age exceeds 300 seconds for five
>   minutes, leaving a response window before the default 900-second reaper
>   timeout; operator/deployment docs describe the contract
> - optional Prometheus imports now retain strict type coverage through explicit
>   aliases; no runtime dependency or schema change was added
>
> **Verification:** test-first contract was 3 expected failures before
> implementation and 7 passes after. Closure gate found one stale Session test
> double, then passed **87 tests** with one expected deprecation warning. Scoped
> Ruff is clean; locked Python 3.11 / mypy 1.19.1 / NumPy 2.4.4 reports no
> issues in the two changed runtime modules; diff checks are clean.
>
> **Current truth:** plan step 4 remains in progress. ING-01 queue-age
> observability is now locally implemented; live Redis/Postgres/Celery
> outage/recovery and real migration drills remain open. ING-02 atomic/versioned
> index publish + rollback and TEN-03 remain open. No next implementation slice
> was selected. No Grok/delegation, push, deploy, or live service calls occurred;
> protected untracked user artifacts remain unstaged and untouched.

## 2026-08-02 Update-19 (step 4.4 bounded upload retry/idempotency @ `1cebd14`) — SUPERSEDED by Update-20

> **User explicitly resumed after the Update-18 incident.** Work stayed within
> one bounded local slice; no Grok/delegated runs, push, deploy, or live service
> calls occurred.
>
> **Implementation commit:** `1cebd14` (`feat(ingestion): make upload retries
> idempotent`). Plan slice **4.4 is locally complete and verified**:
> - tenant-scoped optional `Idempotency-Key` stores only its SHA-256 hash and a
>   normalized filename/content fingerprint behind migration `021`'s partial
>   unique index
> - same key + same payload replays the durable job identity; different payload
>   fails with 409; no-key uploads retain distinct-job behavior
> - deterministic Celery task identity is reserved before publish; bounded
>   broker-publish retry runs off the FastAPI event loop; exhausted publish
>   returns 503 with browser-readable `X-Ingestion-Job-Id`
> - `source_ready_at` is a queued-only CAS boundary; worker/task autoretry after
>   load/index mutation remains intentionally disabled while ING-02 is open
> - request/response CORS and operator docs cover the new contract
>
> **Independent Codex verification:** 73 focused idempotency/job/upload tests
> passed (2 expected deprecation warnings); scoped Ruff clean; locked Python
> 3.11 / mypy 1.19.1 / NumPy 2.4.4 checks clean for changed core and API files;
> `alembic heads` = `021 (head)`; staged and unstaged diff checks clean.
> TestClient startup was isolated from unrelated real Alembic/reaper DB work,
> reducing the formerly timing-out 73-test batch to about 41 seconds.
>
> **Current truth:** plan step 4 remains in progress. Queue-age metric/alert,
> live Redis/Postgres/Celery outage/recovery and real migration drills, ING-02
> atomic/versioned index publish + rollback, and TEN-03 remain open. No next
> implementation slice was selected in this turn. Protected untracked user
> artifacts remain unstaged and were not intentionally edited.

## 2026-08-02 Update-18 (cycle incident; step 4.4 paused) — SUPERSEDED by Update-19

> **Documentation-only incident record.** User hard-stopped the session because
> it had become an open-ended cycle. No source/runtime/test/config changes in
> this docs pass. Project is **paused by the user**, not technically blocked.
>
> **Process failure (measured; unacceptable; must not recur):**
> - **9 delegated Grok runs** (`a1`–`a9`)
> - **>40 status-poll iterations** of a buffered background runner
>
> **Root causes:**
> - serial design → implementation → repeated “final QA” edge-hunt runs
> - excessive polling of a buffered background runner
> - continuing from one atomic audit slice into another within one user turn
> - treating additional possible review as a reason to continue after green
>   evidence
>
> **Guard remediation (recorded globally in `D:\AGENTS.md` + `cycle-guard`
> skill):**
> - max **one atomic slice** per user turn
> - max **three delegated runs** for that slice: implementation, one batched
>   QA, one documentation-only run
> - max **one QA follow-up**
> - max **six status polls** or **ten minutes** of monitoring, whichever first
> - after a green gate: commit / document / yield — do **not** select the next
>   slice
> - on hard stop: only **one** exact-writer cancellation cleanup is permitted
>
> **Repository truth at pause:**
> - tracked `HEAD`: `ba647b88b2a2a840c590d5501867063242a97bf0`
> - step **4.3** is committed and independently verified
> - step **4.4** bounded retry/idempotency changes exist in the working tree
>   and are **uncommitted**
> - Grok run `a8` reported green executor-side checks; Codex then found three
>   issues (CORS response-header exposure, queued-state CAS for source-ready,
>   blocking broker publish on the async event loop)
> - run `a9` edited the WIP, but its final report and resulting diff were
>   **not independently reviewed** before the stop — do **not** claim `a9`
>   passed
> - therefore step **4.4 is not verified, not complete, and not committed**
> - no push or deployment occurred
> - protected untracked user artifacts were not staged or intentionally edited
>
> **Mandatory next-session rule:**
> - do **not** automatically resume step 4.4, choose another backlog item, run
>   tests, or start Grok without a **new explicit user direction**
> - if the user explicitly resumes: begin with **one bounded audit** of the
>   existing WIP; do **not** launch another design run; state the numeric
>   cycle budget before work
>
> **Owner/product policy unchanged:** no Hugging Face Space/public HF target;
> external users run locally with their own Mistral key and remote embeddings;
> owner/local defaults remain unchanged.
>
> Historical pre-incident status for steps 4.1–4.3 lives in Update-17 below
> (superseded as current truth; body retained as evidence).

## 2026-08-02 Update-17 (step 4.3 durable liveness/recovery @ `6dc6fe4`) — SUPERSEDED by Update-18

> **SUPERSEDED by Update-18 (cycle incident; step 4.4 paused).** Historical
> status after verified plan-step 4.3. Body retained as evidence; current
> truth and pause rules live in Update-18.
>
> **Documentation-only truth pass** after verified plan-step 4.3 code already on
> HEAD. No source/runtime/test/config/Helm changes in this docs refresh
> (status-layer docs only; README status note only).
>
> **HEAD:** `6dc6fe4` (`fix(ingestion): recover stale jobs with durable leases`).
> Relevant commits:
> - `edb729c` — reopen audit remediation + no-HF local-user path
> - `3c1e7b7` / `28580aa` — TEN-01/TEN-02 tenant + schema ownership
> - `ed8520a` / `2767b9d` — OPS-01 Helm persistence + safe Postgres backup
> - `5a9f857` — OBS-01: internal `trace_id` UUID4 + nullable `correlation_id`
> - `b7faa19` — step 4.1: durable tenant-owned ingestion job contract
> - `4f93038` — step 4.2: single-worker Compose + Helm sidecar topology
> - `6dc6fe4` — step 4.3: durable job lease/heartbeat + stale recovery/reaper
>
> **Exact current truth:**
> - Plan remains **ACTIVE**. Project/production release is **not** complete.
> - P0 release-blocker **implementation is locally remediated and mechanically
>   verified**; production release remains gated by explicit live/external checks.
> - Plan step 1 **locally complete**: all named contract-test slices
>   demonstrated red then green (tenant/audit/Helm + OBS-01). Does **not**
>   close production release.
> - Plan step 2 **local implementation verified; live PostgreSQL DoD open**.
> - Plan step 3 **chart/backup runtime locally verified; operational restore
>   DoD open**.
> - Plan step 4 **in progress** (not complete). Slices **4.1** (`b7faa19`),
>   **4.2** (`4f93038`), and **4.3** (`6dc6fe4`) are locally verified:
>   - **4.1:** ORM `IngestionJob` + migration `019`; durable `job_id`/status;
>     DB-only jobs/tasks reads; tenant-aware worker lifecycle; terminal errors
>   - **4.2 Compose/Helm:** one worker topology (Compose one-worker + Helm
>     Celery sidecar), concurrency 1, exact-node health, 3600s warm shutdown
>   - **4.3:** migration `020`; persisted opaque worker lease token with
>     heartbeat/expiry; atomic queued→running claim; tenant/token/status CAS
>     for heartbeat and terminal transitions; background interruptible
>     heartbeat; independent FastAPI stale queued / expired-lease /
>     legacy-running reaper (only async jobs reaped); recovery clears active
>     ownership/stale result while preserving last heartbeat; sync SQL reaper
>     runs off the event loop; shutdown cancels+awaits reaper; runtime
>     liveness config fails closed (including blank explicit env and
>     heartbeat ≥ lease)
> - Independent Codex verification after final Grok changes for 4.3:
>   55 liveness + 9 ingest-task + 12 upload/security + 26 settings + 27 durable
>   job-contract + 24 docs = **153 passed** total; expected deprecation
>   warnings only. Ruff clean; mypy `--follow-imports=skip` clean;
>   `alembic heads` = `020 (head)`; `git diff --check` clean; protected user
>   artifacts 9/9 unchanged.
> - Test-first/adversarial evidence (honest): import-order fixture leak found
>   via order-dependent failures and fixed by late session resolution; runtime
>   clamp/fallback tests were red before correction; explicit blank env
>   produced 25 expected failures before becoming 25/25 green.
> - Audit finding **ING-01 further partially locally remediated**: durable
>   job/status, local Compose/Helm worker topology, and durable lease/
>   heartbeat + stale recovery/reaper are implemented. **Still open:**
>   bounded retry/idempotency; queue-age metric/alert; live
>   Redis/Postgres/Celery worker-outage/recovery drill; real PostgreSQL
>   upgrade/downgrade through migrations `019`/`020`.
> - **ING-02** non-atomic delete-then-build / atomic versioned index publish +
>   rollback remains **open**.
> - **TEN-03** collision-resistant tenant physical naming remains **open**.
> - Plan step 5 **open / partially remediated**: trace identity done at
>   `5a9f857`; timeout cancellation, bounded capacity, session
>   concurrency/history ordering, sticky experiment propagation still require
>   work.
> - Steps 6–10 remain open. Audit plan / OPS-01 operational DoD / project
>   closure are **not** complete.
> - Owner policy unchanged: **no HF Space/public target**; external users run
>   locally with own `MISTRAL_API_KEY` + remote embeddings + empty
>   `RAG_RERANKER_MODEL`. Do not duplicate or modify recipes.
>
> **Protected untracked artifacts:** nine protected untracked user artifacts
> still match their recorded hashes (portfolio/kitchen + presentation/explainer
> + architecture diagram, etc.). Do not stage/delete/rename them in scoped
> commits unless the owner explicitly includes them. Original audit body in
> `audit_gpt_23_07_26.md` is a dated snapshot — update only the top
> remediation/status layer.
>
> **Next atomic implementation slice (plan order):** step **4.4** bounded
> retry/idempotency contract. Keep queue-age alerting, atomic publish, TEN-03,
> and live/external drills explicitly **unclaimed**.

## 2026-08-02 Update-16 (step 4.2 worker topology @ `4f93038`) — SUPERSEDED by Update-17

> **SUPERSEDED.** Historical status at HEAD `4f93038` after step 4.2 worker
> topology and before step 4.3 liveness/recovery. Next was 4.3 durable
> lease/heartbeat + stale reaper. Status truth now lives in Update-17.

## 2026-08-02 Update-15 (step 4.1 durable job contract @ `b7faa19`) — SUPERSEDED by Update-16

> **SUPERSEDED.** Historical status at HEAD `b7faa19` after step 4.1 durable
> job contract and before step 4.2 worker topology. Next was 4.2 Compose/Helm
> worker. Status truth now lives in Update-17.

## 2026-08-02 Update-14 (OBS-01 local remediation documented @ `5a9f857`) — SUPERSEDED by Update-15

> **SUPERSEDED.** Historical status at HEAD `5a9f857` after OBS-01 local close
> and before step 4.1 durable job contract. Step 4 was still wholly open as the
> next first job-contract slice. Status truth now lives in Update-17.

## 2026-08-02 Update-13 (P0 local remediation documented @ `2767b9d`) — SUPERSEDED by Update-14

> **SUPERSEDED.** Historical status at HEAD `2767b9d` after P0 local
> remediation and before OBS-01 close. Step 1 was still in progress with
> OBS-01 as next slice. Status truth now lives in Update-17.

## 2026-08-02 Update-12 (audit revalidation + no-HF local-user path) — SUPERSEDED by Update-13

> **SUPERSEDED.** Historical revalidation at HEAD `26d24e6` before P0 local
> remediation commits. P0 were still open at that SHA. HF no-Space policy and
> reopened audit plan remain valid; status truth now lives in Update-17.

## 2026-07-27 Update-11 (project closure candidate) — SUPERSEDED by Update-12

> **SUPERSEDED 2026-08-02.** Historical closure-candidate note. Product backlog
> was marked empty and feature-frozen; deferred SLA/Q1b/C1/live-benchmark
> choices recorded in `docs/PROJECT_CLOSURE.md`. Twelve local untracked
> portfolio/kitchen artifacts remain preserved.
>
> Remaining external publish/CI/Pages gates from that note are still owner-
> gated; they do **not** override the reopened audit plan.

## 2026-07-21 Update-10 (presentation DoD добит 10/10: axe 0 + вычитка) — SUPERSEDED by Update-11

> **START HERE.** Заход: «продолжи» после Update-9. Product backlog по-прежнему
> **пуст** (гейты Update-7 без изменений); сделан единственный незагейченный
> остаток — presentation residual (§6 axe + §9 вычитка, были non-blocking).
>
> **Сделано (все файлы untracked, в git не попадали):**
> - **axe (WCAG A/AA, Playwright+axe-core 1536×740, reducedMotion): 0 violations
>   RU+EN**, включая ночной band и открытый поповер `#src`. Было: 21 узел
>   color-contrast. Затемнены токены: день `--muted #6E7686→#666E7D`,
>   `--faint #A6ADBA→#646C7B` (проходят и на карточке `#F2F4F8`: 4.66/4.80);
>   ночь `--faint #5E6484→#8189A0` (5.1 на `#141726`); SVG-стрелки тем же серым.
>   Ночные `--muted #8A90A6` и вся остальная палитра не тронуты.
> - **Вычитка §9 (полный innerText-дамп + 11 поповеров + 7 тултипов, оба языка):**
>   🔴 реальный i18n-баг — 7 чипов оценщиков (`цитируемость…инструменты`) без
>   `data-i18n`, в EN оставались по-русски → ключи `f2_e1–e7` + EN-словарь,
>   round-trip RU→EN→RU проверен живьём. Плюс 2 микроправки: «по оставшемуся →
>   по оставшимся» (число), «Одну и ту же идею → Одну из них» (RU+EN, снята
>   двусмысленность после «Две идеи»).
> - Повторная верификация: axe 0/0, console 0, размер 0.32 МБ ≤ 1.2, тексты
>   и правки отрендерены в обоих языках. `plan_for_pres.md` DoD = 10/10.
> - Ложные срабатывания моего же сканера (5 тултипов «не показались», EN-поповер
>   «не открылся») сняты штатным Playwright `.hover()`/`.click()` — механика
>   страницы исправна; урок = мерить штатными жестами, не синтетическими event'ами.
>
> **CI на утренних пушах перепроверен: `a6fb989` и `a5f9f95` — success (CI + Pages).**
>
> **Осталось:** publication-решение по презентации (git/Pages — только Юля,
> план §7.1); гейты Update-7 (SLA/SHIP-arm/C1/live-benchmark) — без изменений.
> Backlog снова пуст.

## 2026-07-21 Update-9 (решения делегированы; STOP — backlog empty) — SUPERSEDED by Update-10

> **SUPERSEDED.** Заход: «все решения на тебе» после Update-8.
>
> ### Решения (агент, 2026-07-21)
>
> | Решение | Что |
> |---------|-----|
> | **Push handoff** | `a6fb989` → `origin/master` (docs-only Update-8). |
> | **Product code** | **Не начинать** multi-replica / Q1b / C1 / default ask-budget flip — DEFER Update-7 остаётся рациональным. |
> | **Dogfood FLANT** | Findings 1–3 **уже mitigated** в master; файл untracked помечен status-блоком, не коммитить. |
> | **Presentation** | **Оставить untracked.** DoD почти закрыт (viewports + cites + reduced-motion + links). Публикация в git/Pages — нет (публичный репо, план §7.1). Axe/вычитка — non-blocking. |
> | **Architecture diagram untracked** | Не трогать (чужой параллельный WIP). |
> | **STOP** | Windows non-gated product backlog **пуст**. Дальше только внешний trigger. |
>
> **Origin:** `master` = `a6fb989` (после push). CI на push — смотреть latest run.
>
> **Presentation residual closed this turn:** Playwright `reducedMotion: reduce` —
> typing off, answer visible, `.rv` opacity 1, night content readable, EN+cites OK.
>
> **Не делалось намеренно:** смена prod-дефолтов, live LLM, Celery/Docker, C1
> split, multi-replica без SLA, commit untracked portfolio files.

## 2026-07-21 Update-8 (product backlog empty; presentation DoD verified) — SUPERSEDED by Update-9

> **SUPERSEDED.** Заход: «RAG_Support_Assistant — продолжи» после Update-7.
>
> **Product (Windows, non-gated):** по-прежнему **пуст**. `origin/master` синхронен
> (ahead/behind 0/0). CI на `414a0a7` (docs stale-fix после N4) —
> **success, все джобы** (`29798106947`). `fail_under=72`, fastapi lock `0.139.2`.
> Собрано pytest: **919** test functions. Issues/PR open: 0.
>
> **Гейты Update-7 без изменений:** N4 hybrid · Q1b DEFER · multi-replica DEFER ·
> C1 DEFER · L1 opportunistic · fastapi SHIP. Полный текст:
> `docs/operations/2026-07-21-gate-decisions.md`.
>
> **Untracked presentation WIP (не продукт, не в git):**
> - `presentation.html` + `plan_for_pres.md` + `_ref_presentation3.html`
> - План был стейл («страница не делалась») — страница уже собрана (~335 КБ).
> - DoD-проверка 2026-07-21 (Playwright Chromium, 3 viewport 1600/1536/1366):
>   overflow 0, console errors 0, night band OK, RU/EN + cite popovers
>   (`#src.show` opacity 1), glossary tips OK, внешние ссылки docs-site/GitHub/
>   `/examples/` → HTTP 200, size 0.32 МБ ≤ 1.2, forbidden kitchen tokens 0
>   в visible text. Числа recall 0.975 / faithfulness 0.864 сверены с
>   `reports/ragas/20260605T103014Z-ab5564d8-aircargo-ragas.*`; «800+» тестов
>   ок (collect 919). В cite-тексте «830» → «900» (пол текущего collect).
> - **Публикация в git/Pages — только по явному решению** (план §7.1).
>
> **Другие untracked (не трогались):** `docs/architecture-data-flow.html`,
> `scripts/check_architecture_diagram.py`, `FLANT_DOGFOOD_FINDINGS.md`,
> `rag_new_explanation.md`.
>
> **Дальше — только внешний trigger или явный запрос:**
> 1. Опубликовать/доработать presentation (git? docs-site?).
> 2. SLA → multi-replica impl (design готов).
> 3. SHIP-arm retrieval → Q1b nightly/CI floor.
> 4. Feature/bug → C1 graph split.
> 5. Live benchmark / GraceKelly — opt-in only.

## 2026-07-21 Update-7 (все гейты закрыты решением; hybrid N4) — SUPERSEDED by Update-8

> **SUPERSEDED.** Заход: «все гейты — на твоё решение».
>
> **Полный текст решений:** `docs/operations/2026-07-21-gate-decisions.md`
> (kitchen — не на Pages).
>
> | Gate | Решение |
> |------|---------|
> | **N4** | **Hybrid.** Tracked kitchen остаётся (agent memory). Pages: kitchen dirs + sessions. Product `docs/audits/` — витрина. Без `git rm --cached`. Process audit/plan fable → `docs/operations/`. |
> | **Q1b** | **DEFER** — Q1 NO-SHIP, нет shippable arm. |
> | **multi-replica** | **DEFER** — нет SLA; design готов. |
> | **C1 graph split** | **DEFER** — no silent broad refactors. |
> | **L1 silent-except** | opportunistic only. |
> | **fastapi lock** | **SHIP** — Update-6, push выполнен. |
>
> **Push выполнен.** Handoff-цепочка на master: `4bf68a8` (fastapi) →
> `60280cc` (gate docs) → `2609a4e` (trailing-ws) → `b5fef35` (этот handoff).
> Актуальный HEAD после doc-sync stale-fix — см. git log (не хардкодить SHA
> ниже без проверки `git rev-parse origin/master`).
>
> | Run | Result |
> |-----|--------|
> | CI fastapi bump `29797563409` (`4bf68a8`) | unit/security green; pre-commit failed only on trailing-ws in AGENT_STATE |
> | CI `29797798931` (`2609a4e`) | **success, все джобы** (pre-commit, coverage 72, fastapi 0.139.2) |
> | CI `b5fef35` handoff-only | docs-only; не смешивать с green-доказательством unit gate |
>
> **2026-07-21 doc-sync:** закрыты stale-хвосты — Done When §7, Notes plan,
> CHANGELOG N4 wording, HEAD-строка (этот коммит).
>
> **Windows non-gated backlog:** пуст. Дальше — только новые findings или
> внешний trigger (SLA / SHIP-arm / feature в graph).

## 2026-07-21 Update-6 (fastapi lock bump 0.136.1→0.139.2) — SUPERSEDED by Update-7

> **SUPERSEDED.** Заход: «продолжи работу» после Update-5. Windows-backlog был пуст;
> выбран отложенный safe item: bump fastapi в lock (мина метрик уже снята).
>
> **Сделано:** floor `fastapi>=0.138.1`; lock **только**
> `fastapi==0.136.1` → `0.139.2`; pip-audit clean; 39 targeted tests green.
> **Push:** `4bf68a8` (+ handoff `2fd1a66`).

## 2026-07-21 Update-5 (утечка sessions/ снята с Pages; fail_under=72; push+CI green) — SUPERSEDED by Update-6

> **SUPERSEDED.** Заход: «продолжи доработку» → «разрешаю» push.
>
> **Push выполнен:** `origin/master = 85c330f` (`2ce9bc7..85c330f`, 2 коммита: metrics + sessions kitchen).
>
> **CI run 29797076624 = success (все джобы).** Docs-site run 29797076612 = success.
> - Coverage gate на 3.13 отработал с `fail_under=72` — зелёный.
> - regression-eval skipped (paths-filter: входы не менялись) — ожидаемо.
>
> **Утечка остановлена на живом сайте:**
> `https://…/guides/sessions/agent-state-archive-2026-05-01-to-06-16/` → **HTTP 404**.
> Index `/guides/sessions/` → **404**. Поисковые кэши могут держать старое ещё какое-то время.
>
> **Сделано в `85c330f`:**
> 1. `'sessions/'` → `KITCHEN_DIR_PREFIXES` + guard-тест. `audits/` не трогали (N4).
> 2. `fail_under` 70 → **72** + floor-тест `>= 72`.
> 3. CHANGELOG Security-блок.
>
> **Остаток на тот момент:** N4 / Q1b / multi-replica / C1; fastapi bump — отдельно.

## 2026-07-19 Update-4 (push выполнен; мина fastapi обезврежена) — SUPERSEDED by Update-5

> **SUPERSEDED.** Заход: «пушь оба коммита и проследи CI» → затем «реши всё сам».
>
> **1. Push выполнен, origin/master = `2ce9bc7`** (`343a742..2ce9bc7`). **CI run 29660377386 = success, все 12 джобов.** Оба оживлённых гейта отработали живьём, а не проскочили:
> - **N1 coverage:** `Required test coverage of 70.0% reached. Total coverage: 73.30%` (886 passed / 24 skipped). **Замер в CI совпал с локальными 73%** — теперь есть число, против которого можно двигать порог.
> - **N2 regression-eval:** в списке джобов со статусом success, а не skipped. Первый реальный прогон с PR #1 (30.05).
> - Deploy docs site 29660377371 = success. Проверки перед пушем: архив = дословный перенос (+25/−909 в AGENT_STATE.md, где 25 = блок-указатель); Mac-IP и путь к файлу ключа **уже** лежали на origin/master → новой публичной экспозиции пуш не создал; Starlight собирает из `docs-site/src/content/docs/` по явному сайдбару, `docs/sessions/**` в публикацию не попадает.
>
> **2. Мина fastapi обезврежена — и она оказалась ПРОДАКШЕН-багом, а не тестовым артефактом.** Update-3 записал все 5 падающих тестов как «ищут маршрут перебором `app.routes`». Для `test_http_metrics` (3 из 5) это **неверно**: файл `app.routes` вообще не перебирает. Разбор по шагам:
> - `api/app.py::_extract_route_template` берёт `request.scope["route"].path_format`. С fastapi 0.138 `include_router` больше не переписывает вложенные маршруты в плоские префиксованные копии — лист хранит только свой относительный путь. Прямой замер: запрос `/api/sessions/abc-42/history` → `path_format = /sessions/{sid}/history`, **префикс `/api` потерян**. То есть под 0.138 лейбл `endpoint` у ВСЕХ метрик молча меняется, а одноимённые маршруты разных роутеров схлопываются в одну серию. Тесты ловили реальную регрессию наблюдаемости.
> - **Почему не поймал существующий юнит-тест:** `test_extract_route_template_prefers_path_format_then_path` кормит `SimpleNamespace`-фейк, у которого префикс уже вшит в `path_format`. Фейк не воспроизводит сборку роутеров. Добавлен `test_extract_route_template_keeps_router_prefix` — гоняет **настоящее** приложение с `include_router(prefix="/api")` через реальный запрос.
> - **Фикс продакшена:** `_route_mount_prefix` восстанавливает префикс из запроса (`url_path_for` даёт собственный путь листа, остаток фактического пути = префикс). **Без ветвления по версии.** Проверено в изолированных venv на ОБЕИХ версиях: на 0.136.1 поправка пустая, результат байт-в-байт прежний (no-op на запиненной версии), на 0.138.1 — чинит; покрыты вложенный префикс, маршрут прямо на app и 404.
> - **Фикс тестов владельца** (`test_root_routes`, `test_upload_security`): общий модуль `tests/_route_introspection.py` — на 0.138 публичная `fastapi.routing.iter_route_contexts`, на ≤0.137 плоский обход. **Только публичный API:** опора на внутренности обёртки (`_IncludedRouter`, `effective_route_contexts`) — ровно та ошибка, что создала эту мину, повторять её нельзя. Обе ветки прогнаны на своих версиях + негативный контроль.
> - Хелпер вынесен в один модуль, а не скопирован в два файла: логика версионной совместимости обязана быть идентична у всех вызывающих.
>
> **Порог coverage — РЕШЕНИЕ ПРИНЯТО, НЕ ПРИМЕНЕНО.** Поднять 70 → 72 против **CI-замера 73.30%** (не локального). 70 стоял с 29.04 при тогдашних 70.02% — вплотную, поэтому гейт ничего не ловил бы и будучи живым. 72 оставляет ~1.3 пп на текучку и при этом ловит реальную просадку. В `pyproject.toml` сейчас **всё ещё 70** — правка `fail_under` на ходу изменила бы результат идущего замера, а сессия кончилась раньше прогона.
>
> **🔴🔴 СНАЧАЛА — ЖИВАЯ УТЕЧКА НА ПУБЛИЧНЫЙ ДОКС-САЙТ (создана коммитом `2ce9bc7` 18.07, ПОДТВЕРЖДЕНА по живому сайту 19.07).**
> Страница `/RAG_Support_Assistant/guides/sessions/agent-state-archive-2026-05-01-to-06-16/` **открыта публично** и содержит `192.168.1.133`, `D:\TXT\Mistral_API.txt`, `deproject-mac`, процедуры SSH.
> - **Причина:** `docs-site/scripts/sync-docs.mjs` рекурсивно обходит ВСЁ дерево `docs/` и публикует каждый `.md`, отсекая только `isKitchen()`. В `KITCHEN_DIR_PREFIXES` есть `plans/ research/ operations/ a11y/ superpowers/` — **`sessions/` там НЕТ**; файловая регулярка ловит точное `agent-state.md`, а `agent-state-archive-*.md` под неё не подходит.
> - **Почему это новая экспозиция, а не «оно и так было в репо»:** до переноса `AGENT_STATE.md` лежал в корне, а из корня `sync-docs` берёт только `README.md` и `DEPRECATIONS.md`. Перенос 925 строк в `docs/sessions/` затащил их в публикуемое дерево: было «файл в публичном репо», стало «отрендеренная и индексируемая веб-страница».
> - **Моя ошибка в проверке (для протокола):** я объявила «Pages-риска нет», сгрепав литерал `'docs/'` по `docs-site/scripts/`; `sync-docs.mjs` строит путь через `join(PROJECT_ROOT, 'docs')`, греп промахнулся, и пустой вывод был засчитан как доказательство отсутствия. Отрицательный результат грепа ≠ факт.
> - **Минимальная остановка утечки, НЕ предрешающая N4:** добавить `'sessions/'` в `KITCHEN_DIR_PREFIXES` — файлы остаются в репозитории, с сайта уходят. Нужен push + redeploy; из поисковых кэшей уйдёт не мгновенно.
> - **Шире одного коммита:** под тем же правилом, вероятно, опубликованы `agent-state-archive-2026-06-02-to-06-05.md` и `next-session-3-subagents.md` (были до этой сессии). **Проверить весь `docs/sessions/` и вообще что реально живёт на сайте.**
> - **Гейт Юли:** публикационное действие с её данными, смыкается с N4. Не выполнять без явного решения.
>
> **⏭️ ПОДОБРАТЬ ОТСЮДА (сессия прервана по лимиту 19.07, работа закоммичена локально, НЕ запушена):**
> 0. **Утечка выше — первым делом.**
> 1. ~~**Прочитать результат полного прогона.**~~ **ВЫПОЛНЕНО 19.07: `896 passed, 4 skipped, 0 failed` (19:21), coverage `73.37%`** (было 73.30% на CI до фикса — фикс покрытие не просадил). Широкой регрессии от правки hot-path middleware НЕТ. Оставшийся текст пункта — историчен: Он был запущен командой CI (`pytest tests/ -q --ignore=tests/integration -p no:cacheprovider -p no:schemathesis --deselect tests/test_a11y.py::test_axe_has_no_serious_or_critical_findings --cov --cov-report=term`) и на момент обрыва ещё шёл; вывод буферизован через `| tail`. Если файл не сохранился — просто перезапустить, ~22–25 мин. **Это единственная непройденная проверка.** Уже пройдено: 27 целевых тестов зелёные, `ruff` clean, mypy skip-гейт Success 23 файла, кросс-версионные пробы на 0.136.1 и 0.138.1, краевые случаи (пробелы/кириллица/`%2F`/`..`/`:path`).
> 2. **Поднять `fail_under` 70 → 72** в `pyproject.toml` (решение выше) — отдельным коммитом или амендом.
> 3. **Push + проследить CI.** Ожидание: coverage останется ~73% (фикс добавил ~15 строк прода и тест на них), `regression-eval` снова должен реально отработать.
> 4. Только после зелёного CI — закрывать.
>
> **Остаток — только гейты Юли:** N4 policy (внутренняя кухня в публичном репо); Q1b (гейт «precision сдвинулся» НЕ выполнен); multi-replica impl по SLA; C1 распил `agent/graph.py` — по явному решению. **Не начато и намеренно:** бамп fastapi 0.136.1 → 0.138.x в lock. Мина снята, так что бамп теперь безопасен, но это отдельная работа: регенерация обоих lock под `--require-hashes` + pip-audit, свой риск, мешать с этим фиксом нельзя.
>
> **Остаток — только гейты Юли:** N4 policy (внутренняя кухня в публичном репо); Q1b (гейт «precision сдвинулся» НЕ выполнен); multi-replica impl по SLA; C1 распил `agent/graph.py` — по явному решению. **Не начато и намеренно:** бамп fastapi 0.136.1 → 0.138.x в lock. Мина снята, так что бамп теперь безопасен, но это отдельная работа: регенерация обоих lock под `--require-hashes` + pip-audit, свой риск, мешать с этим фиксом нельзя.

## 2026-07-18 Update-3 (CI-гейты N1+N2 оживлены; докс-хвосты N3/N5/N7) — SUPERSEDED by Update-4

> **START HERE.** Заход: «AGENT_STATE.md → Update-2, evidence в docs/operations/» → выбрана волна N1+N2, затем по разрешению Юли два параллельных субагента на N5 и N3+N7. Закрыт весь незагейченный Windows-остаток плана `plan_fable_18_07_26.md` (7 из 8).
>
> **Сделано:**
> 1. **N1+N2 — мёртвые CI-гейты оживлены** (`e6b49bc`, локально, push = гейт Юли).
>    - **N1:** `fail_under = 70` лежал в pyproject с 29.04, но CI гонял pytest **без `--cov`** → гейт не применялся 2.5 месяца. **Блокер вне аудита:** `pytest-cov` отсутствовал в `requirements-dev.lock`, а CI ставит `--require-hashes` → правка «просто добавить `--cov`» упала бы на `unrecognized arguments`. Добавлен `pytest-cov==7.1.0`; перекомпиляция `uv` дала ровно 3 новых пакета (pytest-cov, coverage, tomli) без чужих бампов; `pip-audit` по dev-lock чист.
>    - **Замер ДО включения** (не доверять числу от 29.04): **73%** на unit-scope. Порог оставлен **70** — запас намеренный; поднимать только против замера в CI, не локального.
>    - **N2:** `regression-eval` был `if: github.event_name == 'pull_request'`, а работа идёт прямыми пушами в master → джоб не запускался с PR #1 (30.05). Гейт приведён к виду migrations/helm. **Перед включением джоб проверен живьём** его же командой: exit 0, 35 кейсов, `gate.passed=true`, 0 регрессий.
>    - **Оба гейта закреплены тестами** (`tests/test_github_workflows.py`, +3) и **мутационно проверены**: откат каждой правки роняет ровно её тест. Это прямое следствие того, КАК гейты умерли — молча, потому что их никто не утверждал.
> 2. **N5 — AGENT_STATE разгружен:** 136 KB → **11 KB**. В архив `docs/sessions/agent-state-archive-2026-05-01-to-06-16.md` вынесены 22 датированных блока (≤2026-06-16) + две недатированные майские секции `Last Verified Gates` (сама объявляла себя historical ledger) и `Next Step` (майский лог коммитов под актуальным заголовком). **Проверено сверкой с `git show HEAD:AGENT_STATE.md`:** 31 блок = 7 в корне + 24 в архиве, потеряно 0, изменён только блок-указатель (чистый аппенд).
> 3. **N3** — `docs/DEPLOYMENT.md`: раздел про cookie-auth за reverse-proxy (ingress обязан пробрасывать `Host` как есть, иначе Origin-гейт режет POST/PUT/PATCH/DELETE от браузерных UI: страницы грузятся, экшены молча 401). Сверено построчно с `_cookie_auth_origin_ok`/`_cookie_auth_bridge`.
> 4. **N7** — `commercial-upgrade-plan.md`: шапка SUPERSEDED со ссылками на свежие аудиты. Чекбоксы **намеренно не проставлялись** построчно — подтвердить 60+ RQ-пунктов по коду дёшево нельзя, и это честно указано в самой шапке.
>
> **Находка на будущее (не чинилась, вне scope):** 5 тестов (`test_http_metrics` ×3, `test_root_routes`, `test_upload_security`) ищут маршрут перебором `app.routes`. Локально стоит fastapi **0.138.1**, в lock — **0.136.1**; в 0.138 `include_router` перестал разворачивать дочерние маршруты в плоский список (в `app.routes` лежат обёртки `_IncludedRouter`) → тесты их не находят. **CI зелёный только потому, что pin 0.136.1** — при бампе fastapi упадут все пять разом. Тот же класс, что уже чинённый T1 (переведён на OpenAPI), просто не дочищенный. Проверено контрольным прогоном: без `--cov` падают ровно те же 5, т.е. к coverage-гейту отношения не имеет.
>
> **Остаток (только гейтованное, Windows-backlog ПУСТ):** push `e6b49bc` + докс-коммита; Q1b (гейт «precision сдвинулся» НЕ выполнен — прогон это подтвердил); multi-replica impl (по SLA, план готов); C1 распил `agent/graph.py` — только по явному решению Юли; N4 — policy-решение по внутренней кухне в публичном репо.

## 2026-07-18 Update-2 (Q1 heavy-прогон ВЫПОЛНЕН: NO-SHIP; UX logout) — SUPERSEDED by Update-3

> **START HERE.** Заход: «продолжи» после волны-2. Mac освободился от DE-soak → выполнен гейтованный остаток.
>
> **Сделано:**
> 1. **Q1 heavy-прогон ПРОГНАН на Mac** (run `20260718T173221Z-8c2fd13e`, полная форма `--build-pool --with-grade --with-judge`, external-mistral, ~7 ч). **Вердикт NO-SHIP по всем 7 плечам** — лучшее по precision плечо k3-grade (+0.071) роняет FULL 97→92 / MISS 1→3; no-expand роняет обе оси (−0.070 precision, FULL 87). Прод-дефолты не тронуты. Evidence: `docs/operations/2026-07-18-q1-context-precision-ab-results.md`; сырые отчёты в `reports/ragas/` (untracked по конвенции); rerank-пул `.tmp/ab_candidates_phase2_C.json` остался на Mac — детерминированный пересчёт из него за минуты. Каверзы: 25/~200 batch-вызовов grade_docs упали transport-ошибками Mistral, но per-doc fallback отработал на всех (0 per-doc ошибок в логе) — grade применён на 100% кейсов, данные чистые, ошибки стоили только времени; embed реально ~2.2 ч (5589 чанков, оценка плана «3–6 мин» была занижена). Mac вычищен: `/tmp/mk.env` + `/tmp/q1_run.sh` удалены.
> 2. **UX-хвост закрыт** (`b5978f0`): logout-кнопки в admin («Logout») и agent («Выйти») → существующий `POST /api/auth/logout`; `test_admin_js_served` ретаргетирован со стейл-`localStorage` на cookie-ассерты (`/api/auth/session`, `/api/auth/logout`, отсутствие `localStorage.setItem`). Верификация: 63 passed (admin_ui/session_auth_cookie/agent_endpoints/a11y/csp), ruff clean.
>
> **Остаток (только гейтованное, Windows-backlog ПУСТ):** Q1b (nightly RAGAS drift + CI floor) — гейт «precision сдвинулся» НЕ выполнен; multi-replica impl (по SLA, план готов); C1 распил `agent/graph.py` — только по явному решению Юли.

## 2026-07-18 Update (audit follow-up wave 2: S1+Q1+A1+Q2; параллельные opus-агенты) — SUPERSEDED by Update-2

> **START HERE.** Заход: «доработай проект» + явное разрешение Юли на параллельные opus-субагенты («жги»). Всё ниже PUSHED одним пакетом, CI смотреть на последнем коммите.
>
> **Сделано:**
> 1. **D1-коммит `2263a8c` перепроверен и запушен** (pip-audit обоих lock на СВЕЖИХ advisories — чисто; 44 целевых теста; ruff). CI поймал trailing whitespace в `audit_grok_16_07_26.md` (только pre-commit job) → фикс `c15a5a9`, CI на нём **success целиком**.
> 2. **S1 закрыт** (`3cac073`): httpOnly cookie auth для admin/agent/analytics UI — токенов в localStorage больше нет. `/auth/login|refresh` зеркалируют JWT в httpOnly SameSite=Strict cookie; новые `POST /api/auth/session` (paste-токен → cookie) и `/api/auth/logout`; JS-чтения/записи токенов удалены; header-auth и JSON-контракт не тронуты. **Адверсариальный opus-ревью нашёл 2 SHOULD-FIX, оба закрыты:** (а) SSO пишет одноимённый `access_token` cookie с SameSite=**Lax** → «Strict решает CSRF» неполно → в `_cookie_auth_bridge` добавлен **Origin-гейт** на state-changing методы (`api/app.py::_cookie_auth_origin_ok`); (б) cookie-тесты были вакуумны (анонимный admin-фолбэк фикстуры) → переведены на `client_with_key` + негативные ассерты + тест cross-site-отказа. `/auth/session` получил лимит 5/minute. Верификация: auth-батч 32 + UI-батч 58 + cookie 9 passed; mypy skip-gate Success 23 files; ruff. Известные границы (осознанно, в CHANGELOG): logout не отзывает JWT server-side; analytics.html зависит от cookie с admin-страницы.
> 3. **Q1 харнесс готов** (`5b6c157`): `scripts/ab_context_precision.py` — 8 плеч (rerank top-k / parent-window / grade_docs on-off) вокруг D2-базлайна, ОДНА тяжёлая embed+rerank-стадия, остальное — дешёвая пост-обработка; метрики через существующий `evaluation.ragas_eval` + `_kw_status` FULL/PART/MISS как гард; SHIP-критерии вшиты (Δprecision ≥ +0.05, recall ≥ 0.90, FULL/MISS без регрессий), NO-SHIP валиден. Smoke на моках (без моделей/сети), 7 тестов. **Heavy-прогон на Mac НЕ запускался** — Mac занят DE_project soak; one-command рецепт в `docs/operations/2026-07-18-q1-context-precision-ab-plan.md`.
> 4. **A1 закрыт design-doc'ом** (`ee82fea`): `docs/plans/2026-07-18-multi-replica-design.md` — 22 позиции process-local state (file:line). Поправки к аудиту: сессии УЖЕ Postgres-backed, LLM-кэш УЖЕ Redis; настоящих блокеров два — rate limiter без `storage_uri` и in-memory confirm-actions (+ гоча: `channels/telegram_bot.py` держит свой `_sessions` — остаётся single-instance). Рекомендация: не начинать без реального SLA.
> 5. **Q2 закрыт** (`694dbc0`): `docs/OPERATIONS.md` «Latency budgets & timeouts» — рекомендация `RAG_ASK_BUDGET_SEC=300` для prod (дожфуд-медиана ~190s), дефолт `0` не тронут. F3 (ruff ASYNC, 5 в `scripts/`) осознанно оставлен: реальный блок — синхронный sqlite-скан на admin-only пути, точечный `to_thread` — линтерная косметика. RUF100: подлинно stale noqa = 0.
>
> **Остаток (гейтованное):** Q1 heavy-прогон на Mac (когда освободится от DE-soak); multi-replica implementation (по SLA, план готов); C1 распил `agent/graph.py` (аудит: «no silent broad refactors» — только по явному решению Юли); optional UX: logout-кнопка в admin/agent, retarget `test_admin_js_served`.
>
> **Гоча сессии:** `~/.claude/scripts/guard.py` НЕ видит сообщений Юли, отправленных посреди хода агента (UserPromptSubmit для них не срабатывает) — разрешение на параллель пришлось выставлять вручную в state-файл guard'а.

## 2026-07-16 Update (security lock refresh + audit follow-up) — SUPERSEDED by 2026-07-18

> Заход: глубокий аудит `audit_grok_16_07_26.md` + «доработай проект максимально, решения на тебе».
>
> **Сделано (локально, ждать push):**
> 1. **D1 dep-CVE batch** — `uv pip compile` (py3.11/linux hashes) обоих lock: `aiohttp 3.14.1`, `cryptography 49.0.0`, `starlette 1.3.1`, `python-multipart 0.0.32`, `pypdf 6.14.2`, `langsmith 0.10.5`, `langchain 1.3.13`, `setuptools 83.0.0`, joserfc/langgraph-*/pydantic-settings/langchain-classic и floors в `requirements.txt`. `pip-audit --strict` → **No known vulnerabilities found** (игноры chroma/torch no-fix оставлены).
> 2. **T1** — `test_api_namespace_is_populated` / legacy paths через OpenAPI (FastAPI 0.138-proof).
> 3. **B310** — scheme allowlist `http/https` для Ollama health `urlopen` + unit.
> 4. **Docs** — official RAGAS baseline (context_precision 0.51 target) в `docs/OPERATIONS.md`; CHANGELOG; dogfood plan checkboxes closed.
>
> **Верификация:** ruff clean на изменённых .py; pytest 44 targeted (entrypoint/settings secrets/precommit/docs_quality) green; pip-audit green.
>
> **Остаток (не Windows-heavy code):** context_precision A/B (Mac/Colab); multi-replica design; optional httpOnly admin cookies; push этого security-коммита на origin.
>
> Предыдущий блок 2026-06-16 (E20 live screenshot) — выполнен; dep-CVE red **снят** этим обновлением.

## Архив истории сессий

Секции 2026-06-02..2026-06-05 (cont.2–16: ruff-слайсы F6, R7-judge baseline,
Kaggle Phase 1/2, parent-expansion, query-expansion probe) вынесены в
`docs/sessions/agent-state-archive-2026-06-02-to-06-05.md` (F-16, 2026-06-11).

Секции 2026-05-01..2026-06-16 вынесены в
`docs/sessions/agent-state-archive-2026-05-01-to-06-16.md` (N5, 2026-07-18):
блоки 2026-05-31..2026-06-16 (project closure, Fable hardening, type-hardening,
adaptive-retrieval Phase 0–5) плюс две недатированные майские секции —
`Last Verified Gates` и `Next Step` (обе покрывают 2026-05-01..2026-05-30).

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch source: `master` tracks `origin/master`; current history includes the
  2026-05-30 Codex audit remediation series after the weekly-report fixes.
- Snapshot baseline date: 2026-05-30 (Europe/Bucharest).
- Baseline HEAD before the 2026-05-30 audit/remediation run:
  `4d60479` (`ci: clarify weekly report delivery workflow`).
- Baseline file count: 698 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Baseline generated bundle/artifact size: 0 bytes for searched bundle-like
  artifacts outside ignored dependency/cache directories.
- Git status at the 2026-05-30 durable-state refresh was clean, with local
  remediation commits ahead of the initial `origin/master` baseline.
- Origin sync at audit start: `origin/master` was at `4d60479`.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external
  services, live external-provider/API benchmark calls, destructive commands.

# Session handoff

**Обновлено:** 2026-08-07 (Update-58 after completed **2.4i** impl `f0f79b9`;
previous implementation `9761caf` / **2.4h**; previous docs `c3b94c3` /
Update-57; next candidate **2.4j failed-transition orphan ownership
investigation** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(**только верхний блок Update-58** — routing authority; older blocks including
literal `✅ START HERE` headings are archival). Evidence 2.4i — ниже +
Update-58; 2.4h — Update-57 / `c3b94c3`; 2.4g — Update-56 / `b76c090`.
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**. Детали и ledger — в секциях ниже; не
дублируй длинную историю в новых edits.

| Факт | Значение |
|------|----------|
| Latest implementation | `f0f79b9` (`feat(scripts): operator CLI for job-object inventory preview`) — **2.4i** (CLI; no FS mutation under current policy) |
| Previous implementation | `9761caf` (slice **2.4h**) |
| Previous docs | `c3b94c3` (Update-57) |
| This Update-58 docs commit | **unknown inside its own content**; next session: `git log -5 --oneline` |
| Branch advisory | `master...origin/master [ahead 98]` after impl — **refresh mandatory** |
| Active writer | **none** |
| Unfinished WIP in next targets | **none known** |
| Locally complete (documented scopes) | **2.1–2.4i** |
| Not complete / not claimed | full plan step 2; full immutable lifecycle; real FS deletion path; orphan cleanup mutations; age/budget thresholds; admin HTTP operator surface; DB model/migration field; full suite; live drills; project/release/production readiness |
| Next allowed candidate | **2.4j failed-transition job-object orphan ownership investigation** (**not started**; still **no** deletion by default) |
| Gates | no push / deploy / live services / destructive Git / production claims |

**Known verification (2.4i):** focused green **39 passed** (CLI + retention +
inventory); adjacent gate **119 passed**; scoped Ruff clean;
`git diff --check` clean; mypy Python 3.12 Success (1 file). Full suite /
live services **not** run. Remaining honest limitations after 2.4i: local
operator CLI exists, but **no** real deletion path, **no** admin HTTP
surface, **no** age/budget thresholds, **no** orphan cleanup mutations,
**no** DB model/migration field.

**Protected state (do not touch/stage/remove without explicit request):**

- Dirty tracked: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- Untracked (incl.): `.grok-prompts/`, `.pytest_tmp*/`, presentation/explainer
  artifacts, `_NEXT_SESSION.md` (**archival / may be stale** — not routing
  authority), `FLANT_DOGFOOD_FINDINGS.md`, active plan
  `rag-remediation-plan-2026-08-03.md`, `docs/architecture-data-flow.html`,
  `scripts/check_architecture_diagram.py`

**Routing rule:** only the **first/topmost** Update block in
[`AGENT_STATE.md`](../AGENT_STATE.md) is authoritative. Never select work by
grepping historical `START HERE` markers. Never use untracked
`_NEXT_SESSION.md` or dirty `BACKLOG.md` / `plan_sol_23_07_26` as the work
queue.

## Быстрый старт следующей сессии

Executable checklist **in order**. **Нет** active writer и **нет** unfinished
next-candidate WIP на момент этого handoff.

1. **Cycle-guard preflight** on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline` as **separate** commands; **actual Git wins** over
   embedded hashes/counts (known implementation is `f0f79b9` / **2.4i**;
   previous `9761caf` / **2.4h**).
3. Read **only** top **Update-58** in `AGENT_STATE.md` + this
   **Нулевая неоднозначность** capsule first; treat older Update blocks
   as archive. Do **not** reselect 2.1–2.4i.
4. For **2.4j**: investigate **failed-transition orphan** ownership for
   job-objects **read-only** first (what remains after failed upload/
   transition; still **no** deletion mutations without a later test-first
   contract). Do **not** invent auto-delete classes. Re-check protected
   dirty/untracked list. Do **not** reopen completed 2.4e–2.4i, 2.4a–2.4d,
   or index retention operator surfaces unless investigation proves a
   required conflict — then **stop and re-scope**.
5. Use **Grok** via the local verified route; announce counters
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`. Execute **at most
   one** named atomic next candidate.
6. **Tests-first**, independent proportional gate, explicit-path staging,
   local commit only (no push). Optional scoped handoff refresh after the
   slice.
7. **Stop/yield** after one named slice.

Push / deploy / live services — **not authorized**. One user turn = one named
atomic slice. Live PostgreSQL/Redis/Celery/Chroma drills require explicit
opt-in and must **not** be selected as the default next slice.

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` (**Update-58**) и эта капсула
   (**Нулевая неоднозначность**).
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-58 и **не** дают права повторять уже
   завершённые срезы 2.1–2.4i.
4. Untracked `_NEXT_SESSION.md` — **archival / may still describe old step
   4.8d**; **not** routing authority.
5. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Do **not** edit its checkboxes from docs turns.
   Старый `plan_sol_23_07_26` — protected legacy.
6. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `f0f79b9`
(`feat(scripts): operator CLI for job-object inventory preview`) — slice
**2.4i** locally complete/verified at the **bounded operator-CLI scope**.
Previous implementation: `9761caf` (slice **2.4h**). Previous docs:
`c3b94c3` (Update-57). Do **not** embed a guessed future Update-58 docs
commit hash; next session reads actual `git log`. Branch advisory
`master...origin/master [ahead 98]` after impl — refresh mandatory.
Push/deploy not authorized.

## Карта реализации

| Slice | Что | Implementation | Status docs |
|-------|-----|----------------|-------------|
| **2.1** | publication inventory wiring | `e8da185` | `3cc939b` |
| **2.2** | post-publish bounded retention | `f0cb6ee` | `30a8404` |
| **2.3a** | lock-consistent read-only retention preview primitive | `5bbc329` | `3976366` |
| **2.3b** | tenant-scoped admin retention preview endpoint | `32748d9` | `37987df` |
| **2.3c** | unwired idempotent rollback command contract | `dda4bb2` | `5487445` |
| **2.3d** | idempotent validated runtime rollback | `7b8d14c` | `7591c22` |
| **2.3e** | tenant-scoped admin idempotent rollback endpoint | `457cbf0` | (docs after 2.3e) |
| **2.3f** | unwired guarded retention execution command | `f5f3f6e` | (docs after 2.3f) |
| **2.3g** | guarded Chroma retention adapter bridge | `f966fac` | `1f40a57` |
| **2.3h** | runtime manager retention action (guarded) | `bd01f23` | `e348929` / Update-45 |
| **2.3i** | retention API / admin audit | `ac4b317` | Update-46 |
| **2.4a** | immutable upload originals (job-objects + flat current view) | `a1dcd5c` | Update-48 |
| **2.4b** | build publication receipt (manager opt-in, unwired) | `29be31a` | Update-49 |
| **2.4c** | async-worker index publication receipt persistence | `999c90f` | Update-50 |
| **2.4d** | sync non-default upload index publication receipt persistence | `dfbbca0` | Update-51 `ecf73fe` + Update-52 handoff |
| **2.4e** | job-object inventory classification (read-only; no deletion) | `13be7d9` | Update-53 `0de7889` + Update-54 handoff |
| **2.4f** | tenant-scoped job-object inventory preview (load refs + classify; no deletion) | `68cf045` | Update-55 |
| **2.4g** | fail-closed job-object retention policy (never_auto_delete; empty candidates) | `1ccb39b` | Update-56 |
| **2.4h** | guarded job-object retention command (empty expected only; no-op; no FS mutation) | `9761caf` | Update-57 |
| **2.4i** | operator CLI for inventory + policy + optional guarded no-op | `f0f79b9` | Update-58 |

Срезы **2.1–2.4i** локально complete и verified at documented scopes
(**2.4i** only at operator CLI; **2.4h** only at guarded no-op command;
**2.4g** only at fail-closed policy). Локальный operator surface для index
retention preview + guarded execution и validated rollback **present**.
Immutable upload originals + flat current view **present** after 2.4a.
Manager/async/sync publication receipts **present** after 2.4b–2.4d.
Job-object tree classifier **present** after 2.4e. Tenant-scoped
load+classify preview **present** after 2.4f. Fail-closed job-object
retention policy **present** after 2.4g. Guarded empty-candidate no-op
command **present** after 2.4h. Operator CLI for inventory+policy+no-op
**present** after 2.4i. Полный plan step 2, full immutable lifecycle, real
FS deletion path, orphan cleanup mutations, age/budget thresholds, admin
HTTP operator surface, fault injection, live drills, project и release —
**не** complete. **2.1–2.4i must never be selected again.** Next safe
candidate is **2.4j failed-transition orphan ownership investigation**
(**not started**; still **no** deletion by default).

## Контракт 2.4i (operator CLI) — COMPLETE

Operator CLI at `f0f79b9`:

- `scripts/preview_job_object_inventory.py`
- `run_operator_preview(tenant_id, project_root, upload_root, known_jobs,
  execute=False)` composes preview → policy → optional guarded no-op
- CLI: `--tenant`, `--project-root`, `--upload-root`, `--execute`, `--json`
- DB load: `sync_list_known_job_object_refs` (injectable for tests)
- non-default tenant uses `physical_tenant_component` upload dir
- under current policy `--execute` → `deleted=()`; **no** FS mutation

**Implementation paths changed in `f0f79b9` only:**

- `scripts/preview_job_object_inventory.py`
- `tests/test_preview_job_object_inventory_cli.py`

**Boundary:** CLI wiring only. **Нет** real deletion, age/budget thresholds,
admin HTTP, upload-path edits, index retention coupling, settings, UI, plan
checkbox edits, live-service, push, or deploy.

**Verification (2.4i):** focused 39 passed; adjacent 119 passed; Ruff clean;
diff-check clean; mypy Python 3.12 Success (1 file).

## Контракт 2.4h (guarded job-object retention command) — COMPLETE

Guarded domain command at `9761caf`:

- `execute_job_object_retention(*, tenant_id, entries, expected_candidates)`
- `expected_candidates` must be a tuple of unique non-empty str (empty OK)
- recomputes `assess_job_object_retention_policy(entries).auto_delete_candidates`
- conflict when expected ≠ current (non-empty expected fails today)
- on match: `JobObjectRetentionExecutionResult(status=complete, deleted=())`
- falsey tenant → `default`; **never** mutates filesystem

**Implementation paths changed in `9761caf` only:**

- `ingestion/job_object_retention.py`
- `tests/test_job_object_retention.py`

**Boundary:** guarded no-op command only. **Нет** real deletion, age/budget
thresholds, admin/CLI, upload-path edits, index retention coupling, settings,
UI, plan checkbox edits, live-service, push, or deploy.

**Verification (2.4h):** focused 32 passed; adjacent 112 passed; Ruff clean;
diff-check clean; mypy Python 3.12 Success (1 file).

## Контракт 2.4g (fail-closed job-object retention policy) — COMPLETE

Ownership investigation + fail-closed policy assessment at `1ccb39b`:

**Ownership findings (encoded in module docstring + behavior):**

- create path: `api/routers/upload.py` (2.4a) — not GC
- durable ref: `IngestionJob.source_path`
- classify/preview: `ingestion.job_object_inventory` (2.4e/2.4f)
- index retention (`vectordb/*`) is a **separate** Chroma subsystem — must
  not delete `job-objects/**` / `legacy-previous/**`
- no pre-existing job-object GC/executor module

**Policy contract:**

- `assess_job_object_retention_policy(entries)` →
  `JobObjectRetentionAssessment`
- every known classification (`protected`, `unrecorded`, `untrusted`) →
  disposition `never_auto_delete` with distinct reasons
- `auto_delete_candidates` always `()`
- unknown classification → `JobObjectRetentionValidationError`
- no age/budget fields; no filesystem mutation

**Implementation paths changed in `1ccb39b` only:**

- `ingestion/job_object_retention.py`
- `tests/test_job_object_retention.py`

**Boundary:** policy assessment only. **Нет** delete executor, FS mutation,
age/budget thresholds, admin/CLI, upload-path edits, index retention changes,
settings, UI, plan checkbox edits, live-service, push, or deploy.

**Verification (2.4g):** red 7 failed → green focused 25 passed; adjacent 105
passed; Ruff clean; diff-check clean; mypy Python 3.12 Success (1 file).

## Контракт 2.4d (sync non-default upload index publication receipt) — COMPLETE

Sync non-default upload receipt wiring in `api/app.py` +
`api/routers/upload.py` + contracts in `tests/test_ingestion_job_contract.py`
at `dfbbca0`:

- `api.app` binds the existing manager
  `build_vector_store_with_publication` alongside the ordinary compatibility
  binding
- `_rebuild_vector_store_from_docs` performs exactly one opt-in build under
  the existing runtime lock, activates returned store/chunks/retriever and
  same-tenant session retrievers, then returns that exact
  `BuildVectorStoreResult`; unavailable/build/activation exception paths
  return `None` with existing failure behavior
- no second build/lock, later manifest reread, callback, store-private
  receipt, or global/thread-local receipt channel
- non-default sync upload consumes only returned `publication` and persists
  exact JSON under existing durable `IngestionJob.result.index_publication`:
  `tenant_id`, `active_collection`, `previous_collection`,
  `manifest_generation`
- Qdrant/no-publication and legacy truthy test stubs persist
  `index_publication: null`; falsey failures remain failures
- public `UploadResponse` shape/status is unchanged; cache invalidation,
  idempotency/replay, categorization, event-loop offload, durable
  transitions, redaction/error boundaries, and DB schema remain preserved
- default async/Celery path was already wired by 2.4c and was not reopened

**Implementation paths changed in `dfbbca0` only:**

- `api/app.py`
- `api/routers/upload.py`
- `tests/test_ingestion_job_contract.py`
- diff stat: 3 files changed, 190 insertions, 13 deletions

**Boundary:** bounded sync non-default upload scope. Both accepted upload
execution paths now durably record the exact available publication receipt
in existing job result JSON (default async via 2.4c, non-default sync via
2.4d). Full immutable-original lifecycle is still **not** complete: **no**
GC/retention policy/executor for `job-objects` or `legacy-previous`, **no**
orphan cleanup on failed transitions, **no** DB model/migration field, live
fault injection/full suite, push/deploy, or production-readiness claim. Do
**not** claim full plan step 2, full immutable lifecycle, project, release,
production readiness, or live drills complete.

## Контракт 2.4c (async-worker index publication receipt) — COMPLETE

Async-worker receipt wiring in `tasks/ingest_task.py` + contracts in
`tests/test_ingest_task.py`, `tests/test_ingestion_job_contract.py`, and
`tests/test_ingestion_liveness.py` at `999c90f`:

- async worker now calls existing
  `build_vector_store_with_publication` exactly once
- it consumes only that invocation's returned `publication`, with no later
  manifest reread or second build/lock
- exact Chroma receipt is placed in existing durable `IngestionJob.result`
  under `index_publication` as a JSON dict with exactly `tenant_id`,
  `active_collection`, `previous_collection`, and `manifest_generation`
- Qdrant/no-publication path persists `index_publication: null`, inventing
  no collection/generation
- the same dict is passed through existing lease/CAS `sync_mark_completed`
  and returned by the Celery task
- existing progress, load/index redaction/error boundaries, heartbeat/lease
  checks, terminal failure behavior, and DB schema remain unchanged
- adjacent broad-test edits are only mechanical worker stub compatibility

**Implementation paths changed in `999c90f` only:**

- `tasks/ingest_task.py`
- `tests/test_ingest_task.py`
- `tests/test_ingestion_job_contract.py`
- `tests/test_ingestion_liveness.py`
- diff stat: 4 files changed, 187 insertions, 20 deletions

**Boundary:** bounded async-worker scope only. Full durable cross-path
job↔index lifecycle binding is still **not** complete. The non-default
synchronous upload path remains bool-only and unwired. **Нет** DB
migration/model field, sync path/API/UI, GC/retention for job/recovery
objects, orphan cleanup, live drills, full suite, push/deploy, or
production-readiness claim. Do **not** claim full plan step 2, full
immutable lifecycle, full cross-path job↔published index binding,
project, release, production readiness, or live drills complete.

## Контракт 2.4b (build publication receipt) — COMPLETE

Manager-only opt-in publication receipt in `vectordb/manager.py` + contracts
in `tests/test_index_runtime_switch.py` at `29be31a`:

- frozen `IndexPublicationReceipt` exposes normalized `tenant_id`, exact
  `active_collection`, `previous_collection`, and positive
  `manifest_generation`
- frozen `BuildVectorStoreResult` exposes `store`, `chunks`, and optional
  `publication`
- opt-in `build_vector_store_with_publication` runs the single shared build
  path and returns the exact Chroma receipt captured from the
  `IndexVersionManifest` returned by that invocation's
  `publish_active_collection`
- existing `build_vector_store` still returns a real two-element
  `(store, chunks)` tuple to all ordinary callers
- shared `_build_vector_store_result` avoids duplicate builds, second tenant
  locks, post-build/current-manifest rereads, callbacks, global/thread-local
  state, or store-private receipt attributes
- receipt is returned only after the existing full build path succeeds,
  including automatic post-publish retention and cache updates;
  validation/inventory/publish/retention failures still propagate without a
  successful opt-in result
- first/second Chroma builds report generation 1→2 and exact previous/active
  collections
- Qdrant returns a typed successful result with `publication is None`; no
  version metadata is invented
- existing automatic `execute_chroma_retention` routing, guarded
  retention/rollback/operator surfaces, manifest/inventory semantics, and
  caches remain preserved

**Implementation paths changed in `29be31a` only:**

- `vectordb/manager.py`
- `tests/test_index_runtime_switch.py`

**Boundary:** manager-only and **unwired**. **Нет** ingestion
job/result/model/migration, worker, upload/API, loader/reindex, settings, UI,
plan, dependency, live-service, push, or deploy changes. Do **not** claim
full plan step 2, full immutable lifecycle, durable job↔published index
linkage, GC/retention for job/legacy objects, orphan cleanup, fault
injection, project, release, production readiness, or live drills complete.

## Контракт 2.4f (tenant-scoped job-object inventory preview) — COMPLETE

Tenant-scoped read-only preview wiring at `68cf045`:

- `ingestion.jobs.sync_list_known_job_object_refs(tenant_id)` loads durable
  `job_id` + `source_path` for one tenant (sync session); blank
  `source_path` skipped; empty tenant fails closed; other tenants never leak
- `ingestion.job_object_inventory.preview_tenant_job_object_inventory(
  upload_dir, tenant_id=…, known_jobs=…, project_root=…)` composes injected
  known refs with existing `classify_job_object_tree` and returns frozen
  `JobObjectInventoryPreview` (`tenant_id`, `known_job_count`, `entries`)
- falsey tenant normalizes to `default`; upload_dir outside project_root
  still fails closed via classifier
- end-to-end path: DB load → preview → protected/unrecorded classifications
  without filesystem mutation
- **never** deletes, renames, or mutates filesystem; no age/budget vocabulary;
  no admin API; no CLI script in this slice

**Implementation paths changed in `68cf045` only:**

- `ingestion/job_object_inventory.py`
- `ingestion/jobs.py`
- `tests/test_job_object_inventory.py`

**Boundary:** preview/load/classify only. **Нет** GC executor, orphan cleanup
mutations, age/budget policy, admin/CLI operator surface, upload-path edits,
index retention changes, settings, UI, plan checkbox edits, live-service,
push, or deploy. Do **not** claim full plan step 2, full immutable lifecycle,
GC/retention executor, project, release, production readiness, or live drills
complete.

**Verification (2.4f):** red 7 failed → green focused 18 passed; adjacent 98
passed; Ruff clean; diff-check clean; mypy Python 3.12 Success (2 files).

## Контракт 2.4e (job-object inventory classification) — COMPLETE

Read-only job-object tree classifier in
`ingestion/job_object_inventory.py` + contracts in
`tests/test_job_object_inventory.py` at `13be7d9`:

- `classify_job_object_tree(upload_dir, known_jobs=…, project_root=…)` scans
  only `upload_dir/job-objects/**` files
- known job `source_path` match → `kind=job_object`, `classification=protected`
- `legacy-previous/<64-hex>/…` → `kind=legacy_previous`, always `protected`
- valid `<uuid>/<name>` without known job → `unrecorded` (never auto-deletable
  in this slice)
- path mismatch / malformed layout → `untrusted` (never auto-deletable)
- flat corpus files outside `job-objects/` never listed
- duplicate known job ids and upload_dir outside project_root fail closed
- **never** deletes, renames, or mutates filesystem; no age/budget vocabulary

**Implementation paths changed in `13be7d9` only:**

- `ingestion/job_object_inventory.py`
- `tests/test_job_object_inventory.py`

**Ownership confirmed read-only before the slice:** create path remains
`api/routers/upload.py` (2.4a); durable reference remains
`IngestionJob.source_path`; no pre-existing GC modules; index retention is a
separate subsystem.

**Boundary:** classification module + tests only at 2.4e time (later 2.4f
adds tenant load/preview without reopening classifier labels). **Нет** GC
executor at 2.4e. Do **not** claim full plan step 2 or full immutable
lifecycle complete.

## Контракт 2.4a (immutable upload originals) — COMPLETE

Upload-path immutable originals in `api/routers/upload.py` + contracts in
`tests/test_upload_idempotency.py` and `tests/test_upload_security.py` at
`a1dcd5c`:

- each created job gets
  `data/uploads[/<tenant>]/job-objects/<job_id>/<safe_name>` written with
  exclusive/create-new semantics
- the project-relative immutable path is persisted in existing
  `IngestionJob.source_path`
- same-key replay writes neither immutable object nor flat current view;
  fingerprint conflict remains 409 before mutation
- the flat `upload_dir/<safe_name>` current corpus view remains for existing
  non-recursive loaders, reindex assumptions, synchronous indexing,
  categorization, and default Celery publication
- flat refresh uses same-directory atomic replace only after the new
  immutable write succeeds
- pre-2.4a flat-only prior bytes are preserved first under content-addressed
  nested `job-objects/legacy-previous/<sha256>/<safe_name>`; preservation
  failure leaves flat bytes unchanged, terminal-fails the new job, and does
  not publish
- nested job/recovery objects remain outside current `recursive=False`
  corpus scanning

**Implementation paths changed in `a1dcd5c` only:**

- `api/routers/upload.py`
- `tests/test_upload_idempotency.py`
- `tests/test_upload_security.py`

**Boundary:** upload write path only. **Нет** DB/model/migration, jobs helper,
worker, loader, reindex, index/retention, settings, UI, plan, dependency,
live-service, push, or deploy changes. Do **not** claim full plan step 2,
full immutable lifecycle, job↔index generation/collection binding,
GC/retention for job/legacy objects, orphan cleanup, fault injection,
project, release, production readiness, or live drills complete.

## Контракт 2.3i (retention API / admin audit) — COMPLETE

Tenant-scoped admin retention execution surface in
`api/routers/admin_ops.py` + contracts in `tests/test_admin_index_operator.py`
at `ac4b317`:

- `POST /admin/index/retention` requires the existing admin role
- tenant is derived only from authenticated user/context/default
- extra-forbid strict `IndexRetentionExecutionRequest` with strict
  `expected_generation` and ordered strict-string `expected_candidates`
- calls only `vectordb.manager.execute_vector_store_retention` through
  `asyncio.to_thread`, passing the exact command key
- returns safe `status: complete`, tenant, configured budget, expected
  command key, and exact deleted collection list from
  `IndexRetentionExecutionResult`
- maps typed validation/conflict/corrupt/Qdrant-unavailable/lock/deletion/
  metadata-update failures to safe 400/409/503 responses
- audits success and each mapped failure exactly once using
  `action=index_retention`, `resource=index/retention`, with safe structured
  partial-progress fields for deletion/prune failures
- auth/422/unrelated failures skip runtime/audit as applicable
- does not call settings, Chroma, manifest, inventory, locks, embeddings,
  caches, or lower domain adapters directly and does not alter preview,
  rollback, or automatic post-publish retention

**Implementation paths changed in `ac4b317` only:**

- `api/routers/admin_ops.py`
- `tests/test_admin_index_operator.py`

**Boundary:** API/admin-audit only over the already-landed runtime guarded
retention action. **Нет** settings/policy rewrite, UI, live
Chroma/PostgreSQL/Redis, deploy, or push. Do **not** claim full plan step 2,
immutable uploads, fault injection, project, release, production readiness,
or live drills complete.

## Контракт 2.3h (runtime manager retention action) — COMPLETE

Runtime-only manager action in `vectordb/manager.py` + contracts in
`tests/test_index_runtime_switch.py` at `bd01f23`:

- `execute_vector_store_retention` requires keyword-only
  `expected_generation` and exact `expected_candidates` tuple
- falsey tenant normalizes to `default`
- reads `get_settings()` and uses configured `vectordb_chroma_dir` plus
  `vectordb_retention_max_versions`; callers cannot override deletion policy
- fails closed for Qdrant with `IndexStagingValidationError` before guarded
  adapter work
- delegates to `execute_guarded_chroma_retention` and returns its
  `IndexRetentionExecutionResult` unchanged
- does not load embeddings, touch runtime caches, open Chroma directly,
  acquire another lock, directly mutate manifest/inventory, or add
  API/audit/retry
- automatic post-publish `execute_chroma_retention` path remains preserved

**Implementation paths changed in `bd01f23` only:**

- `vectordb/manager.py`
- `tests/test_index_runtime_switch.py`

**Boundary:** runtime-only. **Нет** HTTP/API/admin audit in 2.3h itself
(later landed as 2.3i @ `ac4b317`). **Нет** settings/policy change, UI, live
Chroma/PostgreSQL/Redis, deploy, or push. Do **not** re-select 2.3h.

## Контракт 2.3g (guarded Chroma retention adapter bridge)

Adapter-only bridge in `vectordb/chroma_retention.py` + contracts in
`tests/test_chroma_retention.py`:

- new adapter-only `execute_guarded_chroma_retention` requires explicit
  expected generation and exact candidate tuple, accepts no caller lock token,
  supplies the shared Chroma direct-delete callback to
  `execute_index_retention`, and returns its domain result
- both guarded and automatic paths share one lazy direct-delete helper: one
  client per invocation, client created only on first deletion, only direct
  `delete_collection`, `NotFoundError` idempotent, other failures propagate
- existing `execute_chroma_retention` signature/held-lock/tuple-return and
  automatic post-publish behavior remain preserved
- validation/conflict/corrupt/lock/empty pre-delete paths do not instantiate a
  client

**Preserved foundations (not re-implemented here):** domain guarded retention
command (2.3f), existing automatic post-publish Chroma retention path, and
preview/rollback surfaces remain as before; 2.3g only adds the adapter bridge.

**Boundary:** adapter-only. **Нет** manager/runtime public action,
HTTP/API/admin audit, settings/policy change, UI, live Chroma/PostgreSQL/Redis,
deploy, or push. Do **not** claim full operator surface, plan step 2, project,
release, production readiness, live drills, or retention API complete.

## Уже существующее durable lifecycle-поведение

- Validated Chroma rebuild под tenant lock: record new version в trusted
  inventory → publish manifest → configured bounded retention.
- Active/previous и unrecorded collections защищены existing policy.
- Partial retention delete/prune failures остаются observable/repeatable
  (existing executor semantics).
- Domain preview (`preview_index_retention`) читает candidate policy, manifest
  и inventory под одним tenant lock **без** mutation.
- Admin retention preview API (2.3b): `GET /api/admin/index/retention-preview`
  — read-only, tenant from auth context only, no deletion/rollback/publish.
- Idempotent rollback command (2.3c): domain contract with explicit expected
  generation/target and exact-retry no-op.
- Runtime rollback (2.3d): manager requires the same expected generation/target,
  validates the explicit target under the operator lock, and updates cache from
  the rollback result without oscillation on exact retry.
- Admin rollback API (2.3e): existing-admin POST endpoint with strict body,
  tenant-from-auth only, safe typed mapping, `asyncio.to_thread`, and
  tenant-scoped `index_rollback` audit.
- Guarded retention execution (2.3f): unwired domain command requiring expected
  generation + exact candidate tuple before invoking bounded retention under
  one tenant lock.
- Guarded Chroma retention bridge (2.3g): adapter-only
  `execute_guarded_chroma_retention` requiring expected generation + exact
  candidate tuple, sharing the lazy direct-delete helper with automatic
  post-publish retention, without manager/runtime/HTTP wiring.
- Runtime manager retention action (2.3h):
  `execute_vector_store_retention` requires expected generation + exact
  candidate tuple, derives configured Chroma directory/budget via settings,
  fails closed for Qdrant before adapter work, and returns the guarded adapter
  result unchanged, without HTTP/API/admin audit.
- Admin retention execution API (2.3i): `POST /admin/index/retention` —
  existing-admin role, tenant-from-auth only, strict expected generation +
  exact candidates body, `asyncio.to_thread` to
  `execute_vector_store_retention`, safe complete response, typed 400/409/503
  mapping, and exactly-once `index_retention` audit with safe partial-progress
  fields; does not alter preview, rollback, or automatic post-publish
  retention.
- Immutable upload originals (2.4a): each created job writes exclusive
  job-scoped object under `job-objects/<job_id>/`, persists path on
  `IngestionJob.source_path`, keeps flat current corpus view via atomic
  replace after immutable write, preserves pre-2.4a flat-only prior bytes
  under `job-objects/legacy-previous/<sha256>/`, and leaves nested objects
  outside `recursive=False` scanning; replay/fingerprint rules unchanged.
- Build publication receipt (2.4b): manager opt-in
  `build_vector_store_with_publication` returns frozen
  `BuildVectorStoreResult` with optional `IndexPublicationReceipt` captured
  from the exact publish manifest of that build; ordinary
  `build_vector_store` remains a two-element `(store, chunks)` tuple; Qdrant
  success keeps `publication is None`.
- Async-worker receipt persistence (2.4c): async worker calls
  `build_vector_store_with_publication` exactly once, places exact Chroma
  receipt under durable `IngestionJob.result.index_publication` (or `null`
  for Qdrant/no-publication), and passes the same dict through
  lease/CAS `sync_mark_completed` / Celery return.
- Sync non-default upload receipt persistence (2.4d): `api.app` binds
  opt-in manager entrypoint; `_rebuild_vector_store_from_docs` performs one
  opt-in build under the existing runtime lock and returns exact
  `BuildVectorStoreResult`; non-default sync upload persists exact available
  `publication` under durable `IngestionJob.result.index_publication` (or
  `null` for Qdrant/no-publication and legacy truthy stubs); public
  `UploadResponse` unchanged.

**Не утверждать:** Qdrant operator support, live services, production
readiness, full immutable lifecycle, GC/retention for job/legacy objects,
orphan cleanup, complete fault injection, complete plan step 2,
project/release readiness. Local retention preview + guarded execution +
validated rollback operator surface is present after 2.3i. Immutable upload
originals + flat current view are present after 2.4a. Manager opt-in
publication receipt is present after 2.4b. Async-worker receipt persistence
is present after 2.4c. Sync non-default upload receipt persistence is
present after 2.4d; both accepted upload paths now record exact available
publication receipt in existing job result JSON.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.4d (latest)

- Grok implementation run `rag-step2-4d-20260803-a1`, local Grok CLI,
  requested `grok-4.5`, actual `grok-4.5-build`, normal `end_turn`, 18 turns,
  stderr empty.
- Tests-first red: **3 failed** — missing
  `_build_vector_store_with_publication` binding, missing durable
  `index_publication` for exact receipt, and missing durable null key.
- One allowed green diagnostic correction changed only the helper test's
  monkeypatch target from `config.settings.get_settings` to module-local
  `api.app.get_settings`.
- Grok focused green aggregate: **33 passed**; scoped Ruff clean;
  `mypy --follow-imports=skip` clean for app+upload; diff-check clean.
- Codex review found one concrete test-isolation defect only: direct global
  assignments and unisolated `_sessions` in the new helper test.
- Grok QA/fix run `rag-step2-4d-20260803-qa1`, same route/requested/actual
  model, 7 turns, stderr empty, ended `cancelled` after applying only the
  test-isolation fix and after pytest/Ruff/diff-check had passed. The stored
  output does **not** expose the exact pytest count; **do not invent one**
  and do **not** call this an unqualified normal completion. Production
  hashes remained unchanged.
- Independent Codex final proportional gate: **8 passed**; two known warnings
  (Starlette TestClient/httpx deprecation and LangChain Ollama deprecation);
  scoped Ruff clean; `python -m mypy --follow-imports=skip api/app.py
  api/routers/upload.py` clean; scoped diff-check clean.
- All nine protected hashes matched: manager, async worker, jobs, model,
  upload idempotency/security tests, categorizer test, integration ingestion
  flow test, and active protected plan.
- Full suite and live services were **not** run. Push/deploy not authorized;
  production readiness and full plan step 2 **not** claimed.
- Этот docs-only Update-51 **не** перезапускал project tests.

### 2.4c (summary)

- Tests-first red by Codex after prior Grok tests-only WIP: with local
  basetemp, **3 failed** because the unchanged worker still called ordinary
  `build_vector_store`, bypassed opt-in stubs, attempted a real Chroma build,
  and raised `Vector indexing failed`. An initial attempted run did not reach
  tests because global pytest temp root returned `WinError 5`; the narrowed
  local-basetemp rerun produced the valid behavioral red.
- Grok run `rag-step2-4c-20260803-a1`, route local Grok CLI, requested
  `grok-4.5`, actual `grok-4.5-build`, 8 turns, stderr empty, ended
  `cancelled` while locating a nonexistent `.venv`; it had written only the
  tests-first WIP, not production. Do **not** call this an unqualified normal
  completion.
- Grok follow-up `rag-step2-4c-20260803-a2`, same route/model request, actual
  `grok-4.5-build`, 10 turns, stderr empty, ended `cancelled` after production
  implementation and focused QA. Its focused aggregate: **16 passed**; Ruff
  and diff-check clean. Default Mypy hit an external installed
  NumPy-stub/project Python-version mismatch; narrowed
  `--follow-imports=skip` passed. Do **not** call this cancelled run an
  unqualified normal completion either.
- Independent Codex proportional gate after final diff: **6 passed**, one
  known Starlette deprecation warning; scoped Ruff clean;
  `python -m mypy --follow-imports=skip tasks/ingest_task.py` clean; scoped
  diff-check clean.
- Protected hashes matched for `vectordb/manager.py`, `ingestion/jobs.py`,
  `db/models.py`, `api/routers/upload.py`, `api/app.py`,
  `ingestion/pipeline.py`, and active untracked plan.
- Full default Mypy is **not** claimed clean in this environment. Full suite
  and live services were **not** run. Push/deploy not authorized. Production
  readiness **not** claimed.
- Docs-only Update-50 recorded 2.4c without re-running project tests.

### 2.4b (summary)

- Grok implementation: run `rag-step2-4b-20260803-a1`, route `local_grok_cli`,
  requested model `grok-4.5`, actual model `grok-4.5-build`; 20 turns;
  stderr empty; tests-first red `4 failed, 1 passed` for the missing opt-in
  receipt contract; focused green `8 passed`; Ruff clean; Mypy clean; scoped
  diff-check clean. The process ended `cancelled` only at its final
  disallowed multi-line `python -c` protected-hash probe, after code/static
  verification and status. Do **not** describe it as an unqualified normal
  completion; do **not** rerun that probe.
- Independent Codex proportional gate: `8 passed`, one known Starlette
  deprecation warning; Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4
  clean for `vectordb/manager.py`; scoped diff-check clean.
- All twelve protected SHA-256 baselines matched before commit, including
  manifest, worker/jobs/model, upload/API, pipeline, adjacent tests, and the
  active untracked plan.
- Full test suite and live services were **not** run. Push/deploy not
  authorized. Production readiness **not** claimed.
- Docs-only Update-49 recorded 2.4b without re-running project tests.

### 2.4a (summary)

- Grok implementation: run `rag-step2-4a-20260803-a1`, route `local_grok_cli`,
  requested model `grok-4.5`, actual model `grok-4.5-build`; 16 turns, normal
  `end_turn`, stderr empty; tests-first red `6 failed`, then focused green
  `76 passed`; Ruff clean.
- Independent Codex gate before QA: `12 passed`, one known Starlette
  deprecation warning; Ruff clean; Mypy clean for `api/routers/upload.py`;
  scoped diff-check clean.
- Grok QA/fix follow-up: run `rag-step2-4a-20260803-qa1`, same route/model;
  13 turns, normal `end_turn`, stderr empty; added legacy previous-original
  regression/fix; red evidence: two focused failures (missing recovery
  object and missing preservation helper); focused final `9 passed`; Ruff
  clean.
- Final independent Codex gate after QA: `16 passed`, one known Starlette
  deprecation warning; Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4
  clean for `api/routers/upload.py`; scoped diff-check clean.
- All protected hashes documented for 2.4a matched before commit, including
  `ingestion/jobs.py`, `tasks/ingest_task.py`, `db/models.py`,
  `ingestion/loader.py`, `scripts/reindex.py`, completed retention surfaces,
  and the active untracked plan.
- Full test suite and live services were **not** run. Push/deploy not
  authorized. Production readiness **not** claimed.
- Docs-only Update-48 recorded 2.4a without re-running project tests.

### 2.3i (summary)

- Grok: route `local_grok_cli`; requested model `grok-4.5`, actual model
  `grok-4.5-build`; first run `rag-step2-3i-20260803-a1` was cancelled before
  edits at a denied multi-line exploratory Pydantic `python -c` probe (target
  hashes remained unchanged); one cause-specific retry
  `rag-step2-3i-20260803-a2` forbade interpreter/hash probes, completed
  normally in 14 turns, and made the implementation; tests-first red:
  `32 failed, 40 deselected` for expected 404/missing route and missing source
  marker; focused final full admin operator file: `72 passed`, one known
  Starlette deprecation warning; Ruff clean; direct Mypy reported exactly one
  known pre-existing unchanged `dict-item` issue in trace-purge logic;
  narrowed `--disable-error-code=dict-item` passed; scoped diff-check clean.
  Do **not** claim unconditional full-file Mypy cleanliness and do **not**
  hide the first cancelled no-edit run.
- Codex independent: full scoped diff review found only the two allowed
  implementation files; independent proportional pytest gate:
  `14 passed, 58 deselected`, one known Starlette deprecation warning; scoped
  Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4 narrowed only for the
  known pre-existing `dict-item`: no issues in the changed contract; scoped
  diff-check clean; all eight protected hashes matched:
  `vectordb/manager.py`, `vectordb/chroma_retention.py`,
  `vectordb/index_operator.py`, `vectordb/index_retention.py`,
  `config/settings.py`, `api/app.py`, `auth/dependencies.py`, and
  `tests/test_index_runtime_switch.py`.
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.

### 2.3h (summary)

- Grok: route `local_grok_cli`; requested model `grok-4.5`, actual model
  `grok-4.5-build`; tests-first red failed for the expected missing
  `execute_vector_store_retention` entrypoint (the unrelated automatic rebuild
  routing test passed in the red selection); focused green `25 passed`; Ruff
  clean; Mypy clean. The 16-turn run ended `cancelled` only at the final
  disallowed compound `python -c` protected-hash request — do **not** describe
  that run as an unqualified clean completion, and do **not** invent a red
  failure count.
- Codex independent: scoped review found only the two allowed implementation
  files changed; independent proportional pytest gate:
  `12 passed, 24 deselected`, one known Starlette deprecation warning; scoped
  Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4: no issues in
  `vectordb/manager.py`; scoped diff-check clean before commit; all six
  protected file hashes matched (`vectordb/chroma_retention.py`,
  `tests/test_chroma_retention.py`, `vectordb/index_operator.py`,
  `vectordb/index_retention.py`, `config/settings.py`,
  `api/routers/admin_ops.py`).

### 2.3g (summary)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; tests-first red: `7` guarded tests failed because
  bridge/operator import was absent; focused final: `66 passed`; Ruff and
  scoped diff-check clean.
- Codex independent: adapter/runtime-retention compatibility gate:
  `13 passed, 23 deselected`, one known Starlette warning; scoped Ruff clean;
  Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4: no issues in
  `vectordb/chroma_retention.py`; scoped diff-check clean; protected
  operator/policy/manager/API/runtime-test hashes unchanged before commit.

### 2.3f (summary)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; first attempt cancelled before edits at a denied redundant
  `python -c` hash command; one cause-specific follow-up completed in 11 turns;
  tests-first red: `26 failed` due missing execution contract; final focused
  aggregate: `76 passed`, one known Starlette warning; Grok Ruff and scoped
  diff-check clean.
- Codex independent: new execution/boundary gate: `26 passed, 28 deselected`,
  one known Starlette warning; scoped Ruff clean; Python 3.11 / Mypy 1.19.1 /
  NumPy 2.4.4: no issues in `vectordb/index_operator.py`; scoped
  `git diff --check` clean; protected implementation/dependency/runtime/API
  hashes unchanged before commit.

### 2.3e (summary)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; red `26 failed, 14 deselected`; focused final `128 passed`
  with one known Starlette warning; Ruff/diff clean.
- Codex independent: `40 passed` with one known warning; scoped Ruff clean;
  narrowed Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4 passed with only existing
  `dict-item` disabled; protected hashes/route search/diff clean; final
  key-contract gate `19 passed`, Ruff/diff clean.
- Direct Mypy на весь `admin_ops.py`: pre-existing `dict-item` на **unchanged**
  logic at line **223** (commit `3c1e7b7d`, line shifted by inserted rollback
  code). **Никогда** не называть весь файл unconditionally Mypy-clean.

### 2.3d (summary)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; initial red `18 failed, 18 passed`; final focused gate
  `90 passed` with two pre-existing warnings; Ruff/diff clean.
- Codex independent: `53 passed` with one known FastAPI/Starlette warning;
  scoped Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4 clean; caller
  search found no production call sites; protected hashes/diff clean. One Grok
  QA follow-up corrected only the stale module word `unwired`; final
  key-contract gate `9 passed`, Ruff/diff clean.

### 2.3c (summary)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, result-reported
  actual model `grok-4.5-build`; initial red `18 failed, 9 passed`; focused
  final `60 passed` after one allowed narrowed correction to a false-positive
  source-boundary assertion; Ruff and scoped diff check clean.
- Codex independent: `27 passed` with the already known FastAPI/Starlette
  TestClient deprecation warning; scoped Ruff clean; Python 3.11 /
  Mypy 1.19.1 / NumPy 2.4.4 clean; protected hashes and diff check clean.

### 2.3b (summary)

- Grok TDD: **14** expected failures (route absent) → **48** focused passes;
  scoped Ruff/diff clean; route/model `local_grok_cli` / `grok-4.5-build`.
- Codex independent closure: **103** passed, 1 known FastAPI TestClient
  deprecation warning; scoped Ruff clean; protected hashes + cached diff check
  clean.
- Direct Mypy caveat originally reported at unchanged line **215**; later
  shifted by inserted lines (see 2.3e caveat at **223**).

### 2.3a (summary)

- Grok: **46** focused passes; Codex: **79**-pass closure.

### Reference commands (2.4e) — только при regression / new classifier code

```powershell
python -m pytest tests/test_job_object_inventory.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4e-<unique>
# adjacent (as run for 2.4e):
python -m pytest tests/test_job_object_inventory.py tests/test_upload_idempotency.py tests/test_upload_security.py tests/test_ingestion_job_contract.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4e-adj-<unique>
python -m ruff check ingestion/job_object_inventory.py tests/test_job_object_inventory.py
# mypy: prefer py3.12+ host with mypy 1.19.1; host 3.13 may hit NumPy stub syntax noise
python -m mypy ingestion/job_object_inventory.py --config-file pyproject.toml
git diff --check -- ingestion/job_object_inventory.py tests/test_job_object_inventory.py
```

### Reference commands (2.4f — landed)

```powershell
python -m pytest tests/test_job_object_inventory.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4f-<unique>
python -m pytest tests/test_job_object_inventory.py tests/test_upload_idempotency.py tests/test_upload_security.py tests/test_ingestion_job_contract.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4f-adj-<unique>
python -m ruff check ingestion/job_object_inventory.py ingestion/jobs.py tests/test_job_object_inventory.py
python -m mypy ingestion/job_object_inventory.py ingestion/jobs.py --config-file pyproject.toml
git diff --check -- ingestion/job_object_inventory.py ingestion/jobs.py tests/test_job_object_inventory.py
```

### Reference commands (2.4g — landed)

```powershell
python -m pytest tests/test_job_object_retention.py tests/test_job_object_inventory.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4g-<unique>
python -m pytest tests/test_job_object_retention.py tests/test_job_object_inventory.py tests/test_upload_idempotency.py tests/test_upload_security.py tests/test_ingestion_job_contract.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4g-adj-<unique>
python -m ruff check ingestion/job_object_retention.py tests/test_job_object_retention.py
python -m mypy ingestion/job_object_retention.py --config-file pyproject.toml
git diff --check -- ingestion/job_object_retention.py tests/test_job_object_retention.py
```

### Reference commands (2.4h — landed)

```powershell
python -m pytest tests/test_job_object_retention.py tests/test_job_object_inventory.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4h-<unique>
python -m pytest tests/test_job_object_retention.py tests/test_job_object_inventory.py tests/test_upload_idempotency.py tests/test_upload_security.py tests/test_ingestion_job_contract.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4h-adj-<unique>
python -m ruff check ingestion/job_object_retention.py tests/test_job_object_retention.py
python -m mypy ingestion/job_object_retention.py --config-file pyproject.toml
git diff --check -- ingestion/job_object_retention.py tests/test_job_object_retention.py
```

### Reference commands (2.4i — landed)

```powershell
python -m pytest tests/test_preview_job_object_inventory_cli.py tests/test_job_object_retention.py tests/test_job_object_inventory.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4i-<unique>
python -m ruff check scripts/preview_job_object_inventory.py tests/test_preview_job_object_inventory_cli.py
python -m mypy scripts/preview_job_object_inventory.py --config-file pyproject.toml
# operator smoke (no DB load if using injected tests; live needs DATABASE_URL):
python scripts/preview_job_object_inventory.py --tenant default --json
```

### Reference commands (2.4j candidate) — after investigation/contract

```powershell
# Adjust once 2.4j lands; keep CLI + retention green:
python -m pytest tests/test_preview_job_object_inventory_cli.py tests/test_job_object_retention.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-4j-<unique>
```

### Reference commands (2.4d) — только при new code/failure

```powershell
python -m pytest tests/test_ingestion_job_contract.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4d-<unique>
python -m ruff check api/app.py api/routers/upload.py tests/test_ingestion_job_contract.py
python -m mypy --follow-imports=skip api/app.py api/routers/upload.py
git diff --check -- api/app.py api/routers/upload.py tests/test_ingestion_job_contract.py
```

### Reference commands (2.4c) — только при new code/failure

```powershell
python -m pytest tests/test_ingest_task.py tests/test_ingestion_job_contract.py tests/test_ingestion_liveness.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4c-<unique>
python -m ruff check tasks/ingest_task.py tests/test_ingest_task.py tests/test_ingestion_job_contract.py tests/test_ingestion_liveness.py
python -m mypy --follow-imports=skip tasks/ingest_task.py
git diff --check -- tasks/ingest_task.py tests/test_ingest_task.py tests/test_ingestion_job_contract.py tests/test_ingestion_liveness.py
```

### Reference commands (2.4b) — только при new code/failure

```powershell
python -m pytest tests/test_index_runtime_switch.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4b-<unique>
python -m ruff check vectordb/manager.py tests/test_index_runtime_switch.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/manager.py --no-incremental --show-error-codes
git diff --check -- vectordb/manager.py tests/test_index_runtime_switch.py
```

### Reference commands (2.4a) — только при new code/failure

```powershell
python -m pytest tests/test_upload_idempotency.py tests/test_upload_security.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4a-<unique>
python -m ruff check api/routers/upload.py tests/test_upload_idempotency.py tests/test_upload_security.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy api/routers/upload.py --no-incremental --show-error-codes
git diff --check -- api/routers/upload.py tests/test_upload_idempotency.py tests/test_upload_security.py
```

### Reference commands (2.3i) — только при new code/failure

```powershell
python -m pytest tests/test_admin_index_operator.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3i-<unique>
python -m ruff check api/routers/admin_ops.py tests/test_admin_index_operator.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy api/routers/admin_ops.py --no-incremental --show-error-codes --disable-error-code=dict-item
git diff --check -- api/routers/admin_ops.py tests/test_admin_index_operator.py
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи. Direct full-file Mypy on `admin_ops.py` still
has the known pre-existing unchanged `dict-item` issue in trace-purge logic;
never claim unconditional full-file Mypy cleanliness without evidence.

## Что остаётся открытым / следующий safe slice

**Не начато (вне next candidate):**

- broader fault injection, live PostgreSQL/Redis/Celery/Chroma drills
  (explicit opt-in only — do **not** select as default next slice),
  release gates, project completion.
- full immutable lifecycle beyond 2.4a–2.4e: GC/retention **executor** for
  job-objects and legacy-previous recovery objects; orphan cleanup
  **mutations** after failed transition; live concurrency/fault-injection
  for upload originals; age/budget delete policy.
- DB migration/model fields for index version/collection; API/UI surfaces
  (out of 2.4f preview scope unless proven required).

**Remaining honest limitations after 2.4i:**

- both accepted upload paths still record publication receipts (2.4c/2.4d)
- read-only job-object classifier exists (`13be7d9`)
- tenant-scoped DB load + preview composition exists (`68cf045`)
- fail-closed retention policy exists (`1ccb39b`) with **empty** auto-delete
  candidates
- guarded retention command exists (`9761caf`) but is a **no-op** under
  current policy (`deleted` always empty; no FS mutation)
- operator CLI exists (`f0f79b9`) for inventory + policy + optional no-op
- full immutable-original lifecycle is still **not** complete
- no real filesystem **deletion** path for job-objects / legacy
- no orphan cleanup **mutations** on failed transitions
- no age/budget delete thresholds
- no admin HTTP operator surface
- no migration/model field for index version/collection on the job
- no live concurrency/fault-injection; full suite not run
- full plan step 2 / project / release / production readiness **not** complete

**Next candidate (not started):** **2.4j failed-transition job-object orphan
ownership investigation**. Candidate only — **not** completed work and
**not** started. Confirm what remains on disk/DB after failed upload/
transition paths **read-only** before any mutation contract. Still **no**
deletion by default. Do **not** invent auto-delete classes or age/budget
rules, edit the plan, reopen 2.1–2.4i, or mark 2.4j started/complete from
docs alone.

**Superseded / do not re-select:** 2.1–2.4i are complete. Historical
next-work text that still names **2.4a**–**2.4i** as the next candidate is
stale. Historical headings containing `✅ START HERE` are archival.

### Следующий named candidate: 2.4j failed-transition orphan ownership (не начат)

Smallest safe framing: investigate failed-transition / partial-write orphans
for job-objects and legacy-previous (who creates them, which classifications
already cover them, whether any mutation is ever safe). **Not started.**
**Do not re-select 2.4a–2.4i.** Default remains **no** deletion.

**Candidate ownership (confirm read-only next session):**

| Surface | Module / symbols | Notes |
|---------|------------------|-------|
| Operator CLI (do not reopen) | `scripts/preview_job_object_inventory.py` | 2.4i @ `f0f79b9` |
| Guarded command / policy | `job_object_retention` | 2.4g/2.4h |
| Classify / preview / load | `job_object_inventory` + `jobs.sync_list_*` | 2.4e/2.4f |
| Create / fail paths | `api/routers/upload.py` | 2.4a — read-only inspect |
| Orphan cleanup mutations | **none** | 2.4j investigation target |

**Evidence-based boundary for 2.4j:**

- investigation / ownership first — **no** filesystem mutation by default
- **no** inventing auto-delete classes or age/budget thresholds
- **no** reopening 2.4e–2.4i without proven conflict
- **no** plan checkbox edits from docs turns
- do **not** mark 2.4j started/complete from docs alone

**Plan source (direction only):** active untracked plan
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
§2 still carries the broader immutable/versioned originals + lifecycle bind
item (do **not** edit plan checkboxes here). 2.4i landed operator CLI; 2.4j
is the failed-transition orphan ownership candidate only.

### Historical 2.4d ownership notes (archive; 2.4d COMPLETE @ `dfbbca0`)

Landed sync non-default upload receipt wiring is in §Контракт 2.4d above.
**Do not treat as next-work instruction.**

| Surface | Module / symbols | Focused tests |
|---------|------------------|---------------|
| Sync rebuild helper | `api/app.py` — `_rebuild_vector_store_from_docs` + opt-in binding | `tests/test_ingestion_job_contract.py` |
| Non-default sync upload | `api/routers/upload.py` | `tests/test_ingestion_job_contract.py` |
| Opt-in manager entrypoint (consumed; not re-opened) | `vectordb.manager.build_vector_store_with_publication` | already covered by 2.4b |
| Async worker receipt (not re-opened) | `tasks/ingest_task.py` | already covered by 2.4c |

**Gap closed by 2.4d:** non-default sync upload now persists exact available
publication receipt under durable `IngestionJob.result.index_publication`
(or `null`). Together with 2.4c, both accepted upload execution paths record
the exact available receipt in existing job result JSON. **Later closed by
2.4e (classification only):** read-only inventory classifier for
job-objects / legacy-previous. **Gap still open after 2.4e:** GC/retention
executor, tenant-scoped preview wiring (**2.4f**), orphan cleanup mutations —
not a claim that full plan step 2 is complete.

### Historical 2.4c ownership notes (archive; 2.4c COMPLETE @ `999c90f`)

Landed async-worker receipt wiring is in §Контракт 2.4c above. **Do not
treat as next-work instruction.**

| Surface | Module / symbols | Focused tests |
|---------|------------------|---------------|
| Async worker completion | `tasks/ingest_task.py` | `tests/test_ingest_task.py`, `tests/test_ingestion_job_contract.py`, `tests/test_ingestion_liveness.py` |
| Opt-in manager entrypoint (consumed; not re-opened) | `vectordb.manager.build_vector_store_with_publication` | already covered by 2.4b |

**Gap closed by 2.4c (async-worker only):** durable `IngestionJob.result`
now carries `index_publication` from the exact opt-in manager invocation via
lease/CAS completion. **Later closed by 2.4d:** non-default sync upload path
receipt persistence.

### Historical 2.4a ownership notes (archive; 2.4a COMPLETE @ `a1dcd5c`)

The following Update-47 ownership evidence guided 2.4a and is retained as
archive. **Do not treat as next-work instruction.** Landed behavior is in
§Контракт 2.4a above.

| Surface | Module / symbols | Focused tests |
|---------|------------------|---------------|
| HTTP upload write path | `api/routers/upload.py` | `tests/test_upload_security.py`, `tests/test_upload_idempotency.py` |
| Durable job identity | `ingestion/jobs.py` (unchanged in 2.4a) | job-contract / upload idempotency tests |
| Job ORM | `db/models.py` — still **no** index-version / collection fields | same |
| Async worker | `tasks/ingest_task.py` — after 2.4c, completion `result` includes `index_publication` (async path only) | `tests/test_ingest_task.py` |
| Corpus load / reindex | `ingestion/loader.py`; `scripts/reindex.py` — flat tenant upload dir, `recursive=False` (unchanged; flat current view preserved by 2.4a) | loader / reindex-adjacent gates |

**Historical pre-2.4a overwrite gap (closed by `a1dcd5c`):** flat
`write_bytes` overwrite of prior working original is no longer the creator
path; job-scoped immutable objects + legacy-previous preservation + atomic
flat refresh landed. Nested job/recovery objects stay outside non-recursive
corpus scanning.

### Explicit non-goals (next candidate and standing)

- Re-opening completed 2.4i CLI, 2.4h command, 2.4g policy, 2.4f–2.4e
  inventory, 2.4d–2.4a upload/receipt surfaces, or index retention operator
  surfaces without proven conflict
- Settings/policy rewrite, UI, Helm/PVC/object-storage migration
- Inventing auto-delete classifications or age/budget thresholds in the 2.4j
  investigation slice without explicit later policy expansion
- Filesystem mutation under current empty-candidate policy
- Editing plan checkboxes from docs turns
- DB migration / model field for index version/collection without proven need
- Full fault-injection matrix; concurrent multi-tenant load drills
- Live PostgreSQL/Redis/Celery/Chroma; push; deploy; production readiness
- Claiming full plan step 2 or full immutable lifecycle “done” from
  classification, preview, policy, guarded no-op, CLI, or receipt wiring alone

### Stop / re-scope conditions

- Protected completed-slice surfaces change without an explicit conflict plan
- Target files become unexpectedly dirty / foreign WIP appears
- Scope requires multi-subsystem expansion (manifest + retention + upload +
  reindex + migration) in one turn
- Second independent verification fails after one allowed narrow correction
- Any push/deploy/live/destructive Git pressure without user authorization
- Exact owners cannot be confirmed read-only without inventing APIs or
  deletion rules — stop and report rather than guess

## Definition of done / stop conditions

- **2.4i is complete** at implementation commit `f0f79b9` with the
  verification ledger above, **only at the bounded operator-CLI scope**.
  **Do not re-select 2.4i.**
- **2.4h is complete** at implementation commit `9761caf` with the
  verification ledger above, **only at the bounded guarded no-op command
  scope**. **Do not re-select 2.4h.**
- **2.4g is complete** at implementation commit `1ccb39b` with the
  verification ledger above, **only at the bounded fail-closed policy
  assessment scope**. **Do not re-select 2.4g.**
- **2.4f is complete** at implementation commit `68cf045` with the
  verification ledger above, **only at the bounded read-only tenant preview
  scope**. **Do not re-select 2.4f.**
- **2.4e is complete** at implementation commit `13be7d9` with the
  verification ledger above, **only at the bounded read-only classification
  scope**. **Do not re-select 2.4e.**
- **2.4d is complete** at implementation commit `dfbbca0` with the
  verification ledger above, **only at the bounded sync non-default upload
  scope**. **Do not re-select 2.4d.**
- **2.4c is complete** at implementation commit `999c90f` with the
  verification ledger above, **only at the bounded async-worker scope**.
  **Do not re-select 2.4c.**
- **2.4b is complete** at implementation commit `29be31a`. **Do not
  re-select 2.4b.**
- **2.4a is complete** at implementation commit `a1dcd5c`. **Do not
  re-select 2.4a.**
- **Do not re-select 2.3i** (`ac4b317`) or **2.1–2.3h.**
- Next candidate **2.4j** is **done only after** read-only ownership evidence
  for failed-transition orphans and (if chosen) a separate tests-first
  contract, one independent proportional gate, protected-surface checks,
  scoped diff-check, and local explicit-path commit. Do **not** mark 2.4j
  started/complete from docs alone. Default is **no** deletion.
- **No** full-suite / live / deploy / push / production-readiness claims.
- **Stop/yield after one named slice** because one user turn equals one
  slice.
- **Stop and report** if a target file becomes unexpectedly dirty, a second
  verification fails, or scope needs expansion.
- **Actual Git wins** over any embedded hashes/counts in this handoff.

## Защищённое локальное состояние

Dirty tracked (не трогать без explicit request):

- `BACKLOG.md`
- `README.md`
- `audit_gpt_23_07_26.md`
- `plan_sol_23_07_26`

Protected untracked categories (summarized; do not remove/stage without
specific request):

- `.grok-prompts/`, `.pytest_tmp*/`
- presentation/explainer artifacts (`pres.html`, `presentation.html`,
  `RAG Explainer.html`, `_ref_presentation3.html`, `plan_for_pres.md`,
  `rag_new_explanation.md`)
- `_NEXT_SESSION.md`, `FLANT_DOGFOOD_FINDINGS.md`
- active untracked remediation plan `rag-remediation-plan-2026-08-03.md`
- architecture HTML/check script (`docs/architecture-data-flow.html`,
  `scripts/check_architecture_diagram.py`)

Не читать `.env`. Не обращаться к live services без explicit opt-in.
Никогда не stage/remove/touch listed protected artifacts without explicit
scope.

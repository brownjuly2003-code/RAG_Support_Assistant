# Session handoff

**Обновлено:** 2026-08-03 (Update-51 docs-only record of completed slice
**2.4d**; latest implementation `dfbbca0`; previous docs `7e2fa84`; previous
implementation `999c90f` / **2.4c**; next candidate **2.4e immutable
job-object lifecycle cleanup ownership/policy investigation** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(**только верхний блок Update-51** — routing authority; older blocks including
literal `✅ START HERE` headings are archival). Evidence 2.4d — ниже; 2.4c —
Update-50; 2.4b — Update-49; 2.4a — Update-48; 2.3i — Update-46; 2.3h —
Update-45; 2.3g — Update-43; детали 2.3f/2.3e/2.3d/2.3c/2.3b/2.3a —
Update-42/Update-41/Update-40/Update-39/Update-37/Update-36. Активный plan
source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**. Детали и ledger — в секциях ниже; не
дублируй длинную историю в новых edits.

| Факт | Значение |
|------|----------|
| Latest implementation | `dfbbca0` (`feat(ingestion): persist sync upload publication receipt`) — **2.4d** (bounded sync non-default upload scope) |
| Previous docs commit | `7e2fa84` (`docs: record async worker publication receipt`) |
| Previous implementation | `999c90f` (slice **2.4c**) |
| Future Update-51 docs commit | **unknown inside its own content**; next session: `git log -5 --oneline` |
| Branch advisory | `master...origin/master [ahead 86]` — **refresh mandatory** |
| Active writer | **none** |
| Unfinished WIP in next targets | **none known** |
| Locally complete (documented scopes) | **2.1–2.4d** |
| Not complete / not claimed | full plan step 2; full immutable lifecycle; GC/retention for job/legacy objects; orphan cleanup; DB model/migration field; full suite; live drills; project/release/production readiness |
| Next allowed candidate | **2.4e immutable job-object lifecycle cleanup ownership/policy investigation** (**not started**) |
| Gates | no push / deploy / live services / destructive Git / production claims |

**Known verification caveats (2.4d):** tests-first red 3 failed; one allowed
green diagnostic correction (helper test monkeypatch target only); Grok
focused green 33 passed + scoped Ruff/Mypy/diff-check clean; Codex review
found one concrete test-isolation defect only; Grok QA/fix run ended
`cancelled` after applying only that isolation fix and after pytest/Ruff/
diff-check had passed (exact pytest count not exposed — do **not** invent
one; do **not** call it an unqualified normal completion); independent Codex
final proportional gate 8 passed + two known deprecation warnings; full
suite/live services **not** run. Remaining honest limitations: both accepted
upload paths now record exact available publication receipt in job result
JSON, but full immutable lifecycle is still incomplete (no GC/retention for
`job-objects`/`legacy-previous`, no orphan cleanup, no DB model/migration
field). **No** full/live suite in 2.4d or this docs-only Update-51.

**Protected state (do not touch/stage/remove without explicit request):**

- Dirty tracked: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- Untracked (incl.): `.grok-prompts/`, `.pytest_tmp*/`, presentation/explainer
  artifacts, `_NEXT_SESSION.md`, `FLANT_DOGFOOD_FINDINGS.md`, active plan
  `rag-remediation-plan-2026-08-03.md`, `docs/architecture-data-flow.html`,
  `scripts/check_architecture_diagram.py`

**Routing rule:** only the **first/topmost** Update block in
[`AGENT_STATE.md`](../AGENT_STATE.md) is authoritative. Never select work by
grepping historical `START HERE` markers.

## Быстрый старт следующей сессии

Executable checklist **in order**. **Нет** active writer и **нет** unfinished
next-candidate WIP на момент этого handoff.

1. **Cycle-guard preflight** on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline` as **separate** commands; **actual Git wins** over
   embedded hashes/counts (including the future Update-51 docs commit SHA).
3. Read **only** top **Update-51** in `AGENT_STATE.md` + this
   **Нулевая неоднозначность** capsule first; treat older Update blocks as
   archive. Do **not** reselect 2.1–2.4d.
4. Confirm **2.4e ownership/policy read-only** before any edit (current
   durable evidence only: 2.4a creates `job-objects/<job_id>/...` and
   `job-objects/legacy-previous/<sha256>/...`; current handoff states no GC
   or orphan cleanup exists). Next session must confirm owners, retention
   safety invariants, job/index references, and tests **read-only** before
   choosing a small test-first contract; re-check protected dirty/untracked
   list. Do **not** reopen completed 2.4d sync upload receipt, completed
   2.4c async worker receipt, completed 2.4b manager receipt, completed 2.4a
   upload originals, or retention operator surfaces unless investigation
   proves a required conflict — then **stop and re-scope**. Do **not**
   prescribe deletion rules, edit the plan, or mark 2.4e started/complete
   without a confirmed contract.
5. Use **Grok** via the local verified route; announce counters
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`. Execute **at most
   one** named atomic next candidate after ownership is confirmed.
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
2. Далее: верхний блок `AGENT_STATE.md` (**Update-51**) и эта капсула.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-51 и **не** дают права повторять уже
   завершённые срезы 2.1–2.4d.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Do **not** edit its checkboxes from docs turns.
   Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `dfbbca0`
(`feat(ingestion): persist sync upload publication receipt`) — slice **2.4d**
locally complete/verified at the **bounded sync non-default upload scope**.
Previous docs commit: `7e2fa84` (`docs: record async worker publication
receipt`). Previous implementation: `999c90f` (slice **2.4c**). Do **not**
embed a guessed future docs commit hash; next session reads actual `git log`.
Branch was observed as `master...origin/master [ahead 86]` immediately after
implementation — ahead counts/timestamps are **advisory only**. Push/deploy
not authorized.

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
| **2.4d** | sync non-default upload index publication receipt persistence | `dfbbca0` | Update-51 + this handoff |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g, 2.3h, 2.3i, 2.4a,
2.4b, 2.4c, 2.4d** локально complete и verified (**2.4d only at bounded sync
non-default upload scope**; **2.4c only at bounded async-worker scope**).
Локальный operator surface для retention preview + guarded execution и
validated rollback **present**. Immutable upload originals with job-scoped
objects + flat current corpus view **present** after 2.4a. Manager opt-in
publication receipt (`build_vector_store_with_publication`) **present** after
2.4b. Async worker persists exact Chroma receipt into durable
`IngestionJob.result.index_publication` after 2.4c. Non-default sync upload
now also persists exact available publication receipt under the same job
result key after 2.4d. Полный plan step 2, full immutable lifecycle,
GC/retention for job/legacy objects, orphan cleanup, fault injection, live
drills, project и release — **не** complete. **2.4a, 2.4b, 2.4c, and 2.4d
must never be selected again.** Next safe candidate is **2.4e immutable
job-object lifecycle cleanup ownership/policy investigation** (**not
started**).

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
- full immutable lifecycle beyond 2.4a/2.4b/2.4c/2.4d: GC/retention for
  job-objects and legacy-previous recovery objects; orphan cleanup after
  failed transition; live concurrency/fault-injection for upload originals.
- DB migration/model fields for index version/collection; API/UI surfaces
  (out of 2.4e investigation scope until ownership/policy is confirmed).

**Remaining honest limitations after 2.4d:**

- both accepted upload execution paths now durably record the exact available
  publication receipt in existing job result JSON (default async via 2.4c,
  non-default sync via 2.4d)
- full immutable-original lifecycle is still **not** complete
- no GC/retention policy/executor for `job-objects` or `legacy-previous`
- no orphan cleanup on failed transitions
- no migration/model field for index version/collection on the job
- no live concurrency/fault-injection; full suite not run
- full plan step 2 / project / release / production readiness **not** complete

**Next candidate (not started):** **2.4e immutable job-object lifecycle
cleanup ownership/policy investigation**. Candidate only — **not** completed
work and **not** started. Current durable evidence only: 2.4a creates
`job-objects/<job_id>/...` and `job-objects/legacy-previous/<sha256>/...`;
current handoff states no GC or orphan cleanup exists. Next session must
confirm owners, retention safety invariants, job/index references, and tests
**read-only** before choosing a small test-first contract. Do **not**
prescribe deletion rules, edit the plan, reopen 2.4a–2.4d, or mark 2.4e
started/complete from docs.

**Superseded / do not re-select:** 2.1–2.4d are complete. Historical
next-work text that still names **2.4a**, **2.4b**, **2.4c**, **2.4d**, or
generic job↔index investigation as the next candidate is stale. Historical
headings containing `✅ START HERE` are archival.

### Следующий named candidate: 2.4e immutable job-object lifecycle cleanup ownership/policy investigation (не начат)

Smallest safe framing: investigate ownership/policy and the smallest
test-first cleanup contract for immutable job-objects / legacy-previous
recovery objects. **Not started.** **Do not re-select 2.4a, 2.4b, 2.4c, or
2.4d.** No active writer and no unfinished next-candidate WIP at this
handoff.

**Candidate ownership (confirm read-only next session):**

| Surface | Module / symbols | Notes |
|---------|------------------|-------|
| Immutable job objects (create only today) | `api/routers/upload.py` / 2.4a path | creates `job-objects/<job_id>/...` |
| Legacy previous recovery objects (create only today) | 2.4a path | creates `job-objects/legacy-previous/<sha256>/...` |
| Durable job result receipt (do not re-open 2.4c/2.4d) | `IngestionJob.result.index_publication` | both upload paths now persist exact available receipt |
| GC / orphan cleanup | **none known** | current handoff states no GC or orphan cleanup exists |

**Evidence-based boundary for 2.4e:**

- confirm owners, retention safety invariants, job/index references, and
  tests **read-only** before any edit
- choose the smallest test-first cleanup contract only after ownership/policy
  is confirmed
- **no** prescribed deletion rules from docs alone
- **no** reopening 2.4a–2.4d surfaces without proven conflict
- **no** plan checkbox edits from docs turns
- do **not** mark 2.4e started/complete from docs alone

**Plan source (direction only):** active untracked plan
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
§2 still carries the broader immutable/versioned originals + lifecycle bind
item (do **not** edit plan checkboxes here). 2.4a landed immutable originals;
2.4b landed the manager receipt; 2.4c landed async-worker receipt
persistence; 2.4d landed sync non-default upload receipt persistence; 2.4e
is the immutable job-object lifecycle cleanup ownership/policy investigation
candidate only.

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
the exact available receipt in existing job result JSON. **Gap still open:**
full immutable lifecycle cleanup (GC/retention/orphan) — that is the
**2.4e** candidate direction, not a claim that full plan step 2 is complete.

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

- Re-opening completed 2.4d sync upload receipt surfaces, 2.4c async-worker
  surfaces, 2.4b manager receipt surfaces, 2.4a upload write path, or
  retention operator surfaces without proven conflict
- Settings/policy rewrite, UI, Helm/PVC/object-storage migration
- Prescribing deletion rules for 2.4e before ownership/policy confirmation
- Editing plan checkboxes from docs turns
- DB migration / model field for index version/collection without proven need
- Full fault-injection matrix; concurrent multi-tenant load drills
- Live PostgreSQL/Redis/Celery/Chroma; push; deploy; production readiness
- Claiming full plan step 2 or full immutable lifecycle “done” from receipt
  wiring alone

### Stop / re-scope conditions

- Protected completed-slice surfaces change without an explicit conflict plan
- Target files become unexpectedly dirty / foreign WIP appears
- Scope requires multi-subsystem expansion (manifest + retention + upload +
  reindex + migration) in one turn
- Second independent verification fails after one allowed narrow correction
- Any push/deploy/live/destructive Git pressure without user authorization
- Exact owners cannot be confirmed read-only without inventing APIs or
  deletion rules — stop and report rather than guess

This docs-only turn did **not** run project tests and did **not** start the
next candidate.

## Definition of done / stop conditions

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
- Next candidate **2.4e** is **done only after** read-only ownership/policy
  confirmation, a chosen smallest test-first cleanup contract, Grok
  tests-first evidence for that bounded contract, one independent
  proportional gate, protected-surface checks, scoped diff-check, and local
  explicit-path commit. Do **not** mark 2.4e started/complete from docs alone.
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

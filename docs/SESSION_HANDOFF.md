# Session handoff

**Обновлено:** 2026-08-03 (Update-50 docs-only record of completed slice
**2.4c**; latest implementation `999c90f`; previous docs `9f59768`; previous
implementation `29be31a` / **2.4b**; next candidate **2.4d sync non-default
upload receipt ownership/contract investigation** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(**только верхний блок Update-50** — routing authority; older blocks including
literal `✅ START HERE` headings are archival). Evidence 2.4c — ниже; 2.4b —
Update-49; 2.4a — Update-48; 2.3i — Update-46; 2.3h — Update-45; 2.3g —
Update-43; детали 2.3f/2.3e/2.3d/2.3c/2.3b/2.3a —
Update-42/Update-41/Update-40/Update-39/Update-37/Update-36. Активный plan
source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**. Детали и ledger — в секциях ниже; не
дублируй длинную историю в новых edits.

| Факт | Значение |
|------|----------|
| Latest implementation | `999c90f` (`feat(ingestion): persist index publication receipt`) — **2.4c** (async-worker scope only) |
| Previous docs commit | `9f59768` (`docs: record build publication receipt`) |
| Previous implementation | `29be31a` (slice **2.4b**) |
| Future Update-50 docs commit | **unknown inside its own content**; next session: `git log -5 --oneline` |
| Branch advisory | `master...origin/master [ahead 84]` — **refresh mandatory** |
| Active writer | **none** |
| Unfinished WIP in next targets | **none known** |
| Locally complete (documented scopes) | **2.1–2.4c** |
| Not complete / not claimed | full plan step 2; full immutable lifecycle; full durable cross-path job↔published index binding (async worker only; sync non-default upload remains bool-only/unwired); GC/retention for job/legacy objects; orphan cleanup; full suite; live drills; project/release/production readiness |
| Next allowed candidate | **2.4d sync non-default upload receipt ownership/contract investigation** (**not started**) |
| Gates | no push / deploy / live services / destructive Git / production claims |

**Known verification caveats (2.4c):** tests-first red by Codex after prior
Grok tests-only WIP; Grok runs `a1`/`a2` both ended `cancelled` (do **not**
describe as unqualified normal completion); independent Codex proportional
gate 6 passed + one known Starlette deprecation warning; full default Mypy
**not** claimed clean; full suite/live services **not** run. Remaining honest
limitations: 2.4c is **async-worker only**; non-default sync upload remains
bool-only/unwired; no migration/model field; no GC/retention for job objects
or legacy recovery objects; a failed transition can leave an orphaned new
immutable object. **No** full/live suite in 2.4c or this docs-only Update-50.

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
   embedded hashes/counts (including the future Update-50 docs commit SHA).
3. Read **only** top **Update-50** in `AGENT_STATE.md` + this
   **Нулевая неоднозначность** capsule first; treat older Update blocks as
   archive. Do **not** reselect 2.1–2.4c.
4. Confirm **2.4d ownership read-only** before any edit (current evidence:
   non-default upload in `api/routers/upload.py` calls bool-returning
   `_app._rebuild_vector_store_from_docs`; `api/app.py` owns that helper and
   its ordinary `_build_vector_store` binding). These are shared/protected
   surfaces — confirm ownership/test impact **read-only** first; re-check
   protected dirty/untracked list. Do **not** reopen completed 2.4c async
   worker surfaces, completed 2.4b manager receipt, completed 2.4a upload
   originals, or retention operator surfaces unless investigation proves a
   required conflict — then **stop and re-scope**. Do **not** invent an API
   or mark 2.4d started/complete without a confirmed contract.
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
2. Далее: верхний блок `AGENT_STATE.md` (**Update-50**) и эта капсула.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-50 и **не** дают права повторять уже
   завершённые срезы 2.1–2.4c.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Do **not** edit its checkboxes from docs turns.
   Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `999c90f`
(`feat(ingestion): persist index publication receipt`) — slice **2.4c**
locally complete/verified at the **bounded async-worker scope**. Previous
docs commit: `9f59768` (`docs: record build publication receipt`). Previous
implementation: `29be31a` (slice **2.4b**). Do **not** embed a guessed
future docs commit hash; next session reads actual `git log`. Branch was
observed as `master...origin/master [ahead 84]` immediately after
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
| **2.4c** | async-worker index publication receipt persistence | `999c90f` | Update-50 + this handoff |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g, 2.3h, 2.3i, 2.4a,
2.4b, 2.4c** локально complete и verified (**2.4c only at bounded async-worker
scope**). Локальный operator surface для retention preview + guarded
execution и validated rollback **present**. Immutable upload originals with
job-scoped objects + flat current corpus view **present** after 2.4a.
Manager opt-in publication receipt (`build_vector_store_with_publication`)
**present** after 2.4b. Async worker now persists exact Chroma receipt into
durable `IngestionJob.result.index_publication` after 2.4c; non-default sync
upload path remains bool-only/unwired. Полный plan step 2, full immutable
lifecycle, full durable cross-path job↔published index binding,
GC/retention for job/legacy objects, fault injection, live drills, project
и release — **не** complete. **2.4a, 2.4b, and 2.4c must never be selected
again.** Next safe candidate is **2.4d sync non-default upload receipt
ownership/contract investigation** (**not started**).

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
  lease/CAS `sync_mark_completed` / Celery return; non-default sync upload
  path remains bool-only/unwired.

**Не утверждать:** Qdrant operator support, live services, production
readiness, full immutable lifecycle, full durable cross-path
job↔published index binding (2.4c is async-worker only; sync non-default
upload remains bool-only/unwired), GC/retention for job/legacy objects,
orphan cleanup, complete fault injection, complete plan step 2,
project/release readiness. Local retention preview + guarded execution +
validated rollback operator surface is present after 2.3i. Immutable upload
originals + flat current view are present after 2.4a. Manager opt-in
publication receipt is present after 2.4b. Async-worker receipt persistence
is present after 2.4c.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.4c (latest)

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
- Этот docs-only Update-50 **не** перезапускал project tests.

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
- full immutable lifecycle beyond 2.4a/2.4b/2.4c: GC/retention for job-objects
  and legacy-previous recovery objects; orphan cleanup after failed
  transition; live concurrency/fault-injection for upload originals.
- full cross-path job↔published index binding beyond async-worker scope;
  API/UI surfaces; DB migration/model fields for index version/collection
  (out of 2.4d investigation scope until ownership is confirmed).

**Remaining honest limitations after 2.4c:**

- 2.4c is **async-worker only** — full durable cross-path job↔published index
  binding is **not** complete; non-default sync upload remains
  bool-only/unwired
- no migration/model field for index version/collection on the job
- no GC/retention for job objects or legacy recovery objects
- a failed transition can leave an orphaned new immutable object
- no live concurrency/fault-injection; full suite not run
- full default Mypy not claimed clean in this environment
- full plan step 2 / project / release / production readiness **not** complete

**Next candidate (not started):** **2.4d sync non-default upload receipt
ownership/contract investigation**. Candidate only — **not** completed work
and **not** started. Current read-only evidence: non-default upload in
`api/routers/upload.py` calls bool-returning
`_app._rebuild_vector_store_from_docs`; `api/app.py` owns that helper and its
ordinary `_build_vector_store` binding. These are shared/protected surfaces;
next session must confirm ownership/test impact **read-only** before edits
and choose the smallest test-first receipt propagation contract. Do **not**
prescribe an invented API, reopen 2.4b/2.4c, or mark 2.4d started/complete.

**Superseded / do not re-select:** 2.1–2.4c are complete. Historical
next-work text that still names **2.4a**, **2.4b**, **2.4c**, or generic
job↔index investigation as the next candidate is stale. Historical headings
containing `✅ START HERE` are archival.

### Следующий named candidate: 2.4d sync non-default upload receipt ownership/contract investigation (не начат)

Smallest safe framing: investigate ownership and the smallest test-first
receipt propagation contract for the non-default synchronous upload path.
**Not started.** **Do not re-select 2.4a, 2.4b, or 2.4c.** No active writer
and no unfinished next-candidate WIP at this handoff.

**Candidate ownership (confirm read-only next session):**

| Surface | Module / symbols | Notes |
|---------|------------------|-------|
| Non-default sync upload | `api/routers/upload.py` | calls bool-returning `_app._rebuild_vector_store_from_docs` |
| Sync rebuild helper owner | `api/app.py` | owns `_rebuild_vector_store_from_docs` and ordinary `_build_vector_store` binding |
| Opt-in manager entrypoint (consume only; do not re-open 2.4b) | `vectordb.manager.build_vector_store_with_publication` | already covered by 2.4b |
| Async worker receipt (do not re-open 2.4c) | `tasks/ingest_task.py` | already persists `index_publication` after 2.4c |

**Evidence-based boundary for 2.4d:**

- confirm ownership/test impact **read-only** before any edit
- choose the smallest test-first receipt propagation contract only after
  ownership is confirmed
- **no** invented API
- **no** reopening 2.4b manager or 2.4c async-worker surfaces without proven
  conflict
- **no** DB migration / model field unless investigation proves it is the
  only honest path — then **stop and re-scope**
- do **not** mark 2.4d started/complete from docs alone

**Plan source (direction only):** active untracked plan
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
§2 still carries the broader immutable/versioned originals + lifecycle bind
item (do **not** edit plan checkboxes here). 2.4a landed immutable originals;
2.4b landed the manager receipt; 2.4c landed async-worker receipt persistence;
2.4d is the sync non-default upload receipt ownership/contract investigation
candidate only.

### Historical 2.4c ownership notes (archive; 2.4c COMPLETE @ `999c90f`)

Landed async-worker receipt wiring is in §Контракт 2.4c above. **Do not
treat as next-work instruction.**

| Surface | Module / symbols | Focused tests |
|---------|------------------|---------------|
| Async worker completion | `tasks/ingest_task.py` | `tests/test_ingest_task.py`, `tests/test_ingestion_job_contract.py`, `tests/test_ingestion_liveness.py` |
| Opt-in manager entrypoint (consumed; not re-opened) | `vectordb.manager.build_vector_store_with_publication` | already covered by 2.4b |

**Gap closed by 2.4c (async-worker only):** durable `IngestionJob.result`
now carries `index_publication` from the exact opt-in manager invocation via
lease/CAS completion. **Gap still open:** non-default sync upload path
remains bool-only/unwired — that is the **2.4d** candidate direction, not a
claim that full cross-path linkage is complete.

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

- Re-opening completed 2.4c async-worker surfaces, 2.4b manager receipt
  surfaces, 2.4a upload write path, or retention operator surfaces without
  proven conflict
- Settings/policy rewrite, UI, Helm/PVC/object-storage migration
- Inventing an API for 2.4d before ownership confirmation
- DB migration / model field for index version/collection without proven need
- Full fault-injection matrix; concurrent multi-tenant load drills
- Live PostgreSQL/Redis/Celery/Chroma; push; deploy; production readiness
- Claiming full plan step 2, full immutable lifecycle, or full cross-path
  job/index-version binding “done” from async-worker wiring alone

### Stop / re-scope conditions

- Protected completed-slice surfaces change without an explicit conflict plan
- Target files become unexpectedly dirty / foreign WIP appears
- Scope requires multi-subsystem expansion (manifest + retention + upload +
  reindex + migration) in one turn
- Second independent verification fails after one allowed narrow correction
- Any push/deploy/live/destructive Git pressure without user authorization
- Exact owners cannot be confirmed read-only without inventing APIs — stop and
  report rather than guess

This docs-only turn did **not** run project tests and did **not** start the
next candidate.

## Definition of done / stop conditions

- **2.4c is complete** at implementation commit `999c90f` with the
  verification ledger above, **only at the bounded async-worker scope**.
  **Do not re-select 2.4c.**
- **2.4b is complete** at implementation commit `29be31a`. **Do not
  re-select 2.4b.**
- **2.4a is complete** at implementation commit `a1dcd5c`. **Do not
  re-select 2.4a.**
- **Do not re-select 2.3i** (`ac4b317`) or **2.1–2.3h.**
- Next candidate **2.4d** is **done only after** read-only ownership
  confirmation, a chosen smallest test-first receipt propagation contract,
  Grok tests-first evidence for that bounded contract, one independent
  proportional gate, protected-surface checks, scoped diff-check, and local
  explicit-path commit. Do **not** mark 2.4d started/complete from docs alone.
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

# Session handoff

**Обновлено:** 2026-08-07 (Update-68 records completed **2.6d** @ `5b9e384`;
next ordered candidate **2.6e** residual fault injection — concurrency/lock)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-68**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `5b9e384` — **2.6d** cleanup discard-path fault injection |
| Previous implementation | `3ba7986` — **2.6c** embeddings fault |
| Previous docs | `6cbb97c` — Update-67 |
| This Update-68 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.4k + 2.5a + 2.5b + 2.6a–2.6d** |
| Full plan §2 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **2.6e** concurrency/lock residual (**not started**) |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (2.6d):** focused lifecycle + staging green; Ruff clean.
Full suite / live drills **not** run.

**Key invariant:** failed jobs with `source_path`-matched job-objects →
`retained_after_failed_transition` (intentional retention, **not** GC).
`auto_delete_eligible` is always `False`.

### Plan §2 map (honest — plan checkboxes stay open)

| Plan §2 bullet (order) | Local work | Residual |
|------------------------|------------|----------|
| 2.1–2.5b | as prior ledger | live DoD open |
| **fault injection expand** | **2.6a–2.6d** | **← next 2.6e+** concurrency |
| live multi-service drills | not started | **opt-in only**; migrations **019–022** |

### Named fault points (local)

| Point | Slice | Boundary |
|-------|-------|----------|
| `inventory_write` | 2.6a | inventory durable commit |
| `manifest_publish` | 2.6a | manifest durable commit |
| `known_query` | 2.6b | staged known-query validation |
| `embeddings` | 2.6c | staged embedding dimension validation |
| `cleanup` | 2.6d | unpublished candidate discard |

### Protected state (do not touch/stage/remove without request)

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked (incl.):** pytest temps, presentations, `_NEXT_SESSION.md`
  (pointer only), `rag-remediation-plan-2026-08-03.md` (no checkbox edits)

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only.

---

## Быстрый старт следующей сессии

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -5 --oneline` (**actual Git wins**).
4. Read **only** top **Update-68** in `AGENT_STATE.md` + this capsule.
   Do **not** reselect **2.1–2.6d**.
5. Execute **one** named slice: default **2.6e** (below).
6. Tests-first → proportional gate → local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live multi-service
drills, destructive Git, production claims.

---

## Назначение и приоритет источников

1. Fresh `git status` / `git log`.
2. Top `AGENT_STATE.md` (**Update-68**) + this capsule.
3. Dirty backlog/README/audit/plan_sol — protected; **stale**.
4. `_NEXT_SESSION.md` — pointer only.
5. Active plan — **do not** edit checkboxes casually.
6. One user turn = one named atomic slice.

**Authoritative implementation:** `5b9e384` (**2.6d**).

---

## Карта реализации (ledger)

| Slice | Что | Implementation | Status docs |
|-------|-----|----------------|-------------|
| **2.1** | publication inventory wiring | `e8da185` | `3cc939b` |
| **2.2** | post-publish bounded retention | `f0cb6ee` | `30a8404` |
| **2.3a–2.3i** | index preview/rollback/retention operator | see prior ledger | Updates 40–46 |
| **2.4a** | immutable upload originals | `a1dcd5c` | Update-48 |
| **2.4b** | build publication receipt | `29be31a` | Update-49 |
| **2.4c** | async worker receipt | `999c90f` | Update-50 |
| **2.4d** | sync non-default upload receipt | `dfbbca0` | Update-51/52 |
| **2.4e** | job-object classify | `13be7d9` | Update-53/54 |
| **2.4f** | tenant load + preview | `68cf045` | Update-55 |
| **2.4g** | fail-closed retention policy | `1ccb39b` | Update-56 |
| **2.4h** | guarded no-op retention command | `9761caf` | Update-57 |
| **2.4i** | operator CLI | `f0f79b9` | Update-58 |
| **2.4j** | failed-transition ownership annotations | `ea3f59e` | Update-59/60 |
| **2.4k** | job status load + CLI annotations | `9e358f1` | Update-61 |
| **2.5a** | admin GET job-object inventory | `0855528` | Update-62 |
| **2.5b** | durable job↔index publication bind | `6dbabef` | Update-63 + Update-64 |
| **2.6a** | inventory/publish fail-closed fault injection | `3f3c699` | Update-65 |
| **2.6b** | known-query fail-closed fault injection | `0e4451e` | Update-66 |
| **2.6c** | embeddings fail-closed fault injection | `3ba7986` | Update-67 |
| **2.6d** | cleanup discard-path fault injection | `5b9e384` | **Update-68** |

**Do not re-select 2.1–2.6d.**

---

## Контракт 2.5b (job↔index lifecycle bind) — COMPLETE

At `6dbabef`:

- migration `alembic/versions/022_ingestion_job_index_bind.py`
- model columns on `IngestionJob`:
  - `index_active_collection`
  - `index_previous_collection`
  - `index_manifest_generation`
- `ingestion.jobs.index_publication_bind_values(result)`
- written in `mark_job_completed` + `sync_mark_completed`
- `job_public_dict` → `index_publication_bind` (`null` when unbound)
- existing `result.index_publication` JSON (2.4c/2.4d) unchanged

**Boundary:** bind/persist/surface only. No deletion, age/budget, fault
injection, live migration drill.

**Verification:** 51 passed focused; Ruff clean.

### Reference commands (2.5b)

```powershell
python -m pytest tests/test_ingestion_job_contract.py tests/test_ingest_task.py tests/test_admin_job_object_inventory.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-5b-<unique>
python -m ruff check alembic/versions/022_ingestion_job_index_bind.py db/models.py ingestion/jobs.py tests/test_ingestion_job_contract.py
```

---

## Контракт 2.5a (admin job-object inventory) — COMPLETE

At `0855528`:

- `GET /api/admin/job-objects/inventory` — admin, JWT tenant
- `load_and_run_operator_preview(..., execute=False)`
- audit `job_object_inventory_preview`
- no `execution` in response
- composition: `ingestion/job_object_operator.py`

---

## Контракт 2.4k / 2.4j (status + annotations) — COMPLETE

- `sync_list_job_statuses_for_tenant` + CLI/admin annotations path
- failed+protected → `retained_after_failed_transition`

---

## 2.6a (inventory/publish fail-closed fault injection) — COMPLETE

At `3f3c699`:

- `vectordb/index_lifecycle_faults.py` — points `inventory_write`,
  `manifest_publish`; `arm_fault` / `fault_armed` / `maybe_inject`; no-op
  default; no env/settings switch
- hooks immediately before durable `os.replace` in
  `index_retention._write_inventory` and
  `index_manifest.publish_active_collection`
- `tests/test_index_lifecycle_fault_injection.py` — inventory-write fault
  keeps active manifest + discards candidate; publish fault discards
  candidate without live switch; unarmed happy path still publishes

**Boundary:** inventory/publish commit-boundary injection only. No deletion,
age/budget, embeddings/validation/cleanup matrix, concurrency matrix, or
live drills.

**Verification:** 6 passed focused; Ruff clean. Pre-existing unrelated red
in `test_runtime_retention_signature_source_boundary_and_no_production_callers`.

### Reference commands (2.6a)

```powershell
python -m pytest tests/test_index_lifecycle_fault_injection.py tests/test_index_runtime_switch.py::test_inventory_record_failure_does_not_publish_and_discards_candidate tests/test_index_runtime_switch.py::test_publish_failure_removes_unpublished_candidate_and_preserves_manifest -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6a-<unique>
python -m ruff check vectordb/index_lifecycle_faults.py vectordb/index_retention.py vectordb/index_manifest.py tests/test_index_lifecycle_fault_injection.py
```

---

## 2.6b (known-query fail-closed fault injection) — COMPLETE

At `0e4451e`:

- point `known_query` in `vectordb/index_lifecycle_faults.py`
- hook at start of `validate_staged_known_query` (after lock, before smoke)
- known-query fault → no inventory, no publish, candidate discarded, active
  manifest unchanged

**Boundary:** known-query validation only. No embeddings/cleanup matrix,
concurrency matrix, deletion, age/budget, or live drills.

**Verification:** 14 passed focused; Ruff clean.

### Reference commands (2.6b)

```powershell
python -m pytest tests/test_index_lifecycle_fault_injection.py tests/test_index_staging.py tests/test_index_runtime_switch.py::test_known_query_failure_removes_candidate_without_changing_active -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6b-<unique>
python -m ruff check vectordb/index_lifecycle_faults.py vectordb/index_staging.py tests/test_index_lifecycle_fault_injection.py
```

---

## 2.6c (embeddings fail-closed fault injection) — COMPLETE

At `3ba7986`:

- point `embeddings` in `vectordb/index_lifecycle_faults.py`
- hook in `_validate_candidate` after count checks, before dimension probe
- `IndexLifecycleFaultError` re-raised unwrapped from `build_staged_collection`
- embeddings fault → staging cleans partial candidate; no known-query /
  inventory / publish; active manifest unchanged

**Boundary:** embeddings dimension validation only. No cleanup-discard matrix,
concurrency matrix, deletion, age/budget, or live drills.

**Verification:** 15 passed focused; Ruff clean.

### Reference commands (2.6c)

```powershell
python -m pytest tests/test_index_lifecycle_fault_injection.py tests/test_index_staging.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6c-<unique>
python -m ruff check vectordb/index_lifecycle_faults.py vectordb/index_staging.py tests/test_index_lifecycle_fault_injection.py
```

---

## 2.6d (cleanup discard-path fault injection) — COMPLETE

At `5b9e384`:

- point `cleanup` in `vectordb/index_lifecycle_faults.py`
- hook at start of `_cleanup_candidate` (before delete_collection)
- `IndexLifecycleFaultError` re-raised unwrapped
- cleanup fault after known-query discard or embeddings self-cleanup →
  no inventory / no publish; active unchanged; orphan candidate may remain
  only because discard failed (not promoted)

**Boundary:** cleanup discard path only. No concurrency matrix, deletion
age/budget, or live drills.

**Verification:** lifecycle + staging focused green; Ruff clean.

### Reference commands (2.6d)

```powershell
python -m pytest tests/test_index_lifecycle_fault_injection.py tests/test_index_staging.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6d-<unique>
python -m ruff check vectordb/index_lifecycle_faults.py vectordb/index_staging.py tests/test_index_lifecycle_fault_injection.py
```

---

## Следующий named candidate: 2.6e residual fault injection (не начат)

**Plan order:** residual of section 2 fault-injection after **2.6d**.
**Name:** **2.6e — concurrency / lock contention fail-closed** (preferred),
**or** worker-recovery atomic — **one** per turn.

### Intent

1. Prove same-tenant concurrent rebuild / lock contention stays fail-closed
   (no double-publish, no torn active, no dangerous live candidate).
2. Prefer tests-first with existing tenant lock + fault hooks; no live services.
3. Do not also invent age-budget deletion in the same turn.

### Suggested acceptance (tests-first)

1. One focused concurrency or lock-contention scenario + proportional gate.
2. No auto-delete / age-budget / plan checkbox edits.
3. Scoped Ruff + green tests.
4. Local commit only; optional handoff Update after slice.

### Explicitly out of 2.6e

- real FS job-object deletion / age-budget
- live PG/Redis/Celery/Chroma (opt-in separate)
- plan checkbox bulk-edit
- push / deploy

### Reference commands (2.6e — after work lands)

```powershell
python -m pytest tests/<new_or_targeted> -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6e-<unique>
```

---

## Что остаётся открытым (после 2.6d / Update-68)

- **2.6e+** concurrency / lock / worker recovery (next ordered)
- live migrations **019–022** + worker recovery + advisory-lock drills
  (**opt-in**)
- real job-object / legacy-previous **FS deletion** (needs product opt-in)
- age/budget thresholds
- orphan cleanup **mutations**
- job-object retention **execute** HTTP
- full suite, release gates, project/production readiness

**Superseded next-work text:** any handoff still saying next is 2.6c, 2.6d,
or vague residual without naming **2.6e** is **stale**.

---

## Windows / tooling notes

- Unique ignored basetemp: `--basetemp=.tmp/pytest-<slice>`
- Full `requirements-dev.lock` may hit Linux-only wheel issues — do not
  blind-retry install without portability task
- One atomic slice per user turn; stop after commit + optional docs

---

## Do not

- Re-select **2.1–2.6d**
- Treat failed job-objects as deletable orphans
- Invent auto-delete classes or age/budget thresholds without opt-in
- Edit plan checkboxes from casual docs turns
- Push / deploy / live multi-service without explicit user opt-in
- Use grepped historical `✅ START HERE` as work queue

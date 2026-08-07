# Session handoff

**Обновлено:** 2026-08-07 (Update-70 records completed **2.6f** @ `53a398f`;
next ordered candidate **2.6g** worker outage/recovery)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-70**). Plan source:
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

| Факт | Значение |
|------|----------|
| Latest implementation | `53a398f` — **2.6f** duplicate job fail-closed |
| Previous implementation | `fbc2293` — **2.6e** lock contention |
| Locally complete | **2.1–2.5b + 2.6a–2.6f** |
| Next ordered | **2.6g** worker outage/recovery (**not started**) |
| Full plan §2 / prod | **NOT** complete / **NOT** claimed |
| Gates | no push / deploy / live services without opt-in |

**Verification (2.6f):** 8 passed focused/adjacent; Ruff clean.

### Plan §2 residual

| Residual | Status |
|----------|--------|
| fault inject inventory→cleanup | **2.6a–2.6d** local |
| lock contention | **2.6e** local |
| duplicate job | **2.6f** local |
| worker outage/recovery | **← next 2.6g** |
| live multi-service drills | opt-in only |

### Protected

Dirty: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`  
Untracked plan/temps/`_NEXT_SESSION.md` — pointer only.

---

## Быстрый старт

1. `git status` / `git log -5`
2. Top **Update-70** only
3. One slice: default **2.6g**
4. Local commit only; yield after one slice

**Authoritative implementation:** `53a398f` (**2.6f**).

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
| **2.6d** | cleanup discard-path fault injection | `5b9e384` | Update-68 |
| **2.6e** | same-tenant lock contention fail-closed | `fbc2293` | Update-69 |
| **2.6f** | duplicate job fail-closed (no double publish) | `53a398f` | **Update-70** |

**Do not re-select 2.1–2.6f.**

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

## 2.6e (same-tenant lock contention fail-closed) — COMPLETE

At `fbc2293`:

- `tests/test_index_lock_contention.py` — in-process advisory lock registry
- held lock + short wait → `TenantIndexLockTimeout`, no staging, active unchanged
- serialized concurrent rebuilds → monotonic generation, valid active
- adjacent: `test_tenant_index_lock` publish mock includes `previous_collection`

**Boundary:** concurrency/lock contention on rebuild path only. No live PG,
no worker-recovery matrix, no deletion/age-budget.

**Verification:** 11 passed; Ruff clean.

### Reference commands (2.6e)

```powershell
python -m pytest tests/test_index_lock_contention.py tests/test_tenant_index_lock.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6e-<unique>
python -m ruff check tests/test_index_lock_contention.py tests/test_tenant_index_lock.py
```

---

## 2.6f (duplicate job fail-closed) — COMPLETE

At `53a398f`:

- `tests/test_duplicate_job_fail_closed.py`
- terminal completed/failed redelivery → claim fail-closed before load/build
- concurrent claim → one winner, one `JobOwnershipError`
- idempotent create reuse → single durable row
- no production code change (existing CAS claim is the contract)

**Boundary:** duplicate job delivery only. Worker outage/recovery is **2.6g**.
No live multi-service, no deletion/age-budget.

**Verification:** 8 passed; Ruff clean.

### Reference commands (2.6f)

```powershell
python -m pytest tests/test_duplicate_job_fail_closed.py tests/test_ingestion_liveness.py::test_worker_refuses_duplicate_claim_before_load -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6f-<unique>
```

---

## Следующий named candidate: 2.6g residual (не начат)

**Name:** **2.6g — worker outage/recovery fail-closed** (preferred next residual
of plan §2 fault injection).

### Intent

1. Prove stale lease / reaper / lost-ownership paths fail closed without
   double-complete or silent index publish after outage.
2. Prefer tests-first against existing liveness/reaper contracts; no live Celery
   without opt-in.
3. One atomic slice only.

### Explicitly out of 2.6g

- live Redis/Postgres/Celery multi-service drills (opt-in)
- age-budget deletion / plan checkbox bulk-edit
- push / deploy

---

## Что остаётся открытым (после 2.6f / Update-70)

- **2.6g** worker outage/recovery
- live migrations **019–022** + advisory-lock drills (**opt-in**)
- real job-object FS deletion / age-budget
- full suite / release / production readiness

**Superseded next-work text:** next is **2.6g**, not 2.6f/2.6e.

---

## Do not

- Re-select **2.1–2.6f**
- Push / deploy / live multi-service without opt-in
- Invent auto-delete / age-budget without opt-in

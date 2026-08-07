# Session handoff

**Обновлено:** 2026-08-07 (Update-66 records completed **2.6b** @ `0e4451e`;
next ordered candidate **2.6c** residual fault injection)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-66**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `0e4451e` — **2.6b** known-query fail-closed fault injection |
| Previous implementation | `3f3c699` — **2.6a** inventory/publish faults |
| Previous docs | `78b0e8a` — Update-65 |
| This Update-66 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Branch advisory | was `ahead 112` after 2.6b impl — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.4k + 2.5a + 2.5b + 2.6a + 2.6b** |
| Full plan §2 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **2.6c** residual fault injection (**not started**) |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (2.6b):** focused **14 passed**
(`tests/test_index_lifecycle_fault_injection.py` + adjacent known-query /
inventory / publish paths + `tests/test_index_staging.py`); Ruff clean.
Full suite / live drills **not** run.

**Key invariant:** failed jobs with `source_path`-matched job-objects →
`retained_after_failed_transition` (intentional retention, **not** GC).
`auto_delete_eligible` is always `False`.

### Plan §2 map (honest — plan checkboxes stay open)

| Plan §2 bullet (order) | Local work | Residual |
|------------------------|------------|----------|
| 2.1 inventory under lock | 2.1 (+ related) | live DoD open |
| 2.2 bounded retention | 2.2, 2.3f–2.3i | live DoD open |
| operator surface rollback/retention | index 2.3b–2.3i; job-objects 2.4i–2.5a | no job-object delete HTTP |
| immutable originals + lifecycle bind | 2.4a–2.5b | no real FS delete / age-budget |
| **fault injection expand** | **2.6a + 2.6b** | **← next 2.6c+** |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in only**; migrations **019–022** |

### Module owners (do not reopen without proven conflict)

| Module / path | Slice | Role |
|---------------|-------|------|
| `vectordb/index_lifecycle_faults.py` | **2.6a–2.6b** | inventory_write / manifest_publish / **known_query** |
| `vectordb/index_staging.py` | staging + **2.6b** hook | known-query validation boundary |
| `vectordb/index_retention.py` + `index_manifest.py` | 2.1 + **2.6a** hooks | durable inventory + publish commits |
| `vectordb/*` index inventory/retention/rollback | 2.1–2.3i | Chroma subsystem — must **not** delete job-objects |
| `api/routers/upload.py` | 2.4a + receipts | create path |
| `tasks/ingest_task.py` | 2.4c | async receipt + complete |
| `ingestion/jobs.py` | 2.4f/2.4k/**2.5b** | statuses + index bind |
| `db/models.py` + `alembic/versions/022_*` | **2.5b** | bind columns + migration |
| job-object stack | 2.4e–2.5a | classify / policy / CLI / admin GET |

### Protected state (do not touch/stage/remove without request)

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked (incl.):** `.grok-prompts/`, `.pytest_tmp*/`, presentations,
  `_NEXT_SESSION.md` (**pointer only — not routing authority**),
  `rag-remediation-plan-2026-08-03.md` (active plan — **no checkbox edits**
  casually), architecture HTML, etc.

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only.

---

## Быстрый старт следующей сессии

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -5 --oneline` (**actual Git wins**;
   known impl `0e4451e` / **2.6b**).
4. Read **only** top **Update-66** in `AGENT_STATE.md` + this capsule.
   Do **not** reselect **2.1–2.6b**.
5. Execute **one** named slice: default **2.6c** (below). Announce
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Tests-first → proportional gate → explicit-path local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma drills, destructive Git, production claims.

---

## Назначение и приоритет источников

1. Fresh `git status` / `git log` — filesystem/Git truth.
2. Top `AGENT_STATE.md` (**Update-66**) + this capsule.
3. Dirty `BACKLOG.md` / `README.md` / `audit_gpt_*` / `plan_sol_23_07_26` —
   protected user state; **stale**; do not override Update-66.
4. `_NEXT_SESSION.md` — pointer only.
5. `rag-remediation-plan-2026-08-03.md` — active plan direction; **do not**
   edit checkboxes casually.
6. One user turn = one named atomic slice.

**Authoritative implementation:** `0e4451e` (**2.6b**).

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
| **2.6b** | known-query fail-closed fault injection | `0e4451e` | **Update-66** |

**Do not re-select 2.1–2.6b.**

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

## Следующий named candidate: 2.6c residual fault injection (не начат)

**Plan order:** residual of section 2 fault-injection after **2.6b**.
**Name:** **2.6c — embeddings (or cleanup) fail-closed injection** (preferred),
**or** a single concurrency / lock-contention atomic — **one** per turn.

### Intent

1. Prefer next named point on staged embeddings/build validation or cleanup
   discard path; prove active manifest unchanged and no dangerous live candidate.
2. Reuse `index_lifecycle_faults` pattern; no-op default; no env arming switch.
3. Do not dump full concurrency + worker-recovery matrix in the same turn.

### Suggested acceptance (tests-first)

1. One new named fault point + focused tests on the build path.
2. No auto-delete / age-budget / plan checkbox edits.
3. Scoped Ruff + proportional adjacent green.
4. Local commit only; optional handoff Update after slice.

### Explicitly out of 2.6c

- real FS job-object deletion / age-budget
- live PG/Redis/Celery/Chroma (opt-in separate)
- full concurrent + worker-recovery multi-slice dump
- plan checkbox bulk-edit
- push / deploy

### Reference commands (2.6c — after work lands)

```powershell
python -m pytest tests/<new_or_targeted> -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6c-<unique>
```

---

## Что остаётся открытым (после 2.6b / Update-66)

- **2.6c+** residual fault injection (next ordered)
- concurrent same-tenant uploads, duplicate job, worker outage/recovery,
  lock contention (later sub-slices)
- live migrations **019–022** + worker recovery + advisory-lock drills
  (**opt-in**)
- real job-object / legacy-previous **FS deletion** (needs product opt-in)
- age/budget thresholds
- orphan cleanup **mutations**
- job-object retention **execute** HTTP
- full suite, release gates, project/production readiness

**Superseded next-work text:** any handoff still saying next is 2.6a, 2.6b,
or vague residual without naming **2.6c** is **stale**.

---

## Windows / tooling notes

- Unique ignored basetemp: `--basetemp=.tmp/pytest-<slice>`
- Full `requirements-dev.lock` may hit Linux-only wheel issues — do not
  blind-retry install without portability task
- One atomic slice per user turn; stop after commit + optional docs

---

## Do not

- Re-select **2.1–2.6b**
- Treat failed job-objects as deletable orphans
- Invent auto-delete classes or age/budget thresholds without opt-in
- Edit plan checkboxes from casual docs turns
- Push / deploy / live multi-service without explicit user opt-in
- Use grepped historical `✅ START HERE` as work queue

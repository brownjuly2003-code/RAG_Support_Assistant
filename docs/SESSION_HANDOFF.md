# Session handoff

**Обновлено:** 2026-08-07 (Update-65 records completed **2.6a** @ `3f3c699`;
next ordered candidate **2.6b** residual fault injection)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-65**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `3f3c699` — **2.6a** inventory/publish fail-closed fault injection |
| Latest impl docs before Update-65 | Update-64 @ `5ff8cef` (transparency after 2.5b) |
| This Update-65 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Previous implementation | `6dbabef` — **2.5b** durable job↔index lifecycle bind |
| Branch advisory | was `ahead 110` after 2.6a impl — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.4k + 2.5a + 2.5b + 2.6a** |
| Full plan §2 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **2.6b** residual fault injection (**not started**) |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (2.6a):** focused **6 passed**
(`tests/test_index_lifecycle_fault_injection.py` + adjacent inventory/publish
fail paths); Ruff clean on scoped paths. Pre-existing unrelated red:
`test_runtime_retention_signature_source_boundary_and_no_production_callers`
(admin_ops retention caller). Full suite / live drills **not** run.

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
| **fault injection expand** | **2.6a** inventory/publish | **← next 2.6b+** |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in only**; migrations **019–022** |

### Module owners (do not reopen without proven conflict)

| Module / path | Slice | Role |
|---------------|-------|------|
| `vectordb/index_lifecycle_faults.py` | **2.6a** | named inventory_write / manifest_publish fault points |
| `vectordb/index_retention.py` + `index_manifest.py` | 2.1 + **2.6a** hooks | durable inventory + publish commit boundaries |
| `vectordb/*` index inventory/retention/rollback | 2.1–2.3i | Chroma subsystem — must **not** delete job-objects |
| `api/routers/upload.py` | 2.4a + receipts | create path: job → immutable → legacy-previous → flat |
| `tasks/ingest_task.py` | 2.4c | async receipt + complete |
| `ingestion/jobs.py` | 2.4f/2.4k/**2.5b** | known refs, statuses, **index bind columns**, public dict |
| `db/models.py` + `alembic/versions/022_*` | **2.5b** | bind columns + migration |
| `ingestion/job_object_inventory.py` | 2.4e/2.4f | classify + tenant preview |
| `ingestion/job_object_retention.py` | 2.4g/2.4h | fail-closed policy + guarded no-op |
| `ingestion/job_object_orphans.py` | 2.4j | transition ownership annotations |
| `ingestion/job_object_operator.py` | 2.4i–2.5a | shared composition + load_and_run |
| `scripts/preview_job_object_inventory.py` | 2.4i/2.4k | thin operator CLI |
| `api/routers/admin_ops.py` | 2.5a (+ index admin) | `GET /admin/job-objects/inventory` read-only |

### Protected state (do not touch/stage/remove without request)

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked (incl.):** `.grok-prompts/`, `.pytest_tmp*/`, presentations,
  `_NEXT_SESSION.md` (**pointer only — not routing authority**),
  `rag-remediation-plan-2026-08-03.md` (active plan — **no checkbox edits**
  from docs/impl turns without explicit request), architecture HTML, etc.

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only. Never grepping
historical `START HERE`. Never treating dirty backlog/legacy plan as queue.

---

## Быстрый старт следующей сессии

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -5 --oneline` (**actual Git wins**
   over hashes below; known impl `3f3c699` / **2.6a**).
4. Read **only** top **Update-65** in `AGENT_STATE.md` + this capsule.
   Do **not** reselect **2.1–2.6a**.
5. Execute **one** named slice: default **2.6b** (below). Announce
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Tests-first → proportional gate → explicit-path local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma drills, destructive Git, production claims.

---

## Назначение и приоритет источников

1. Fresh `git status` / `git log` — filesystem/Git truth.
2. Top `AGENT_STATE.md` (**Update-65**) + this capsule.
3. Dirty `BACKLOG.md` / `README.md` / `audit_gpt_*` / `plan_sol_23_07_26` —
   protected user state; **stale**; do not override Update-65.
4. `_NEXT_SESSION.md` — pointer only.
5. `rag-remediation-plan-2026-08-03.md` — active plan direction; **do not**
   edit checkboxes casually.
6. One user turn = one named atomic slice.

**Authoritative implementation:** `3f3c699` (**2.6a**). Do not invent future
docs SHAs inside content.

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
| **2.6a** | inventory/publish fail-closed fault injection | `3f3c699` | **Update-65** |

**Do not re-select 2.1–2.6a.**

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

## Следующий named candidate: 2.6b residual fault injection (не начат)

**Plan order:** residual of §2 fault-injection bullet after **2.6a**.
**Name:** **2.6b — validation/known-query (or embeddings) fail-closed
injection** (preferred first residual), **or** a single concurrency /
lock-contention atomic if product priority shifts — **one** per turn.

### Intent

Extend named lifecycle fault points beyond inventory/publish, still
tests-first and fail-closed:

1. Prefer next point on known-query/validation (or embeddings) before
   inventory, proving active manifest unchanged and candidate discarded.
2. Reuse `vectordb/index_lifecycle_faults.py` pattern — add a **known** point
   name; keep no-op default; no env arming switch unless later opt-in.
3. Do **not** start full concurrency + worker-recovery matrix in the same
   turn as a new validation fault point.

### Suggested acceptance (tests-first)

1. One new named fault point + focused tests on the build path.
2. No auto-delete / age-budget / plan checkbox edits.
3. Scoped Ruff + proportional adjacent green.
4. Local commit only; optional handoff Update after slice.

### Explicitly out of 2.6b

- real FS job-object deletion / age-budget
- live PG/Redis/Celery/Chroma (opt-in separate)
- full concurrent + worker-recovery matrix as a multi-slice dump
- plan checkbox bulk-edit
- push / deploy

### Reference commands (2.6b — after work lands)

```powershell
python -m pytest tests/<new_or_targeted> -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6b-<unique>
```

---

## Что остаётся открытым (после 2.6a / Update-65)

- **2.6b+** residual fault injection (next ordered)
- concurrent same-tenant uploads, duplicate job, worker outage/recovery,
  lock contention (later sub-slices)
- live migrations **019–022** + worker recovery + advisory-lock drills
  (**opt-in**)
- real job-object / legacy-previous **FS deletion** (needs product opt-in;
  policy currently fail-closed empty)
- age/budget thresholds
- orphan cleanup **mutations**
- job-object retention **execute** HTTP
- full suite, release gates, project/production readiness

**Superseded next-work text:** any handoff still saying next is 2.5b, 2.6a,
or vague “re-scope only” without naming **2.6b** is **stale**.

---

## Windows / tooling notes

- Unique ignored basetemp: `--basetemp=.tmp/pytest-<slice>`
- Full `requirements-dev.lock` may hit Linux-only wheel issues — do not
  blind-retry install without portability task
- One atomic slice per user turn; stop after commit + optional docs

---

## Do not

- Re-select **2.1–2.6a**
- Treat failed job-objects as deletable orphans
- Invent auto-delete classes or age/budget thresholds without opt-in
- Edit plan checkboxes from casual docs turns
- Push / deploy / live multi-service without explicit user opt-in
- Use grepped historical `✅ START HERE` as work queue

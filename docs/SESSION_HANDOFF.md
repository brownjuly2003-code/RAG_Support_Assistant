# Session handoff

**Обновлено:** 2026-08-07 (Update-72 records completed **2.6g** @ `f347feb`;
previous docs Update-71 `0fda397` / Update-70 `767d283`; next is opt-in live
§2 multi-service **or** plan §3 without live opt-in)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-72**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `f347feb` — **2.6g** worker outage/recovery fail-closed |
| Previous implementation | `53a398f` — **2.6f** duplicate job |
| Latest known docs before this Update | Update-71 `0fda397` |
| This Update-72 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Branch advisory | was `ahead 123` after 2.6g impl — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.4k + 2.5a + 2.5b + 2.6a–2.6g** |
| Full plan §2 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **opt-in live §2 multi-service** **or** plan **§3** |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (2.6g):** focused **14 passed**
(`tests/test_worker_outage_fail_closed.py` + adjacent liveness/duplicate);
full liveness **55 passed**; Ruff clean on scoped paths. Full suite / live
drills **not** run.

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
| **fault injection expand** | **2.6a–2.6g** | **local residual closed** |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in only**; migrations **019–022** |

### Fault-injection inventory (local, complete)

| Contract | Slice | Impl | Primary tests / modules |
|----------|-------|------|-------------------------|
| `inventory_write` / `manifest_publish` | 2.6a | `3f3c699` | `index_lifecycle_faults` + retention/manifest hooks |
| `known_query` | 2.6b | `0e4451e` | `validate_staged_known_query` |
| `embeddings` | 2.6c | `3ba7986` | `_validate_candidate` |
| `cleanup` | 2.6d | `5b9e384` | `_cleanup_candidate` |
| tenant lock contention | 2.6e | `fbc2293` | `tests/test_index_lock_contention.py` |
| duplicate job / no double publish | 2.6f | `53a398f` | `tests/test_duplicate_job_fail_closed.py` |
| worker outage/recovery / no silent publish | 2.6g | `f347feb` | `tasks/ingest_task.py` + `tests/test_worker_outage_fail_closed.py` |

### Module owners (do not reopen without proven conflict)

| Module / path | Slice | Role |
|---------------|-------|------|
| `vectordb/index_lifecycle_faults.py` | 2.6a–2.6d | named no-op-by-default inject points |
| `vectordb/index_retention.py` / `index_manifest.py` | 2.1 + 2.6a | durable inventory + publish commits |
| `vectordb/index_staging.py` | staging + 2.6b–2.6d | known_query / embeddings / cleanup |
| `vectordb/tenant_lock.py` + manager build path | 2.6e | same-tenant rebuild serialization |
| `ingestion/jobs.py` claim CAS | 2.4k/2.5b + 2.6f | queued→running; terminal refuse redelivery |
| `tasks/ingest_task.py` | 2.4c + 2.6f + **2.6g** | claim + phase lease probes before load/index/complete |
| `ingestion/liveness.py` | 4.3 + 2.6g | lease heartbeat + independent reaper |
| job-object stack | 2.4e–2.5a | classify / policy / CLI / admin GET |

### Protected state (do not touch/stage/remove without request)

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked (incl.):** `.grok-prompts/`, `.pytest_tmp*/`, presentations,
  `_NEXT_SESSION.md` (**pointer only — not routing authority**),
  `rag-remediation-plan-2026-08-03.md` (active plan — **no checkbox edits**
  casually), architecture HTML, etc.

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only. Never grepping
historical `START HERE`. Never treating dirty backlog/legacy plan as queue.

---

## Быстрый старт следующей сессии

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -5 --oneline` (**actual Git wins**
   over hashes below; known impl `f347feb` / **2.6g**).
4. Read **only** top **Update-72** in `AGENT_STATE.md` + this capsule.
   Do **not** reselect **2.1–2.6g**.
5. Execute **one** named slice: **opt-in live §2 multi-service** **or**
   plan **§3** start (after reading §3 DoD). Announce
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Tests-first → proportional gate → explicit-path local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma drills, destructive Git, production claims.

---

## Назначение и приоритет источников

1. Fresh `git status` / `git log` — filesystem/Git truth.
2. Top `AGENT_STATE.md` (**Update-72**) + this capsule.
3. Dirty `BACKLOG.md` / `README.md` / `audit_gpt_*` / `plan_sol_23_07_26` —
   protected user state; **stale**; do not override Update-72.
4. `_NEXT_SESSION.md` — pointer only.
5. `rag-remediation-plan-2026-08-03.md` — active plan direction; **do not**
   edit checkboxes casually.
6. One user turn = one named atomic slice.

**Authoritative implementation:** `f347feb` (**2.6g**). Do not invent future
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
| **2.6a** | inventory/publish fail-closed fault injection | `3f3c699` | Update-65 |
| **2.6b** | known-query fail-closed fault injection | `0e4451e` | Update-66 |
| **2.6c** | embeddings fail-closed fault injection | `3ba7986` | Update-67 |
| **2.6d** | cleanup discard-path fault injection | `5b9e384` | Update-68 |
| **2.6e** | same-tenant lock contention fail-closed | `fbc2293` | Update-69 |
| **2.6f** | duplicate job fail-closed (no double publish) | 53a398f | Update-70 + Update-71 |
| **2.6g** | worker outage/recovery fail-closed (no silent publish) | 347feb | **Update-72** |

**Do not re-select 2.1–2.6g.**

---

## Контракт 2.6f (duplicate job) — COMPLETE

At `53a398f`:

- `tests/test_duplicate_job_fail_closed.py`
- terminal completed/failed redelivery → `JobOwnershipError` before load/build
- concurrent claim → one winner, one fail-closed loser
- idempotent create reuse → single durable row
- production claim already requires `status == "queued"` CAS (no code change)

**Boundary:** duplicate job delivery only. Worker outage/recovery closed in **2.6g**.

**Verification:** 8 passed focused/adjacent; Ruff clean.

### Reference commands (2.6f)

```powershell
python -m pytest tests/test_duplicate_job_fail_closed.py tests/test_ingestion_liveness.py::test_worker_refuses_duplicate_claim_before_load -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6f-<unique>
python -m ruff check tests/test_duplicate_job_fail_closed.py
```

---

## Краткие контракты 2.6a–2.6e (COMPLETE)

### 2.6a @ `3f3c699`

Named points `inventory_write` / `manifest_publish`; hooks before durable
`os.replace`; active unchanged on inventory fail; no live candidate on publish
fail. Tests: `tests/test_index_lifecycle_fault_injection.py`.

### 2.6b @ `0e4451e`

Point `known_query` at start of `validate_staged_known_query`.

### 2.6c @ `3ba7986`

Point `embeddings` in `_validate_candidate`; fault re-raised unwrapped from
`build_staged_collection`.

### 2.6d @ `5b9e384`

Point `cleanup` before `delete_collection` in `_cleanup_candidate`.

### 2.6e @ `fbc2293`

`tests/test_index_lock_contention.py` — held lock → `TenantIndexLockTimeout`;
serialized rebuilds → monotonic generation.

### Lifecycle fault points module

`vectordb/index_lifecycle_faults.py` — no-op by default; **no** env/settings
arming switch. Known points: `inventory_write`, `manifest_publish`,
`known_query`, `embeddings`, `cleanup`. Concurrency is lock-path (2.6e), not a
named inject.

---

## Контракт 2.5b (job↔index bind) — COMPLETE

At `6dbabef`: migration `022_ingestion_job_index_bind`; columns
`index_active_collection`, `index_previous_collection`,
`index_manifest_generation`; public `index_publication_bind`.

---

## Контракт 2.6g (worker outage/recovery) — COMPLETE (latest impl)

At `f347feb`:

- `tasks/ingest_task.py`: `_require_live_lease` probes ownership via
  `heartbeat.tick_once()` at `pre_load` / `pre_index` / `pre_complete`
- `tests/test_worker_outage_fail_closed.py` proves:
  - reaper → late complete/fail CAS fail-closed (no `index_*` bind)
  - reaped terminal cannot be reclaimed
  - reaper after claim → no load/build/publish
  - ownership lost after load → no publish (pre_index)
  - healthy path still completes + binds publication
- Complements existing `tests/test_ingestion_liveness.py` reaper matrix

**Boundary:** local worker/reaper/lease only. Live multi-service recovery is
opt-in residual of plan §2 (not a free follow-on).

**Verification:** 14 scoped (+ adjacent) passed; 55 full liveness passed;
Ruff clean on scoped paths.

### Reference commands (2.6g)

```powershell
python -m pytest tests/test_worker_outage_fail_closed.py tests/test_ingestion_liveness.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step2-6g-<unique>
python -m ruff check tasks/ingest_task.py tests/test_worker_outage_fail_closed.py
```

---

## Что остаётся открытым (после 2.6g / Update-72)

- plan §2 **live** multi-service drills (PG/Redis/Celery/Chroma + migrations
  **019–022**) — **opt-in only**
- real job-object / legacy-previous **FS deletion** (needs product opt-in)
- age/budget thresholds
- orphan cleanup **mutations**
- job-object retention **execute** HTTP
- full suite, release gates, project/production readiness
- plan **§3+** not started

**Next routing (choose one):**
1. Opt-in live §2 multi-service drills
2. Default without live opt-in: begin plan **§3** as a new named slice

**Superseded next-work text:** any handoff still saying next is 2.6e, 2.6f,
or **2.6g** is **stale**.

---

## Windows / tooling notes

- Unique ignored basetemp: `--basetemp=.tmp/pytest-<slice>`
- Full `requirements-dev.lock` may hit Linux-only wheel issues — do not
  blind-retry install without portability task
- One atomic slice per user turn; stop after commit + optional docs
- Avoid concurrent full-ingest threads that load real embedding models in tests
  (prefer claim-level races or fully stubbed `build_vector_store_*`)

---

## Do not

- Re-select **2.1–2.6g**
- Treat failed job-objects as deletable orphans
- Invent auto-delete / age-budget without opt-in
- Push / deploy / live services without explicit opt-in
- Grep old `✅ START HERE` for work selection

# Session handoff

**Обновлено:** 2026-08-03 (Update-47 transparent next-session handoff;
docs-only; latest implementation `ac4b317`; committed docs baseline inspected
`deb542f`; next named slice **2.4a** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(**только верхний блок Update-47** — routing authority; older blocks including
literal `✅ START HERE` headings are archival). Evidence 2.3i — ниже и
Update-46; 2.3h — Update-45; 2.3g — Update-43; детали 2.3f/2.3e/2.3d/2.3c/
2.3b/2.3a — Update-42/Update-41/Update-40/Update-39/Update-37/Update-36.
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**. Детали и ledger — в секциях ниже; не
дублируй длинную историю в новых edits.

| Факт | Значение |
|------|----------|
| Latest implementation | `ac4b317` (`feat(api): expose guarded index retention`) — 2.3i |
| Committed docs baseline inspected | `deb542f` (`docs: record guarded index retention API`) |
| Future Update-47 docs commit | **unknown inside its own content**; next session: `git log -5 --oneline` |
| Branch advisory | `master...origin/master [ahead 78]` — **refresh mandatory** |
| Active writer | **none** |
| Unfinished WIP in next targets | **none known** |
| Locally complete (documented scopes) | **2.1–2.3i** |
| Not complete / not claimed | full plan step 2; full suite; live drills; immutable upload lifecycle; release/production readiness |
| Next allowed candidate | **2.4a only** (not started; not complete) |
| Gates | no push / deploy / live services / destructive Git / production claims |

**Known verification caveats (2.3i):** first Grok run
`rag-step2-3i-20260803-a1` cancelled before edits (denied multi-line Pydantic
`python -c` probe; target hashes unchanged); cause-specific retry
`rag-step2-3i-20260803-a2` completed; direct full-file Mypy still has known
unchanged `dict-item`; one Starlette deprecation warning; **no** full/live
suite in 2.3i or this docs-only Update-47.

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
2.4a WIP на момент этого handoff.

1. **Cycle-guard preflight** on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline` as **separate** commands; **actual Git wins** over
   embedded hashes/counts (including the future Update-47 docs commit SHA).
3. Read **only** top **Update-47** in `AGENT_STATE.md` + this
   **Нулевая неоднозначность** capsule first; treat older Update blocks as
   archive. Do **not** reselect 2.1–2.3i.
4. Verify intended **2.4a** candidate targets are clean; re-check protected
   hashes/state still match (see §2.4a ownership baselines + protected dirty
   list). Do **not** reopen completed retention operator surfaces
   (`api/routers/admin_ops.py` retention/rollback, `vectordb/manager.py`
   retention runtime) unless investigation proves a required conflict — then
   **stop and re-scope**.
5. Use **Grok** via the local verified route; announce counters
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`. Execute **at most
   2.4a**.
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
2. Далее: верхний блок `AGENT_STATE.md` (**Update-47**) и эта капсула.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-47 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3i.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `ac4b317`
(`feat(api): expose guarded index retention`). Committed docs baseline
inspected before Update-47: `deb542f` (`docs: record guarded index retention
API`). Do **not** embed a guessed future docs commit hash; next session reads
actual `git log`. Branch was observed as `master...origin/master [ahead 78]`
at inspection — ahead counts/timestamps are **advisory only**. Push/deploy not
authorized.

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
| **2.3i** | retention API / admin audit | `ac4b317` | Update-46 + this handoff |
| **2.4a** | immutable/versioned original uploads (candidate) | — | **not started** |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g, 2.3h, 2.3i**
локально complete и verified. Локальный operator surface для retention
preview + guarded execution и validated rollback **present**. Полный plan
step 2, immutable/versioned original upload lifecycle, fault injection, live
drills, project и release — **не** complete. **2.3i must never be selected
again.** Next safe named slice is **2.4a only**.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection, complete plan step 2,
project/release readiness. Local retention preview + guarded execution +
validated rollback operator surface is present after 2.3i.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3i (latest)

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
- Этот docs-only refresh **не** перезапускал project tests.

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

**Не начато (вне 2.4a):**

- broader fault injection, live PostgreSQL/Redis/Celery/Chroma drills
  (explicit opt-in only — do **not** select as default next slice),
  release gates, project completion.

**Next candidate (not started):** immutable/versioned original uploads tied
to job/index version without losing the previous working version — **2.4a**.

**Superseded / do not re-select:** 2.1–2.3i are complete. Historical
next-work text that still names **2.3i** (or earlier) as the next candidate
is stale. Historical headings containing `✅ START HERE` are archival.

### Следующий named slice: **2.4a only** (не начат)

Smallest test-first local contract toward immutable/versioned original
uploads tied to job/index version without losing the previous working
version. **Not** completed work. **Do not re-select 2.3i.** No active writer
and no unfinished 2.4a WIP at this handoff. Ownership evidence below was
gathered **read-only** in Update-47; **no 2.4a implementation** occurred.

## Exact contract for next slice 2.4a (evidence-based ownership)

**Status:** not started. Implementation candidate with **read-only ownership
resolved below**. Do **not** mark complete or started from docs.

### Plan source (direction only)

Active untracked plan
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
§2 (unchecked item): make original uploads immutable/versioned and bind their
lifecycle to job/index version without losing the previous working version.
Plan does **not** name files/APIs; ownership comes from repository evidence.

### Current owners (fact / evidence)

| Surface | Module / symbols | Focused tests |
|---------|------------------|---------------|
| HTTP upload write path | `api/routers/upload.py` — `_tenant_upload_directory`, `upload_document`, `file_path = upload_dir / safe_name`, `file_path.write_bytes` | `tests/test_upload_security.py`, `tests/test_upload_idempotency.py`, `tests/test_ingestion_job_contract.py` |
| Durable job identity | `ingestion/jobs.py` — `create_or_reuse_ingestion_job`, `project_relative_source_path`, `compute_payload_fingerprint` | `tests/test_ingestion_job_contract.py`, `tests/test_upload_idempotency.py` |
| Job ORM | `db/models.py` — `IngestionJob` (`filename`, `source_path`, status, idempotency hash/fingerprint, `source_ready_at`; **no** index-version / collection fields) | same job-contract tests |
| Async worker | `tasks/ingest_task.py` — `ingest_document(file_path, job_id, tenant_id)`; loads **parent directory** via `DocumentLoader.load_documents(str(path.parent))`; completion `result` has docs_count only (**no** index generation/collection) | `tests/test_ingest_task.py` |
| Corpus load / reindex | `ingestion/loader.py`; `scripts/reindex.py` — flat tenant upload dir, `recursive=False` | `tests/test_loader.py`, reindex-adjacent gates |

### Durable / versioned today vs overwrite gaps (fact)

**Already durable / versioned at other layers (not 2.4a deliverable):**

- Durable `IngestionJob` rows with tenant-scoped optional Idempotency-Key
  replay, payload fingerprint conflict (409), reserved Celery task id,
  source-ready gate, lease/liveness.
- Index lifecycle 2.1–2.3i: versioned collections, inventory, manifest,
  retention preview + guarded execution, validated rollback.

**Upload originals still overwrite / lack job↔index-version link (gap):**

- Explicit comment and path in `upload.py`: *“Keep tenant corpus directory +
  canonical safe_name (no per-job subdirs).”* Path is
  `data/uploads[/<physical_tenant>]/<safe_name>`.
- Creator path calls `file_path.write_bytes(content_bytes)` onto that
  canonical name — same `safe_name` **overwrites** the previous bytes.
- `IngestionJob.source_path` stores project-relative path to that same
  canonical location; multiple jobs for the same filename can point at one
  mutable file.
- Worker/reindex load the **flat tenant directory**, not a per-job immutable
  object tree.
- Job `result` / model columns do **not** record published index generation
  or collection name — **no durable job↔index-version link** for originals.

**Inference (not claimed implemented):** smallest safe 2.4a should stop
overwriting the prior working original while keeping rebuild/reindex able to
see a stable “current” corpus view; full object-store + cleanup policy is
larger than one slice.

### Smallest safe test-first 2.4a contract (candidate)

Advance **immutable/versioned originals** without losing the previous working
version:

1. **Store each new successful upload under a job-scoped immutable path**
   (e.g. under tenant upload root, keyed by `job_id` + safe filename), write
   once, never rewrite prior job objects.
2. **Persist that immutable path on `IngestionJob.source_path`** (already the
   durable pointer field) so job identity and bytes stay linked.
3. **Preserve previous working version:** either keep the prior canonical
   corpus file until a new version is source-ready, or maintain an explicit
   current pointer/copy that is updated only after the new object is durable
   — never delete/overwrite the only remaining prior bytes in the same step
   as writing the new version without a remaining recoverable prior object.
4. **Do not claim full index-version binding in 2.4a unless the chosen edit
   surface already has a single local hook** (today job completion does not
   write generation/collection). Prefer proving immutable original + job
   path linkage first; defer broader inventory/manifest coupling if it forces
   multi-subsystem expansion.
5. **Keep idempotent replay behavior:** replay must not rewrite a different
   payload onto an existing immutable object; existing fingerprint conflict
   rules remain.

### Initial candidate edit/test paths (evidence-proven)

**Primary edit candidates (only if 2.4a proceeds):**

- `api/routers/upload.py` — path construction + write semantics
- `ingestion/jobs.py` — only if helper(s) for versioned relative paths need a
  shared pure function (keep DB transitions out of scope unless required)
- `tasks/ingest_task.py` — only if worker must open the job’s immutable file
  (or its parent) instead of assuming flat `safe_name` under tenant dir
- `db/models.py` / Alembic — **only if** a new column is proven necessary;
  prefer reusing `source_path` first

**Primary test candidates:**

- `tests/test_upload_idempotency.py` / `tests/test_ingestion_job_contract.py`
  — new acceptance for non-overwrite + job `source_path` immutability
- `tests/test_upload_security.py` — path safety still holds
- `tests/test_ingest_task.py` — worker still resolves the job file

**Likely follow-on touch (stop/re-scope if required mid-slice):**
`scripts/reindex.py` and any loader assumption that the tenant corpus is only
flat non-recursive files. If reindex must understand versioned originals in
the same slice and scope explodes, **stop and re-scope** rather than silent
expansion.

**Out of initial 2.4a edit set unless conflict proven:** completed retention
operator surface (`api/routers/admin_ops.py`, `vectordb/manager.py` retention
runtime, chroma/index retention domain/adapters), settings/policy rewrites,
UI, live services.

### Baseline SHA-256 (Update-47 inspection; re-check before edit)

| Path | SHA-256 |
|------|---------|
| `api/routers/upload.py` | `60AE2DCBE9E492AD4EEF30A71AE08E67DC937DC80410B2D01167B4AD148DA19A` |
| `ingestion/jobs.py` | `FFBE1CC08CE6129184DC4156F802B3B634974C1CE0C445201791BA0C47147254` |
| `tasks/ingest_task.py` | `8F1195CC5781E61EC2CB5D3F6B8857C11C1579C774806B2EFCBD79B483EC277C` |
| `db/models.py` | `6C68A83C43336A31D73624006345849BE8E9EBC0F67FD39D19A254223B218AE0` |
| `ingestion/loader.py` | `1E13472F003E327AA418679007FDC810B0A2023844238C5B852F30415A00CDA9` |
| `tests/test_ingestion_job_contract.py` | `87FE0464AAFAEB773DBE03614541C1500540AAB3C4FFDEDB58A563666E6144FE` |
| `tests/test_upload_idempotency.py` | `E7595A6B2111B17773F96B8E4B9C2617D4F514FF0FAC59953387C7EC401E98BB` |
| `tests/test_upload_security.py` | `7EFC31CF2D4B9AFF878D4EC80A1627AE8F998AB632D694C40E2BAED851666E19` |
| `tests/test_ingest_task.py` | `23A58809D91383073CFAFC7DEC98B8AEAB4DEAD375FDC450D3B3C0B124A883CA` |
| `scripts/reindex.py` | `88758766FB18A0628D3153ABC8C79837AD8444B6AB9D56DB10AECBC1C574D209` |
| Protected 2.3i API | `api/routers/admin_ops.py` = `95370181C6649E0A55C8C786E78226610CC91BFD2F28FD5B3ED66EC32F4BA016` |
| Protected 2.3i tests | `tests/test_admin_index_operator.py` = `3059CE75397E0DB2E69937AF68C92234DFFB2FAB1B46EBB5F28D7D595AAEED45` |
| Protected 2.3h runtime | `vectordb/manager.py` = `C5542E861E86FD9B50081668EDF2ECDC02D0CFF240F724B99F3FE958F2B79EC7` |
| Protected 2.3h tests | `tests/test_index_runtime_switch.py` = `D14383CEE143768A5A4F8A039F573267E26FCE7794AA78351C775975C01FB8E0` |
| Active plan (untracked) | `rag-remediation-plan-2026-08-03.md` = `CF0C6FD19DB1EFAF4735A976DA369A0CDFE67C83139072BE4A078A0715615973` |

### Precise red/green verification (unique basetemp)

After 2.4a code exists (not run in Update-47):

```powershell
python -m pytest tests/test_upload_idempotency.py tests/test_ingestion_job_contract.py tests/test_upload_security.py tests/test_ingest_task.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4a-<unique>
python -m ruff check api/routers/upload.py ingestion/jobs.py tasks/ingest_task.py tests/test_upload_idempotency.py tests/test_ingestion_job_contract.py tests/test_upload_security.py tests/test_ingest_task.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy api/routers/upload.py ingestion/jobs.py tasks/ingest_task.py --no-incremental --show-error-codes
git diff --check -- api/routers/upload.py ingestion/jobs.py tasks/ingest_task.py tests/test_upload_idempotency.py tests/test_ingestion_job_contract.py tests/test_upload_security.py tests/test_ingest_task.py
```

Narrow the pytest selection further if the slice touches fewer files. On this
Windows host, unique ignored basetemp is mandatory. Do **not** run full suite
or live services as the default gate.

### Explicit non-goals (2.4a)

- Re-opening retention preview/execution/rollback operator surfaces
- Settings/policy rewrite, UI, Helm/PVC/object-storage migration
- Full fault-injection matrix; concurrent multi-tenant load drills
- Live PostgreSQL/Redis/Celery/Chroma; push; deploy; production readiness
- Claiming full plan step 2 or full immutable lifecycle “done” after one slice

### Unknowns (honest)

- Exact on-disk layout name (`jobs/<job_id>/…` vs content-addressed blob dir)
  is a design choice inside the contract above — pick the smallest that keeps
  prior bytes recoverable and tests clear.
- Whether reindex must change in the **same** slice depends on whether the
  chosen layout breaks flat `load_documents(tenant_dir)`; confirm with a red
  test before expanding.
- Whether a DB migration is required is **unknown until** path-only reuse of
  `source_path` is proven insufficient.
- Binding job rows to published index generation/collection is **not yet
  present**; treating it as mandatory in 2.4a may force stop/re-scope.

### Stop / re-scope conditions

- Protected retention hashes change without an explicit conflict plan
- Target files become unexpectedly dirty / foreign WIP appears
- Scope requires multi-subsystem expansion (manifest + retention + upload +
  reindex + migration) in one turn
- Second independent verification fails after one allowed narrow correction
- Any push/deploy/live/destructive Git pressure without user authorization

This docs-only turn did **not** run project tests and did **not** start 2.4a.

## Definition of done / stop conditions

- **2.4a is done only after** Grok tests-first evidence for the contract
  above, one independent proportional gate, protected hashes, scoped
  diff-check, and local explicit-path commit.
- **Do not re-select 2.3i**; retention API/admin audit is already complete at
  `ac4b317`. **Do not re-select 2.1–2.3h.**
- **No** full-suite / live / deploy / push / production-readiness claims.
- **Stop/yield after 2.4a** because one user turn equals one slice.
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

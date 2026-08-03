# Session handoff

**Обновлено:** 2026-08-03 (Update-46 plan 2.3i complete @ `ac4b317`;
previous docs HEAD `e348929`; next named slice **2.4a** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок **Update-46**; evidence 2.3i — Update-46; 2.3h — Update-45;
2.3g — Update-43; детали 2.3f/2.3e/2.3d/2.3c/2.3b/2.3a — Update-42/Update-41/
Update-40/Update-39/Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Быстрый старт следующей сессии

Точный checklist. **Нет** active writer и **нет** unfinished 2.4a WIP на
момент этого handoff.

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline`; **actual Git wins** over embedded hashes/counts.
3. Read Update-46 in `AGENT_STATE.md` and this handoff; do **not** reselect
   2.1–2.3i.
4. Investigate intended **2.4a** ownership before naming exact files/APIs
   (immutable/versioned original uploads tied to job/index version without
   losing the previous working version); preserve all listed dirty/untracked
   user state. Do **not** reopen completed retention operator surfaces
   (`api/routers/admin_ops.py` retention/rollback, `vectordb/manager.py`
   retention runtime) unless investigation proves a required conflict — then
   stop and re-scope.
5. Use **Grok** via the local verified route for the implementation; announce
   counters `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Execute **only 2.4a**, tests-first, independent verification, explicit-path
   staging, local commit, optional scoped handoff refresh, then yield.

Push / deploy / live services — **not authorized**. One user turn = one named
atomic slice. Live PostgreSQL/Redis/Celery/Chroma drills require explicit
opt-in and must **not** be selected as the default next slice.

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` (**Update-46**) и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-46 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3i.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `ac4b317`
(`feat(api): expose guarded index retention`). Previous docs HEAD at this
handoff inspection: `e348929` (`docs: record guarded runtime retention`). Do
**not** embed a guessed future docs commit hash; next session reads actual
`git log`. Branch was observed as `master...origin/master [ahead 77]` at
inspection — ahead counts/timestamps are **advisory only**; refresh Git next
session. Push/deploy not authorized.

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
| **2.3i** | retention API / admin audit | `ac4b317` | this handoff / Update-46 |
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

- immutable/versioned original uploads tied to job/index version without
  losing the previous working version (**2.4a**, next candidate, not
  authorized until the next explicit one-slice turn);
- broader fault injection, live PostgreSQL/Redis/Celery/Chroma drills
  (explicit opt-in only — do **not** select as default next slice),
  release gates, project completion.

**Superseded / do not re-select:** 2.1–2.3i are complete. Historical
next-work text that still names **2.3i** as the next candidate is stale.

### Следующий named slice: **2.4a only** (не начат)

Smallest test-first local contract toward immutable/versioned original
uploads tied to job/index version without losing the previous working
version. **Not** completed work. **Do not re-select 2.3i.** No active writer
and no unfinished 2.4a WIP at this handoff.

## Exact contract for next slice 2.4a

**Status:** investigation/implementation candidate only — do **not** mark
complete from docs. Exact files, APIs, storage layout, and acceptance tests
must be confirmed against existing upload/job/index ownership during
investigation; do **not** invent completed work or invent unsupported route
details before investigation.

**Derived safe direction (from active remediation plan + repository
handoff):**

- make original uploads immutable/versioned and bind their lifecycle to
  job/index version;
- preserve the previous working version rather than overwriting or losing it;
- keep the slice local, tests-first, and as small as possible;
- do **not** select live PostgreSQL/Redis/Celery/Chroma drills without
  explicit opt-in;
- do **not** reopen completed retention operator surfaces unless investigation
  proves a required conflict — then stop and re-scope.

**Initial likely edit scope:** unknown until ownership investigation. Do
**not** hard-code file paths here; inspect existing upload/job/index modules
before coding.

**Likely protected unless proven conflict:**

- completed retention operator surface (`api/routers/admin_ops.py` retention/
  rollback paths, `vectordb/manager.py` retention runtime, chroma/index
  retention domain/adapters)
- unrelated admin routes/helpers outside the chosen 2.4a surface
- settings/policy rewrites not required by the smallest local contract

If investigation proves a required conflict on a protected path, **stop and
re-scope** rather than silently expanding. Next session must re-check hashes
against the working tree; do not trust stale baseline tables from earlier
slices as permanent truth.

### Required 2.4a test-first evidence (directional)

Add focused acceptance tests around the chosen local contract after
investigation finalizes ownership:

1. versioned/immutable original retention semantics without losing the
   previous working version;
2. linkage to job/index version boundaries already present in the repo;
3. failure/idempotency behavior appropriate to the chosen ownership surface;
4. no accidental re-open of completed retention API/runtime contracts;
5. no live-service drills, deploy, push, or production-readiness claims.

**Recommended focused verification after new code** (unique basetemp
required; exact paths finalized during investigation):

```powershell
python -m pytest <focused-2.4a-tests> -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-4a-<unique>
python -m ruff check <focused-2.4a-paths>
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy <focused-2.4a-paths> --no-incremental --show-error-codes
git diff --check -- <focused-2.4a-paths>
```

This docs-only turn did **not** run project tests.

## Definition of done / stop conditions

- **2.4a is done only after** ownership investigation, Grok tests-first
  evidence, one independent proportional gate, protected hashes, scoped
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

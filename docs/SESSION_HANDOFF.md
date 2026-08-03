# Session handoff

**Обновлено:** 2026-08-03 (Update-45 plan 2.3h complete @ `bd01f23`;
previous docs HEAD `90fa056`; next named slice **2.3i** not started)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок **Update-45**; evidence 2.3h — Update-45; 2.3g — Update-43;
детали 2.3f/2.3e/2.3d/2.3c/2.3b/2.3a — Update-42/Update-41/Update-40/
Update-39/Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Быстрый старт следующей сессии

Точный checklist. **Нет** active writer и **нет** unfinished 2.3i WIP на
момент этого handoff.

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline`; **actual Git wins** over embedded hashes/counts.
3. Read Update-45 in `AGENT_STATE.md` and this handoff; do **not** reselect
   2.1–2.3h.
4. Confirm intended 2.3i targets (likely `api/routers/admin_ops.py` plus
   focused admin API tests) are clean before edits; preserve all listed
   dirty/untracked user state. Do **not** reopen completed runtime manager
   work in `vectordb/manager.py` unless investigation proves a required
   conflict — then stop and re-scope.
5. Use **Grok** via the local verified route for the implementation; announce
   counters `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Execute **only 2.3i**, tests-first, independent verification, explicit-path
   staging, local commit, optional scoped handoff refresh, then yield.

Push / deploy / live services — **not authorized**. One user turn = one named
atomic slice.

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` (**Update-45**) и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-45 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3h.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation is `bd01f23`
(`feat(index): expose guarded runtime retention`). Previous docs HEAD at this
handoff inspection: `90fa056` (`docs: clarify next-session retention
handoff`). Do **not** embed a guessed future docs commit hash; next session
reads actual `git log`. Branch was observed as
`master...origin/master [ahead 75]` at inspection — ahead counts/timestamps
are **advisory only**; refresh Git next session. Push/deploy not authorized.

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
| **2.3h** | runtime manager retention action (guarded) | `bd01f23` | this handoff / Update-45 |
| **2.3i** | retention API / admin audit (candidate) | — | **not started** |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g, 2.3h** локально
complete и verified. Полный plan step 2, operator surface, project и release
— **не** complete: retention HTTP/API/admin audit (2.3i) and further wiring
still absent. **2.3h must never be selected again.** Next safe named slice is
**2.3i only**.

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

**Boundary:** runtime-only. **Нет** HTTP/API/admin audit, settings/policy
change, UI, live Chroma/PostgreSQL/Redis, deploy, or push. Do **not** claim
full operator surface, plan step 2, project, release, production readiness,
live drills, or retention API complete.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection, full retention API,
complete operator surface.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3h (latest)

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
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал project tests.

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

### Reference commands (2.3h) — только при new code/failure

```powershell
python -m pytest tests/test_index_runtime_switch.py tests/test_chroma_retention.py -q -k "retention or guarded" -p no:cacheprovider --basetemp=.tmp/pytest-step2-3h-<unique>
python -m ruff check vectordb/manager.py tests/test_index_runtime_switch.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/manager.py --no-incremental --show-error-codes
git diff --check -- vectordb/manager.py tests/test_index_runtime_switch.py
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3i):**

- HTTP/API/admin audit for retention execution (**2.3i**, next candidate,
  not authorized until the next explicit one-slice turn);
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3i only** (не начат)

Retention API / admin-audit candidate over the already-landed runtime guarded
retention action. **Not** completed work. **Do not re-select 2.3h.** No
active writer and no unfinished 2.3i WIP at this handoff.

## Exact contract for next slice 2.3i

**Status:** investigation/implementation candidate only — do **not** mark
complete from docs. Exact route/body/audit names and status mapping must be
confirmed against existing admin operator patterns during investigation; do
**not** pretend the API contract is already implemented.

**Derived safe direction (from active remediation plan + landed runtime
surface + prior admin slices 2.3b/2.3e):**

- expose a tenant-scoped admin retention **execution** surface that calls the
  already-landed runtime entrypoint `execute_vector_store_retention`;
- keep the explicit idempotent command key
  (`expected_generation` + exact `expected_candidates`) at the API boundary;
- derive tenant only from existing auth/context/default conventions used by
  retention-preview / rollback admin endpoints; do not trust body tenant
  overrides if that is the established pattern;
- map typed runtime/operator failures to safe HTTP details without leaking
  store/chunk internals;
- emit exactly one tenant-scoped admin audit event for success and for mapped
  semantic failures, following the rollback-audit style unless investigation
  proves a narrower existing retention audit helper;
- use `asyncio.to_thread` (or the established admin async boundary) so the
  manager path remains sync;
- do **not** re-implement retention policy, reopen adapter/domain locks, load
  embeddings, mutate caches, open Chroma from the router, change settings, or
  alter automatic post-publish retention.

**Initial likely edit scope (confirm before coding):**

- `api/routers/admin_ops.py`
- focused admin API tests (existing retention-preview / rollback test modules
  are the nearest patterns; exact test path chosen during investigation)

**Likely protected unless proven conflict:**

- `vectordb/manager.py` (2.3h complete; reopen only if a true boundary conflict
  is proven, then stop and re-scope)
- `vectordb/chroma_retention.py`
- `vectordb/index_operator.py`
- `vectordb/index_retention.py`
- `config/settings.py`
- unrelated admin routes/helpers outside the retention execution surface

If investigation proves a required conflict on a protected path, **stop and
re-scope** rather than silently expanding. Next session must re-check hashes
against the working tree; do not trust stale baseline tables from earlier
slices as permanent truth.

### Required 2.3i test-first evidence (directional)

Add focused acceptance tests around the chosen admin surface:

1. auth/admin-role gate and tenant-from-context only;
2. strict request body for expected generation + exact candidates; unknown
   keys / coerced types rejected before runtime/audit where that is the
   established pattern;
3. happy path calls only `execute_vector_store_retention` through the
   established async boundary and returns a safe response without store/chunk
   leakage;
4. mapped validation/conflict/unavailable/corrupt/lock/backend failures return
   safe details and audit once; auth/body-schema/unrelated failures skip
   runtime/audit as applicable;
5. no settings/policy rewrite, no direct Chroma/manifest/inventory mutation in
   the router, no change to automatic post-publish retention.

**Recommended focused verification after new code** (unique basetemp
required; exact paths finalized during investigation):

```powershell
python -m pytest <focused-admin-retention-tests> -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3i-<unique>
python -m ruff check api/routers/admin_ops.py <focused-admin-retention-tests>
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy api/routers/admin_ops.py --no-incremental --show-error-codes
git diff --check -- api/routers/admin_ops.py <focused-admin-retention-tests>
```

If direct full-file Mypy reveals an existing unrelated error in
`admin_ops.py`, document/narrow it honestly (historical `dict-item` caveat
around unchanged logic remains known); never claim an unconditional clean
file without evidence. This docs-only turn did **not** run project tests.

## Definition of done / stop conditions

- **2.3i is done only after** Grok tests-first evidence, one independent
  proportional gate, protected hashes, scoped diff-check, and local
  explicit-path commit.
- **Do not re-select 2.3h**; runtime manager retention is already complete at
  `bd01f23`.
- **No** full-suite / live / deploy / push / production-readiness claims.
- **Stop/yield after 2.3i** because one user turn equals one slice.
- **Stop and report** if a target file becomes unexpectedly dirty, a second
  verification fails, or scope needs expansion.

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

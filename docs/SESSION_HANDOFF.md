# Session handoff

**Обновлено:** 2026-08-03 (Update-44 transparent handoff; no new slice;
latest implementation still `f966fac`; pre-refresh docs HEAD `1f40a57`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок **Update-44**; evidence 2.3g — Update-43; детали
2.3f/2.3e/2.3d/2.3c/2.3b/2.3a — Update-42/Update-41/Update-40/Update-39/
Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Быстрый старт следующей сессии

Точный checklist. **Нет** active writer и **нет** unfinished 2.3h WIP на
момент этого handoff.

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`; run fresh `git status --short --branch` and
   `git log -5 --oneline`; **actual Git wins** over embedded hashes/counts.
3. Read Update-44 in `AGENT_STATE.md` and this handoff; do **not** reselect
   2.1–2.3g.
4. Confirm `vectordb/manager.py` and `tests/test_index_runtime_switch.py` are
   still clean; preserve all listed dirty/untracked user state.
5. Use **Grok** via the local verified route for the implementation; announce
   counters `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Execute **only 2.3h**, tests-first, independent verification, explicit-path
   staging, local commit, optional scoped handoff refresh, then yield.

Push / deploy / live services — **not authorized**. One user turn = one named
atomic slice.

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` (**Update-44**) и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-44 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3g.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

**Authoritative implementation state:** latest implementation remains
`f966fac` (`feat(index): bridge guarded Chroma retention`). Pre-refresh docs
HEAD at this handoff inspection: `1f40a57` (`docs: record guarded Chroma
retention bridge`). Do **not** embed a guessed future docs commit hash; next
session reads actual `git log`. Branch was observed as
`master...origin/master [ahead 73]` at inspection — ahead counts/timestamps
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
| **2.3g** | guarded Chroma retention adapter bridge | `f966fac` | `1f40a57` (pre-refresh docs HEAD at Update-44) |
| **2.3h** | runtime manager retention action (guarded) | — | **not started** |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g** локально complete
и verified. Полный plan step 2, operator surface, project и release — **не**
complete: manager/runtime retention action (2.3h) and further retention
wiring still absent. **2.3g must never be selected again.** Next safe named
slice is **2.3h only**.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection, full retention API,
complete operator surface.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3g (latest)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; tests-first red: `7` guarded tests failed because
  bridge/operator import was absent; focused final: `66 passed`; Ruff and
  scoped diff-check clean.
- Codex independent: adapter/runtime-retention compatibility gate:
  `13 passed, 23 deselected`, one known Starlette warning; scoped Ruff clean;
  Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4: no issues in
  `vectordb/chroma_retention.py`; scoped diff-check clean; protected
  operator/policy/manager/API/runtime-test hashes unchanged before commit.
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал tests.

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

### Reference commands (2.3g) — только при new code/failure

```powershell
python -m pytest tests/test_chroma_retention.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3g-codex-20260803
python -m ruff check vectordb/chroma_retention.py tests/test_chroma_retention.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/chroma_retention.py --no-incremental --show-error-codes
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3h):**

- HTTP/API/admin audit for retention execution (likely later **2.3i**, not
  authorized yet);
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3h only** (не начат)

Runtime-only manager retention action candidate. **Not** completed work.
**Do not re-select 2.3g.** No active writer and no unfinished 2.3h WIP at
this handoff.

## Exact contract for next slice 2.3h

**Status:** investigation/implementation candidate only — do **not** mark
complete from docs.

**Likely public manager entrypoint name:** `execute_vector_store_retention`
(final naming must follow existing manager conventions during
implementation; unresolved naming is **not** already implemented).

**Acceptance contract (concrete, not pretence of done work):**

- require keyword-only `expected_generation` and exact tuple
  `expected_candidates`;
- tenant normalization follows existing manager convention
  (`tenant_id or "default"`);
- call `get_settings()` and derive `vectordb_chroma_dir` plus
  `vectordb_retention_max_versions`; callers must **not** override configured
  deletion policy;
- fail closed for Qdrant using the existing-style typed runtime validation
  boundary (`IndexStagingValidationError` pattern), **before** guarded
  adapter / Chroma work;
- delegate only to `execute_guarded_chroma_retention` with tenant, configured
  budget, expected command key, and configured directory;
- return `IndexRetentionExecutionResult` unchanged;
- do **not** load embeddings, open/list/create collections directly, acquire
  a second tenant lock, read/write manifest/inventory directly, mutate
  caches, add retry/audit/HTTP, or alter automatic post-publish
  `execute_chroma_retention`;
- typed operator/retention/lock/backend failures propagate unchanged;
- exact empty tuple remains a valid guarded no-delete result with no Chroma
  client.

**Initial likely edit scope:** only

- `vectordb/manager.py`
- `tests/test_index_runtime_switch.py`

**Baseline hashes at this handoff (evidence, not permanent truth):**

| Path | Role | SHA256 |
|------|------|--------|
| `vectordb/manager.py` | candidate edit | `B645D365C79CCB36DF7277DF50D87ED1BC41114E3A7478A12F172F9B43F99FCF` |
| `tests/test_index_runtime_switch.py` | candidate edit | `6B552E405B62DACF3BC6CDFBC9E9E8F863465ECD45282DB3734FC21F3EC0C73F` |
| `vectordb/chroma_retention.py` | protected unless proven conflict | `2B9EA72EF284F998642B8BC42B70AAC1CF6A843BC2DAF101139B5444F7C57EE3` |
| `tests/test_chroma_retention.py` | protected unless proven conflict | `2979F29F6DD7A19AE3B9FE8335F8E6FDC0F65239F7BAF0B3DEDABF42D5CF52D5` |
| `vectordb/index_operator.py` | protected unless proven conflict | `EFAEDB85999D30F1C86AE3AE9D7C3F5C07604D76F9E3EC24CC0E7526A59E8035` |
| `vectordb/index_retention.py` | protected unless proven conflict | `215D62D394D2566DCCB2C14B87B6308F99AB9CD8C0DA0E36BFC3BF4E6E1D22AE` |
| `config/settings.py` | protected unless proven conflict | `06A9DAD83665477321AA6CC8958BF703E0AF6C494C6E8997E969E10790751370` |
| `api/routers/admin_ops.py` | protected unless proven conflict | `E22A7C291200DFD5F25FCF53B81BB034F7098C0C2C05862520886C75D52AE88A` |

If investigation proves a required conflict on a protected path, **stop and
re-scope** rather than silently expanding. Next session must re-check hashes
against the working tree; the table is baseline evidence only.

### Required 2.3h test-first evidence

Add focused acceptance tests in `tests/test_index_runtime_switch.py`:

1. exact forwarding of normalized tenant / configured budget / configured
   directory / generation / candidates to the guarded adapter, and unchanged
   result return;
2. no embeddings, cache mutation, direct Chroma, direct manifest/inventory,
   or second lock;
3. Qdrant typed fail-closed before adapter;
4. guarded validation / conflict / corrupt / lock / delete / prune failures
   propagate unchanged;
5. empty tuple result passes through without direct runtime Chroma work;
6. existing automatic rebuild retention path remains on
   `execute_chroma_retention`, not the guarded operator path;
7. source/signature boundary and no production callers until later API slice.

**Recommended focused verification after new code** (unique basetemp
required):

```powershell
python -m pytest tests/test_index_runtime_switch.py tests/test_chroma_retention.py -q -k "retention or guarded" -p no:cacheprovider --basetemp=.tmp/pytest-step2-3h-<unique>
python -m ruff check vectordb/manager.py tests/test_index_runtime_switch.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/manager.py --no-incremental --show-error-codes
git diff --check -- vectordb/manager.py tests/test_index_runtime_switch.py
```

If direct full-file Mypy reveals an existing unrelated error, document/narrow
it honestly; never claim an unconditional clean file without evidence. This
docs-only turn did **not** run project tests.

## Definition of done / stop conditions

- **2.3h is done only after** Grok tests-first evidence, one independent
  proportional gate, protected hashes, scoped diff-check, and local
  explicit-path commit.
- **No API/admin audit in 2.3h**; that remains a later named slice (likely
  **2.3i**, not authorized yet).
- **No** full-suite / live / deploy / push / production-readiness claims.
- **Stop/yield after 2.3h** because one user turn equals one slice.
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

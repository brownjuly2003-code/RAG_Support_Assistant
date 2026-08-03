# Session handoff

**Обновлено:** 2026-08-03 (после plan 2.3g / `f966fac`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок Update-43; детали 2.3f/2.3e/2.3d/2.3c/2.3b/2.3a — Update-42/
Update-41/Update-40/Update-39/Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-43 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3g.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

Baseline pre-refresh HEAD: `f966fac` (`feat(index): bridge guarded Chroma
retention`). Eventual docs commit будет descendant of `f966fac` — next session
берёт actual hash из `git log`, не ожидает embedded self-hash. Ветка локально
ahead of origin; push/deploy не разрешены автоматически.

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
| **2.3g** | guarded Chroma retention adapter bridge | `f966fac` | (docs refresh after this handoff) |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f, 2.3g** локально complete
и verified. Полный plan step 2, operator surface, project и release — **не**
complete: manager/runtime retention action and further retention wiring still
absent. **2.3g must never be selected again.**

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

- manager/runtime public retention action for guarded Chroma execution;
- HTTP/API/admin audit for retention execution;
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3h only** (не начат)

Add a Chroma-only manager/runtime retention action that requires the explicit
expected manifest generation and exact preview candidate tuple, derives the
configured Chroma directory and retention budget through existing
settings/runtime boundaries, and delegates to
`execute_guarded_chroma_retention`, while preserving the automatic
post-publish path.

В **2.3h** остаётся **runtime-only**: no HTTP/API/admin audit, no
settings/policy change, no UI, no live services, deploy, or push. Non-Chroma
behavior must fail through an explicit existing-style runtime validation
boundary rather than silently acting. Treat 2.3h as an
investigation/implementation candidate, **not** completed work. **Do not
re-select 2.3g.**

**Точки входа для исследования** (только investigation; **не** authorization
расширять scope beyond named slice 2.3h):

- manager/runtime retention action surface (existing settings/runtime
  boundaries for Chroma directory and retention budget);
- `vectordb/chroma_retention.py` — `execute_guarded_chroma_retention` and
  preserved automatic post-publish `execute_chroma_retention`;
- `vectordb/index_operator.py` — guarded `execute_index_retention` command;
- focused manager/runtime tests for the above modules.

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

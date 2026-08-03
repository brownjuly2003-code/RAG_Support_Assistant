# Session handoff

**Обновлено:** 2026-08-03 (после plan 2.3f / `f5f3f6e`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок Update-42; детали 2.3e/2.3d/2.3c/2.3b/2.3a — Update-41/
Update-40/Update-39/Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-42 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3f.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

Baseline pre-refresh HEAD: `f5f3f6e` (`feat(index): guard retention
execution`). Eventual docs commit будет descendant of `f5f3f6e` — next session
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
| **2.3f** | unwired guarded retention execution command | `f5f3f6e` | (docs refresh after this handoff) |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e, 2.3f** локально complete и
verified. Полный plan step 2, operator surface, project и release — **не**
complete: Chroma-side adapter bridge and further retention wiring still
absent. **2.3f must never be selected again.**

## Контракт 2.3f (unwired guarded retention execution)

Domain command in `vectordb/index_operator.py` + contracts in
`tests/test_index_operator.py`:

- `execute_index_retention` is an **unwired** domain command
- validates expected generation and exact ordered candidate tuple **before**
  lock; falsey tenant normalizes to `default`
- under one tenant lock: recomputes bounded candidates, reads manifest,
  conflicts on missing/mismatched generation or tuple **before** mutation,
  then calls existing `execute_bounded_retention` with the held token and
  injected idempotent delete callback
- result reports tenant/budget/expected command key and exact deleted tuple
- empty exact tuple still goes through the existing executor
- existing corrupt metadata, lock, delete, and metadata-prune errors
  propagate typed and observable
- partial delete followed by successful prune requires a fresh preview/command
  for the remaining tuple; metadata-prune failure preserves the tuple so an
  exact retry with idempotent deletion remains safe

**Preserved foundations (not re-implemented here):** existing bounded
retention executor, preview primitive, and post-publish automatic Chroma
retention path remain as before; 2.3f only adds the guarded domain command.

**Boundary:** unwired domain command only. **Нет** Chroma adapter/runtime/
manager/HTTP/admin/audit/UI wiring; no new deletion adapter or policy; no live
Chroma/PostgreSQL/Redis; no deploy/push. Do **not** claim full operator
surface, plan step 2, project, release, production readiness, live drills, or
retention API complete.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection, full retention API,
complete operator surface.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3f (latest)

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
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал tests.

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

### Reference commands (2.3f) — только при new code/failure

```powershell
python -m pytest tests/test_index_operator.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3f-codex-20260803
python -m ruff check vectordb/index_operator.py tests/test_index_operator.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/index_operator.py --no-incremental --show-error-codes
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3g):**

- Chroma-side adapter bridge for guarded retention execution;
- manager/runtime public action, HTTP/API/admin audit for retention execution;
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3g only** (не начат)

Add a Chroma-side guarded adapter bridge for the new command, requiring
explicit expected generation/candidates and supplying the existing idempotent
direct-delete behavior, while preserving the existing automatic post-publish
`execute_chroma_retention` contract.

В **2.3g** остаётся **adapter-only**: no manager/runtime public action, no
HTTP/API/admin audit, no settings/policy change, no live services, deploy, or
push. Treat 2.3g as an investigation/implementation candidate, **not**
completed work. **Do not re-select 2.3f.**

**Точки входа для исследования** (только investigation; **не** authorization
расширять scope beyond named slice 2.3g):

- `vectordb/chroma_retention.py` — existing Chroma retention adapter and
  automatic post-publish `execute_chroma_retention` contract;
- `vectordb/index_operator.py` — new guarded `execute_index_retention` command;
- `vectordb/index_retention.py` — retention policy/candidate helpers;
- focused adapter/operator tests for the above modules.

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

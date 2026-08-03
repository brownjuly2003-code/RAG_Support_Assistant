# Session handoff

**Обновлено:** 2026-08-03 (после plan 2.3d / `7b8d14c`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок Update-40; детали 2.3c/2.3b/2.3a — Update-39/Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-40 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3d.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

Baseline pre-refresh HEAD: `7b8d14c` (`feat(index): make runtime rollback
idempotent`). Eventual docs commit будет descendant of `7b8d14c` — next session
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
| **2.3d** | idempotent validated runtime rollback | `7b8d14c` | (docs refresh after this handoff) |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d** локально complete и verified.
Полный plan step 2, operator surface, project и release — **не** complete.

## Контракт 2.3d (idempotent validated runtime rollback)

Runtime surface in `vectordb/manager.py` + operator validator in
`vectordb/index_operator.py`:

- `rollback_vector_store(..., *, expected_generation, target_collection)` —
  keyword-only generation/target; routes through `rollback_index_version`
  instead of calling manifest rollback directly
- optional generic operator `target_validator` runs **exactly once** under the
  already-held tenant lock **only after** durable command classification:
  - first apply: validate before mutation
  - exact retry: validate then return `applied=False`
  - invalid / conflict / missing / corrupt paths: do **not** open the target
- manager opens only the explicit target with
  `create_collection_if_not_exists=False`, restores/dimension/known-query
  validates it under that same lock, then updates cache from
  `IndexRollbackResult.active_collection` and `.manifest_generation` after
  apply or retry
- exact runtime retry preserves manifest bytes/generation/active/previous and
  cannot oscillate; target validation failure preserves manifest and active
  cache

**Preserved 2.3c domain semantics (not re-implemented here):**
`rollback_index_version` still owns first-apply / exact-retry classification,
typed validation/conflict errors, and atomic manifest rollback under one
tenant lock.

**Boundary:** runtime wiring only. **Нет** HTTP/API/admin auth/audit, retention
execution/deletion, settings/migrations, live Chroma/PostgreSQL/Redis/provider,
deploy, push, Qdrant rollback, or production readiness.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3d (latest)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; initial red `18 failed, 18 passed`; final focused gate
  `90 passed` with two pre-existing warnings; Ruff/diff clean.
- Codex independent: `53 passed` with one known FastAPI/Starlette warning;
  scoped Ruff clean; Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4 clean; caller
  search found no production call sites; protected hashes/diff clean. One Grok
  QA follow-up corrected only the stale module word `unwired`; final
  key-contract gate `9 passed`, Ruff/diff clean.
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал tests.

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
- Direct Mypy на весь `admin_ops.py`: pre-existing `dict-item` на **unchanged**
  line **215** (commit `3c1e7b7d`). Narrowed Python 3.11 + mypy 1.19.1 +
  NumPy 2.4.4 с `--disable-error-code=dict-item` — passed. **Никогда** не
  называть весь файл unconditionally Mypy-clean.

### 2.3a (summary)

- Grok: **46** focused passes; Codex: **79**-pass closure.

### Reference commands (2.3d) — только при new code/failure

```powershell
python -m pytest tests/test_index_operator.py tests/test_index_runtime_switch.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3d-codex-20260803
python -m ruff check vectordb/index_operator.py vectordb/manager.py tests/test_index_operator.py tests/test_index_runtime_switch.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/index_operator.py vectordb/manager.py --no-incremental --show-error-codes
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3e):**

- retention execution/deletion operator action;
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3e only** (не начат)

Expose the now-idempotent validated runtime rollback through a tenant-scoped
existing-admin endpoint with explicit expected generation/target, safe typed
error mapping, `asyncio.to_thread`, and tenant-scoped audit outcome.

В **2.3e не** добавлять: retention deletion/execution, live service calls,
deploy, push.

**Точки входа для исследования** (только investigation; **не** authorization
расширять scope beyond named slice 2.3e):

- `api/routers/admin_ops.py` — existing admin operator surface patterns
  (auth, tenant derivation, `asyncio.to_thread`, audit);
- `tests/test_admin_index_operator.py` — endpoint contract patterns from
  retention preview and related admin index tests.

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

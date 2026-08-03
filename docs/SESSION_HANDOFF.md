# Session handoff

**Обновлено:** 2026-08-03 (после plan 2.3e / `457cbf0`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок Update-41; детали 2.3d/2.3c/2.3b/2.3a — Update-40/Update-39/
Update-37/Update-36).
Активный plan source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-41 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3e.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

Baseline pre-refresh HEAD: `457cbf0` (`feat(api): expose idempotent index
rollback`). Eventual docs commit будет descendant of `457cbf0` — next session
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
| **2.3e** | tenant-scoped admin idempotent rollback endpoint | `457cbf0` | (docs refresh after this handoff) |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c, 2.3d, 2.3e** локально complete и verified.
Полный plan step 2, operator surface, project и release — **не** complete:
operator retention execution/deletion still absent.

## Контракт 2.3e (HTTP admin idempotent index rollback)

Admin surface in `api/routers/admin_ops.py` + endpoint contracts in
`tests/test_admin_index_operator.py`:

- `POST /api/admin/index/rollback` requires the existing admin role
- tenant is derived only from JWT/context/default; body must not supply tenant
- strict extra-forbid JSON body requires `expected_generation` and
  `target_collection`; body `tenant_id`/unknown keys and coerced types are
  rejected **422** before runtime/audit; semantic invalid values reach the
  domain contract
- handler calls only `rollback_vector_store` through `asyncio.to_thread` with
  the explicit command key and **no** embeddings
- first apply and exact retry return the same safe `status: active` response
  with expected generation + 1 and explicit target; response does **not** claim
  `applied` or expose store/chunks
- mapped validation/conflict/unavailable/corrupt/target-validation/lock
  failures return safe **400/409/503** details and exactly one tenant-scoped
  `index_rollback` audit; success also audits once
- auth failures, body-schema 422, and unrelated exceptions skip runtime and/or
  audit as applicable (no double audit on mapped paths)

**Preserved 2.3d runtime foundation (not re-implemented here):**
`rollback_vector_store` still requires keyword-only expected generation/target,
routes through `rollback_index_version`, validates the explicit target under
the operator lock, and returns a non-oscillating exact-retry result.

**Boundary:** HTTP admin exposure only. **Нет** retention execution/deletion,
direct Chroma/manifest/operator mutation wiring, settings/migrations, UI, live
services, Qdrant rollback, deploy, push, or production readiness.

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

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3e (latest)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, actual reported
  `grok-4.5-build`; red `26 failed, 14 deselected`; focused final `128 passed`
  with one known Starlette warning; Ruff/diff clean.
- Codex independent: `40 passed` with one known warning; scoped Ruff clean;
  narrowed Python 3.11 / Mypy 1.19.1 / NumPy 2.4.4 passed with only existing
  `dict-item` disabled; protected hashes/route search/diff clean; final
  key-contract gate `19 passed`, Ruff/diff clean.
- Direct Mypy на весь `admin_ops.py`: pre-existing `dict-item` на **unchanged**
  logic at line **223** (commit `3c1e7b7d`, line shifted by inserted rollback
  code). Narrowed Python 3.11 + mypy 1.19.1 + NumPy 2.4.4 с
  `--disable-error-code=dict-item` — passed. **Никогда** не называть весь файл
  unconditionally Mypy-clean.
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал tests.

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

### Reference commands (2.3e) — только при new code/failure

```powershell
python -m pytest tests/test_admin_index_operator.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3e-codex-20260803
python -m ruff check api/routers/admin_ops.py tests/test_admin_index_operator.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy api/routers/admin_ops.py --no-incremental --show-error-codes --disable-error-code=dict-item
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3f):**

- retention execution/deletion operator action (HTTP/API still out of 2.3f);
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3f only** (не начат)

Add an unwired tenant-locked retention execution command contract that requires
an explicit expected manifest generation and exact preview candidate tuple
before invoking the existing bounded retention executor, so changed
state/candidates fail closed and partial delete/prune remains
repeatable/observable.

В **2.3f не** добавлять: HTTP/API, new deletion adapter/policy, live service
calls, deploy, push.

**Точки входа для исследования** (только investigation; **не** authorization
расширять scope beyond named slice 2.3f):

- `vectordb/index_operator.py` — existing operator/command patterns and lock
  semantics;
- `vectordb/chroma_retention.py` — existing bounded retention executor surface;
- `vectordb/index_retention.py` — retention policy/candidate helpers;
- focused tests for the above modules.

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

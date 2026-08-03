# Session handoff

**Обновлено:** 2026-08-03 (после plan 2.3c / `dda4bb2`)

**Назначение:** самодостаточный next-session handoff для coding agent после
compacted context. История срезов — в [`AGENT_STATE.md`](../AGENT_STATE.md)
(верхний блок Update-39; детали 2.3b/2.3a — Update-37/Update-36). Активный plan
source — untracked/protected
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

## Назначение и приоритет источников

1. `git status --short --branch` и `git log -5 --oneline` — авторитетный
   источник текущего filesystem/Git state.
2. Далее: верхний блок `AGENT_STATE.md` и этот handoff.
3. `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26` и их
   dirty working-tree contents — protected user state; могут быть stale. Они
   **не** переопределяют Update-39 и **не** дают права повторять уже
   завершённые срезы 2.1–2.3c.
4. `rag-remediation-plan-2026-08-03.md` — активный plan source
   (untracked/protected). Старый `plan_sol_23_07_26` — protected legacy.
5. Один user turn = максимум один named atomic slice.

Baseline pre-refresh HEAD: `dda4bb2` (`feat(index): add idempotent rollback
command`). Eventual docs commit будет descendant of `dda4bb2` — next session
берёт actual hash из `git log`, не ожидает embedded self-hash. Ветка локально
ahead of origin; push/deploy не разрешены автоматически.

## Карта реализации

| Slice | Что | Implementation | Status docs |
|-------|-----|----------------|-------------|
| **2.1** | publication inventory wiring | `e8da185` | `3cc939b` |
| **2.2** | post-publish bounded retention | `f0cb6ee` | `30a8404` |
| **2.3a** | lock-consistent read-only retention preview primitive | `5bbc329` | `3976366` |
| **2.3b** | tenant-scoped admin retention preview endpoint | `32748d9` | `37987df` |
| **2.3c** | unwired idempotent rollback command contract | `dda4bb2` | (docs refresh after this handoff) |

Срезы **2.1, 2.2, 2.3a, 2.3b, 2.3c** локально complete и verified. Полный plan
step 2, operator surface, project и release — **не** complete.

## Контракт 2.3c (idempotent rollback command)

Public domain surface в `vectordb/index_operator.py`:

- `rollback_index_version(tenant_id, expected_generation, target_collection,
  chroma_directory)`
- frozen `IndexRollbackResult`
- typed `IndexRollbackValidationError` и `IndexRollbackConflict`

**Apply / retry / conflict:**

- first application: current generation and previous target must match;
  holds one tenant lock; calls existing atomic manifest rollback with the
  same lock token;
- exact retry: byte-preserving no-op **only** for generation
  `expected + 1` and active target match — prevents active/previous
  oscillation;
- stale / future / mismatched commands fail closed;
- invalid inputs → typed validation errors;
- absent / no-previous / corrupt-manifest → existing typed manifest errors.

**Boundary (unwired):** manifest command only. **Нет** manager/runtime target
opening/validation, embeddings, cache mutation, HTTP/API, audit, retention
deletion, live services, deploy, push, or production readiness.

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
- Idempotent rollback command (2.3c): unwired domain contract only; manager
  still has legacy `rollback_vector_store` that can oscillate on raw retry
  until 2.3d wires the new command.

**Не утверждать:** Qdrant operator support, live services, production
readiness, immutable uploads, complete fault injection.

## Доказательства верификации (не перезапускать без new code/failure)

### 2.3c (latest)

- Grok: route `local_grok_cli`; CLI-selected model `grok-4.5`, result-reported
  actual model `grok-4.5-build`; initial red `18 failed, 9 passed`; focused
  final `60 passed` after one allowed narrowed correction to a false-positive
  source-boundary assertion; Ruff and scoped diff check clean.
- Codex independent: `27 passed` with the already known FastAPI/Starlette
  TestClient deprecation warning; scoped Ruff clean; Python 3.11 /
  Mypy 1.19.1 / NumPy 2.4.4 clean; protected hashes and diff check clean.
- Real Chroma/PostgreSQL/Redis, full suite, push, deploy, production
  readiness — **не** было и **не** утверждается.
- Этот docs-only refresh **не** перезапускал tests.

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

### Reference commands (2.3c) — только при new code/failure

```powershell
python -m pytest tests/test_index_operator.py -q -p no:cacheprovider --basetemp=.tmp/pytest-step2-3c-codex-20260803
python -m ruff check vectordb/index_operator.py tests/test_index_operator.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy vectordb/index_operator.py --no-incremental --show-error-codes
```

На этом Windows host обязателен unique ignored basetemp
(`--basetemp=.tmp/pytest-<slice>`). Полный `requirements-dev.lock` resolution
blocked unmarked Linux-only `nvidia-cufile` wheel; не retry install без
отдельной portability-задачи.

## Что остаётся открытым / следующий safe slice

**Не начато (вне 2.3d):**

- retention execution/deletion operator action;
- HTTP/API/audit wiring for rollback;
- immutable/versioned originals, broader fault injection, live drills,
  release gates, project completion.

### Следующий named slice: **2.3d only** (не начат)

Wire the already validated Chroma rollback path in `vectordb/manager.py` to
require/pass explicit expected generation and target through the new
idempotent `rollback_index_version` command, preserving
validation-before-mutation and cache-generation behavior.

В **2.3d не** добавлять: HTTP/API, audit, retention deletion, live service
calls, deploy, push.

**Точки входа для исследования** (только investigation; **не** authorization
расширять scope beyond named slice 2.3d):

- `vectordb/manager.py::rollback_vector_store` — existing validated runtime
  rollback that can still oscillate on raw retry until wired;
- `vectordb/index_operator.py::rollback_index_version` — already validated
  idempotent command to call under tenant lock;
- `tests/test_index_runtime_switch.py` и related manager/runtime tests —
  investigation entry points only.

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

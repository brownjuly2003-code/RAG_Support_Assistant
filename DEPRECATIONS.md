# Deprecations & module-layout consolidation

This file tracks legacy module placements and the migration plan to consolidate
the project tree. Created 2026-04-26 as part of the Opus audit follow-up.

## Status legend

- 🔴 **active legacy** — file still imported from production code; cannot be
  removed without an import-rewrite pass + test run.
- 🟡 **shim** — re-exports from canonical location with `DeprecationWarning`.
- 🟢 **canonical** — current home; nothing to do.

## Root-level Python modules

| File | LOC | Status | Canonical | Notes |
|---|---:|---|---|---|
| ~~`graph.py`~~ | — | ✅ removed 2026-04-26 | `agent.graph` | Phase 1 closed. |
| ~~`state.py`~~ | — | ✅ removed 2026-04-26 | `agent.state` | Phase 1 closed. |
| ~~`prompts.py`~~ | — | ✅ removed 2026-04-26 | `agent.prompts` | Phase 1 closed. |
| ~~`manager.py`~~ | — | ✅ removed 2026-04-27 | `vectordb.manager` | Phase 3+4 final cleanup closed by `4c557f3`; root import now raises `ModuleNotFoundError`. |
| ~~`sqlite_trace.py`~~ | — | ✅ removed 2026-04-27 | `tracing.sqlite_trace` | Phase 3+4 final cleanup closed by `4c557f3`; root import now raises `ModuleNotFoundError`. |
| ~~`loader.py`~~ | — | ✅ removed 2026-04-27 | `ingestion.loader` | Phase 3+4 final cleanup closed by `4c557f3`; root import now raises `ModuleNotFoundError`. |
| ~~`chunking.py`~~ | — | ✅ moved 2026-04-27 | `scripts.chunking_eval` | Phase 5 complete. Standalone tuning script moved out of project root. |
| ~~`bitrix.py`~~ | — | ✅ moved 2026-04-27 | `integrations.bitrix` | Phase 2 complete. |
| ~~`mock_inbox.py`~~ | — | ✅ moved 2026-04-27 | `integrations.mock_inbox` | Phase 2 complete. |
| ~~`seed_docs.py`~~ | — | ✅ moved 2026-04-27 | `demo.seed_docs` | Phase 2 complete. |
| `cache.py` | 266 | 🟢 canonical | `cache.py` (root) | Different concern from `cache/redis_cache.py` (in-memory LRU vs Redis). Not a duplicate. |

## Migration plan — do these in order, in dedicated PRs

### Phase 1 — kill the no-op shims ✅ DONE 2026-04-26

Removed `graph.py`, `state.py`, `prompts.py` shims from project root. Also
removed the dead `except ImportError:` fallback in `agent/graph.py:48-80`
which had been re-exporting through the same shims (circular fallback).

### Phase 2 — rename misleading legacy files ✅ DONE 2026-04-27

Move/rename to align with their actual roles. Each move requires updating
import sites:

1. `bitrix.py` → `integrations/bitrix.py`. Create `integrations/__init__.py`.
   Update `mock_inbox.py:54`, `config/settings.py`. ✅ done 2026-04-27.
2. `mock_inbox.py` → `integrations/mock_inbox.py`. Update `agent/graph.py:134`,
   `tests/test_mock_inbox_import.py`, `config/settings.py`. ✅ done 2026-04-27.
3. `seed_docs.py` → `demo/seed_docs.py`. No production imports — only doc updates. ✅ done 2026-04-27.

### Phase 3 — collapse `manager` and `sqlite_trace` ✅ DONE 2026-04-27

These have non-trivial wrappers. Two acceptable end-states:

**Option A (preferred)**: move root content into the package, delete the
wrapper, fold tenant-aware caching / PII redaction into the canonical module.

**Option B**: keep current split, but rename root `manager.py` to
`vectordb/_base_manager.py` so the canonical import is `vectordb.manager`
everywhere. Same idea for `sqlite_trace.py` → `tracing/_base_trace.py`.

2026-04-27 update: `manager.py` and `sqlite_trace.py` used Option B. The base
implementations now live in `vectordb/_base_manager.py` and
`tracing/_base_trace.py`; the temporary root compatibility shims were removed
in `4c557f3`.

### Phase 4 — resolve the `loader` fork ✅ DONE 2026-04-27

Merged the fork into `ingestion.loader`: it now keeps package features
(`.json`/`.csv`, single-file loading, per-page PDF docs) and root-only features
(`DocumentChangeTracker`, `.html`/`.htm` support). Production imports use
`ingestion.loader` directly; the temporary root `loader.py` shim was removed in
`4c557f3`.

### Phase 5 — find a home for `chunking.py` ✅ DONE 2026-04-27

It is a tuning script, not a production module. Moved to
`scripts/chunking_eval.py`; runtime imports now use `vectordb.manager` directly.

## api/app.py monolith split — router extraction complete

`api/app.py` is now 1,884 LOC at `f1e2be0`. Public endpoint groups live under
`api/routers/`, including auth/session management. The app module still owns
FastAPI construction, middleware, lifespan, shared in-memory session state, and
compatibility re-exports used by older tests. Some routers still reach into
`api.app` lazily for `_sessions`, `_session_last_access`, `_db_retry_after`,
and `_pipeline_semaphore` so existing `monkeypatch.setattr(api.app, ...)`
tests continue to work.

### Done sub-routers

- `api/routers/system.py` — `/health/live`, `/health/ready`, `/health`,
  and `/metrics` under the `/api` prefix (Phase 2 PoC + Phase 2a).
- `api/routers/root_pages.py` — root-level `/agent`,
  `/admin/traces/{trace_id}`, and `/metrics`.
- `api/routers/agent.py` — `/agent/tickets`, `/agent/tickets/{id}`,
  `/agent/tickets/{id}/respond`, `/agent/similar` (Phase 2c).
- `api/routers/admin_review.py` — `/admin/review-queue` (list, update, stats)
  (Phase 2e).
- `api/routers/admin_ops.py` — `/admin/circuit-breaker/reset`,
  `/admin/audit`, `/admin/traces/*`, and `/admin/audit-log` (Phase 2d).
- `api/routers/auth_sso.py` — `/auth/sso/providers`, `/auth/sso/{p}/login`,
  `/auth/sso/{p}/callback` (Phase 2j).
- `api/routers/admin_kb.py` — `/admin/curated-dataset/*`,
  `/admin/thresholds/*`, `/admin/improvement-backlog/*`,
  `/admin/recommendations/current`, `/admin/kb-gaps`, `/admin/categories`,
  `/admin/kb-drafts/*`, `/admin/stale-docs/*` (Phase 2f).
- `api/routers/admin_experiments.py` — `/admin/experiments/*`,
  including comparison, deploy/rollback, regression trigger, and assignments
  (Phase 2g).
- `api/routers/admin_evaluations.py` — `/admin/evaluations/*` and
  `/admin/regression-runs/*` (Phase 2h).
- `api/routers/analytics.py` — `/analytics/top-topics`,
  `/analytics/resolution-rate`, `/analytics/cost-summary`, `/analytics/trends`
  (Phase 2i).
- `api/routers/feedback.py` — `/feedback`, `/feedback/stats`, `/escalate`
  (Phase 2b).
- `api/routers/misc.py` — `/admin/providers` and `/channels/email/inbound`
  (Phase 2m). The legacy `/webhook/email` alias is still registered from
  `api.app` against the same handler.
- `api/routers/upload.py` — `/upload` and `/tasks/{task_id}` (Phase 2k).
- `api/routers/conversation.py` — `/ask`, `/chat`, `/ask/stream`, and
  `/chat/stream` (Phase 2l).
- `api/routers/session_auth.py` — `/auth/login`, `/auth/refresh`,
  `/sessions/{id}/history`, `/sessions`, and `DELETE /sessions/{id}` (Step 8
  app-shell cleanup).

Latest sanity: 69 `/api` routes at `f1e2be0` (verified 2026-04-30).

### Lesson learned from the splits — module-import pattern

Tests use `monkeypatch.setattr("db.engine.async_session", ...)`,
`monkeypatch.setattr(api_app, "log_audit", ...)`, and similar `api.app`
helper patches to inject fakes. Direct top-level imports in a sub-router
**break these patches** because the imported name is bound at router-module
load time, before the test patches it.

Pattern that works:

```python
from db import engine as _db_engine

def _async_session():
    return _db_engine.async_session()  # late-bound through the module

async def _log_audit(**kwargs):
    from api import app as _app  # noqa: PLC0415
    return await _app.log_audit(**kwargs)
```

Apply this in every new sub-router that touches DB sessions or audit logs.
For handlers whose tests monkeypatch helpers on `api.app`, use a lazy
`from api import app as _app` inside the handler or a local wrapper. Apply
the same late-bound module pattern in non-router runtime code such as
`evaluation/evaluator_runner.py` when tests replace `db.engine` globals.
For shared rate limiting, import `limiter` from `api.rate_limit`; importing it
from `api.app` creates a circular dependency when a router is imported directly.

### Split checklist

| Phase | Endpoints | Blockers |
|---|---|---|
| ~~2a~~ | ~~`/health` + `/health/ready`~~ | ✅ done 2026-04-27 |
| ~~2b~~ | ~~`/feedback`, `/escalate`~~ | ✅ done 2026-04-27 |
| ~~2c~~ | ~~`/agent/tickets/*` (4 endpoints)~~ | ✅ done 2026-04-26 |
| ~~2d~~ | ~~`/admin/audit`, `/admin/circuit-breaker/reset`, `/admin/traces/*`, `/admin/audit-log` (deletes)~~ | ✅ done 2026-04-27 |
| ~~2e~~ | ~~`/admin/review-queue/*` (3 endpoints)~~ | ✅ done 2026-04-26 |
| ~~2f~~ | ~~`/admin/curated-dataset/*`, `/admin/thresholds/*`, `/admin/improvement-backlog/*`, `/admin/recommendations/*`, `/admin/kb-gaps`, `/admin/kb-drafts/*`, `/admin/categories`, `/admin/stale-docs/*`~~ | ✅ done 2026-04-26 |
| ~~2g~~ | ~~`/admin/experiments/*` (9 endpoints)~~ | ✅ done 2026-04-27 |
| ~~2h~~ | ~~`/admin/regression-runs/*` (2) + `/admin/evaluations/*` (2)~~ | ✅ done 2026-04-27 |
| ~~2i~~ | ~~`/analytics/*` (4)~~ | ✅ done 2026-04-27 |
| ~~2j~~ | ~~`/auth/sso/*` (3)~~ | ✅ done 2026-04-26 |
| ~~2k~~ | ~~`/upload`, `/tasks/{task_id}`~~ | ✅ done 2026-04-27 |
| ~~2l~~ | ~~`/ask`, `/ask/stream`, `/chat`, `/chat/stream`~~ | ✅ done 2026-04-27 |
| ~~2m~~ | ~~`/admin/providers`, `/channels/email/inbound`~~ | ✅ done 2026-04-27 |
| Step 8 | `/auth/login`, `/auth/refresh`, `/sessions/*` | ✅ done 2026-04-28 |

The 2a-2m split plan is complete, and the auth/session surface has also been
extracted. Remaining app-shell work, if desired, is reducing `api/app.py`
further by moving construction/lifespan/shared-state compatibility helpers
behind smaller modules. That is a separate cleanup, not a route ownership gap.

## Type-checking debt

Strict mypy is enforced via `pyproject.toml [[tool.mypy.overrides]]` for:

- `auth.*` — passes clean (4/4 files)
- `db.models` — passes clean
- `db.engine` — passes clean
- `llm.providers.*` — passes clean (promoted к strict 2026-04-27 после фикса
  Mapping для headers и явных kwargs вместо `**dict[str, object]`)
- `config.settings` — passes clean 2026-04-27 (Step 6: removed duplicate
  `tenant_admin_email` field, renamed shadowed `result` local in
  `_load_llm_model_prices`, narrowed `os.getenv("SESSION_SECRET_KEY")` with
  empty default, marked `import yaml` as `type: ignore[import-untyped]`).
- `agent.state`, `agent.prompts`, `agent.prompt_registry`, `agent.tools`,
  `agent.graph` — passes clean 2026-04-30 in focused verification. Step 9 is
  complete; `agent.graph` is now part of the strict override scope.
- `api.app` — strict-clean in its own mypy invocation with `follow_imports=skip`.

CI gate (как gate, не informational): `python -m mypy auth db/models.py
db/engine.py llm/providers/ config/settings.py agent/state.py
agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py
--no-incremental --show-error-codes`, plus a separate `api/app.py` mypy
invocation. Любой регресс блокирует PR (`.github/workflows/ci.yml type-check
job`).

2026-04-30 sanity verification on `f1e2be0`:

- `python -m ruff check api\app.py api agent auth db llm config evaluation scripts tests`
  -> clean.
- `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py
  agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py
  --no-incremental --show-error-codes` -> 18 source files clean.
- `python -m mypy api\app.py --no-incremental --follow-imports=skip --show-error-codes`
  -> clean.
- `python -m pytest tests -q --ignore=tests/integration --ignore=tests/test_a11y.py
  -p no:schemathesis -p no:cacheprovider --timeout=60
  --basetemp=.tmp\pytest-nonintegration-continuation`
  -> 603 passed, 4 skipped.

## What was done in this session (2026-04-26)

- Audited every root-level Python file and confirmed which ones have package
  counterparts and which are orphans.
- Replaced misleading `"""ingestion/chunking.py` / `"""integrations/bitrix.py`
  / etc. headers with accurate descriptions of the file's actual role.
- Wrote this DEPRECATIONS.md to capture the migration plan for future
  sessions. **No files were moved or removed in this pass** — that work is
  scoped to dedicated PRs (see Phases 1-5 above).

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
| `manager.py` | 905 | 🔴 active legacy | (this is canonical) | `vectordb/manager.py` is a tenant-aware wrapper. Imported from `ingestion/pipeline.py:36` and `vectordb/manager.py:11`. |
| `sqlite_trace.py` | 968 | 🔴 active legacy | (this is canonical) | `tracing/sqlite_trace.py` is a thin PII-redacting wrapper. Imported from 3 scripts + `tracing/__init__.py`. |
| `loader.py` | 296 | 🔴 active legacy | `ingestion.loader` (different impl, +csv/json) | `api/app.py:185-194` prefers root, falls back to `ingestion.loader`. Behavior is **not equivalent** — root has `DocumentChangeTracker`, package has csv/json. |
| `chunking.py` | 397 | 🔴 active legacy | (no canonical yet) | Standalone evaluation/tuning script. Header says "ingestion/chunking.py" but no such file exists. Referenced by name from `config/settings.py`, `ingestion/pipeline.py`, `manager.py`, `seed_docs.py`. |
| `bitrix.py` | 130 | 🔴 active legacy | (no canonical yet) | Header says "integrations/bitrix.py" but `integrations/` package was never created. Imported from `mock_inbox.py:54`. |
| `mock_inbox.py` | 156 | 🔴 active legacy | (no canonical yet) | Header says "integrations/mock_inbox.py" but `integrations/` package was never created. Imported from `agent/graph.py:134`. |
| `seed_docs.py` | 156 | 🔴 active legacy | (no canonical yet) | Header says "demo/seed_docs.py" but lives in root. Standalone demo script. |
| `cache.py` | 266 | 🟢 canonical | `cache.py` (root) | Different concern from `cache/redis_cache.py` (in-memory LRU vs Redis). Not a duplicate. |

## Migration plan — do these in order, in dedicated PRs

### Phase 1 — kill the no-op shims ✅ DONE 2026-04-26

Removed `graph.py`, `state.py`, `prompts.py` shims from project root. Also
removed the dead `except ImportError:` fallback in `agent/graph.py:48-80`
which had been re-exporting through the same shims (circular fallback).

### Phase 2 — rename misleading legacy files (medium risk, ~2 hours)

Move/rename to align with their actual roles. Each move requires updating
import sites:

1. `bitrix.py` → `integrations/bitrix.py`. Create `integrations/__init__.py`.
   Update `mock_inbox.py:54`, `config/settings.py`.
2. `mock_inbox.py` → `integrations/mock_inbox.py`. Update `agent/graph.py:134`,
   `tests/test_mock_inbox_import.py`, `config/settings.py`.
3. `seed_docs.py` → `demo/seed_docs.py`. No production imports — only doc updates.

### Phase 3 — collapse `manager` and `sqlite_trace` (high risk, ~half day each)

These have non-trivial wrappers. Two acceptable end-states:

**Option A (preferred)**: move root content into the package, delete the
wrapper, fold tenant-aware caching / PII redaction into the canonical module.

**Option B**: keep current split, but rename root `manager.py` to
`vectordb/_base_manager.py` so the canonical import is `vectordb.manager`
everywhere. Same idea for `sqlite_trace.py` → `tracing/_base_trace.py`.

### Phase 4 — resolve the `loader` fork (high risk, ~half day)

Decide: keep `DocumentChangeTracker` (root) or `csv/json` support
(`ingestion.loader`). The two implementations have diverged by 511 LOC, so
this is a product decision, not a refactor. Likely answer: merge both
features into `ingestion.loader`, mark root `loader.py` as a shim, then
remove the fallback chain in `api/app.py:185-194`.

### Phase 5 — find a home for `chunking.py`

It is a tuning script, not a production module. Move to `scripts/chunking_eval.py`
and update references in `config/settings.py`, `ingestion/pipeline.py`,
`manager.py`, `seed_docs.py`.

## api/app.py monolith split — in progress

`api/app.py` is now 2128 LOC. Most endpoint groups now live under
`api/routers/`. The large conversation orchestration block now lives in
`api/routers/conversation.py` and still reaches into `api.app` lazily for
`_sessions`, `_session_last_access`, `_db_retry_after`, and
`_pipeline_semaphore` so existing `monkeypatch.setattr(api.app, ...)` tests
continue to work.

### Done sub-routers

- `api/routers/system.py` — `/health/live`, `/health/ready`, `/health`,
  and `/metrics` (Phase 2 PoC + Phase 2a).
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

64 endpoints out of 69 API routes are now in dedicated router files. Latest
sanity: 69 `/api` routes, 13/13 conversation/auth/tenant-focused tests pass,
and 56/56 broader `/api/ask` tests pass (2026-04-27, using explicit pytest
`--basetemp` because the default Windows temp directory is not readable in this
workspace).

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

### Next splits (in order of risk)

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

The 2a-2m split plan is complete. `api/app.py` still owns the small auth/session
surface (`/auth/login`, `/auth/refresh`, `/sessions/*`); those can be extracted
later as a separate cleanup if the goal is a pure app-shell module.

## Type-checking debt

Strict mypy is enforced via `pyproject.toml [[tool.mypy.overrides]]` for:

- `auth.*` — passes clean (4/4 files)
- `db.models` — passes clean

The following modules are intentionally **not** strict yet:

- `llm.providers.*` — 14 outstanding type errors as of 2026-04-26 (lambda
  inference, type narrowing of provider unions, dict[str, object] kwargs in
  base provider). Resolve before promoting to strict.
- `db.engine` — `Pool.size/checkedout/overflow` attributes flagged as
  missing by SQLAlchemy stubs; needs cast or stub bump.
- `config.settings` — re-defined names + Optional/str narrowing; cleanup is
  scoped to a separate refactor.

To run mypy locally:

```
mypy auth db/models.py    # strict, must pass
mypy llm/providers        # informational, currently 14 errors
```

## What was done in this session (2026-04-26)

- Audited every root-level Python file and confirmed which ones have package
  counterparts and which are orphans.
- Replaced misleading `"""ingestion/chunking.py` / `"""integrations/bitrix.py`
  / etc. headers with accurate descriptions of the file's actual role.
- Wrote this DEPRECATIONS.md to capture the migration plan for future
  sessions. **No files were moved or removed in this pass** — that work is
  scoped to dedicated PRs (see Phases 1-5 above).

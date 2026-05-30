# Audit Codex 30.05.2026 - RAG Support Assistant

Дата аудита: 2026-05-30
Проект: `D:\RAG_Support_Assistant`
Ветка: `master`
HEAD: `4d60479` (`ci: clarify weekly report delivery workflow`)
Remote: `origin/master` на том же HEAD
Tracked files: 698 (`git ls-files`)
`rg --files`: 648 файлов без ignored artefacts
JS bundle/key count baseline: не применимо к основному приложению; UI - статические HTML/JS, docs-site - отдельный Astro-подпроект.

## Compact Note

Предыдущий аудит не использовался как источник истины. Я восстановил состояние из текущего checkout, `git status`, durable docs и локальных gates. `audit_codex_30_05_26.md` уже существовал как untracked artefact прошлой попытки; текущий файл полностью перезаписан свежим аудитом.

## Executive Summary

Проект в хорошем инженерном состоянии: полный pytest green, coverage выше gate, Python lint/type/security gates green, Helm lint/render green, Alembic имеет единственную head-ревизию. Архитектурно это зрелый FastAPI + LangGraph RAG-сервис с Postgres/Redis, Chroma/Qdrant abstraction, provider runtime, observability, evaluation loop, review queue, backup/restore and docs-site.

Главные риски не в backend gates, а на стыках:

- **High:** DOM XSS в agent UI через `innerHTML` с API-данными тикетов/сообщений; рядом хранится bearer token в `localStorage`, что превращает XSS в захват agent/admin сессии.
- **High:** `docs-site` имеет npm audit high vulnerability в транзитивном `devalue@5.8.0`.
- **Medium:** production app не добавляет security headers/CSP и оставляет FastAPI docs/OpenAPI включенными по умолчанию.
- **Medium:** `docker-compose.yml` выглядит dev-only, но публикует app/Postgres/Redis/Ollama/Jaeger на host ports и не выставляет `RAG_ENV=production`.
- **Medium:** startup auto-migration fail-open может поднять приложение с неполной схемой БД.
- **Medium:** `api/app.py` и `agent/graph.py` остаются крупными центрами сложности; coverage слабее всего именно в критичных orchestration/admin areas.
- **Low:** durable handoff state устарел относительно текущего HEAD, что похоже на причину "невозможного компакта".

## Verification

| Gate | Result |
|---|---|
| `python -m pytest -p no:schemathesis` | **PASS**: 748 passed, 5 skipped, 14 warnings, 17:34 |
| `python -m pytest -p no:schemathesis --cov --cov-report=term` | **PASS**: 748 passed, 5 skipped, 15 warnings, total coverage 71.56%, gate 70% |
| `python -m ruff check .` | **PASS** |
| strict mypy scope | **PASS**: 18 source files clean; warning about unused `api.app` override section |
| `python -m mypy api/app.py --no-incremental --follow-imports=skip` | **PASS**; warning about unused agent override sections |
| `python -m bandit -r . -ll -c pyproject.toml ...` | **PASS**: 0 medium/high; 42 low informational |
| `python -m pip_audit ... -r requirements.lock` | **PASS**: no known Python vulns, 1 ignored Chroma advisory |
| `npm --prefix docs-site run astro -- build` | **PASS**, warning: `/404` conflicts with catch-all route |
| `npm --prefix docs-site audit --audit-level=moderate` | **FAIL**: 1 high severity vulnerability in `devalue` |
| `helm lint deploy/helm/ --strict` | **PASS** |
| `helm template ... --set secrets.existingSecret=ci-placeholder ...` | **PASS** |
| `python -m alembic heads` | **PASS**: single head `017` |

## Architecture Snapshot

- API entrypoint: `main.py` re-exports `api.app:app`.
- Core app: `api/app.py`, 1,633 LOC, owns startup, middleware, legacy helpers, health probes, vector-store initialization, retention tasks and root API router.
- Routers: extracted under `api/routers/` for conversation, upload, auth, admin ops, review queue, experiments, KB, analytics, agent endpoints and system health.
- RAG graph: `agent/graph.py`, 1,824 LOC, builds LangGraph flow: classify -> transform -> retrieve -> grade -> generate -> verify -> evaluate -> retry/suggest/log.
- Retrieval: Chroma default, Qdrant stub/path, hybrid BM25 + vector, optional reranker, semantic chunking, parent-child retrieval.
- LLM runtime: provider registry in `config/providers.yml`, default profile `gracekelly-primary`, local Ollama fallback, direct Mistral profile available with credential validation.
- Persistence: Postgres via SQLAlchemy async + Alembic 001..017; trace store also uses SQLite for operational traces.
- Auth: JWT + legacy API key; RBAC dependencies; OIDC SSO callback issues cookies.
- UI: static HTML pages under `static/`; docs-site is separate Astro/Starlight subproject.
- Deploy: Dockerfile, docker-compose, Helm chart, GitHub Actions CI, Pages docs workflow and weekly-report workflow.

## Findings

### H1 - Agent UI DOM XSS can steal bearer tokens

Severity: **High**
Files:

- `static/agent.html:162-165`
- `static/agent.html:183-185`
- `static/agent.html:248-250`
- `api/routers/agent.py:225-240`
- `api/routers/agent.py:297-321`
- `static/agent.html:126-128`
- `static/agent.html:301-303`

Evidence:

- The backend returns raw `user_question`, `operator_response`, `message.content`, and similar-ticket fields from DB.
- The agent UI renders those fields with `innerHTML`.
- The same page reads/writes `agent_token` in `localStorage`.

Impact:

An escalated user question, stored conversation message, or operator response containing HTML/JS can execute in an agent's browser. Because the bearer token is in `localStorage`, this can become account/session takeover for agent/admin workflows.

Recommended fix:

- Replace dynamic `innerHTML` paths with `textContent` and DOM node construction.
- Keep `innerHTML` only for hardcoded static SVG/empty-state snippets.
- Add a regression test that injects `<img onerror=...>` / `<script>`-like ticket content and asserts it is rendered as text.
- Add CSP after the UI is cleaned up.

### H2 - docs-site has a high npm vulnerability

Severity: **High**
Files:

- `docs-site/package-lock.json:2469`
- `docs-site/package-lock.json:3484-3488`

Evidence:

- `npm --prefix docs-site audit --audit-level=moderate` reports `devalue 5.6.3 - 5.8.0`, severity high, `GHSA-77vg-94rm-hx3p`.
- Current lock has `devalue@5.8.0`.
- `npm --prefix docs-site outdated` shows available updates: `astro 6.3.0 -> 6.4.2`, `@astrojs/starlight 0.39.1 -> 0.39.2`, `yaml 2.8.4 -> 2.9.0`.

Impact:

The public docs build may carry a known high-risk transitive dependency. Even if the app backend is clean by `pip-audit`, Node supply-chain security is not currently green.

Recommended fix:

- Run a controlled docs-site dependency bump, starting with `npm audit fix` or explicit Astro/Starlight updates.
- Commit `docs-site/package-lock.json`.
- Add `npm audit --audit-level=moderate` to `docs-site.yml` or CI.

### M1 - Missing CSP/security headers and public OpenAPI surface

Severity: **Medium**
Files:

- `api/app.py:1720`
- `api/app.py:1816-1825`
- `api/app.py:1893-1896`

Evidence:

- `FastAPI(...)` is created without production-specific `docs_url`, `redoc_url`, or `openapi_url` controls, so `/docs`, `/redoc`, and `/openapi.json` are available by default.
- Middleware adds `X-Request-Id`, but no CSP, `X-Frame-Options`, `X-Content-Type-Options`, HSTS, Referrer-Policy, or Permissions-Policy.
- Static files are mounted directly via `StaticFiles`.

Impact:

The app exposes route/schema metadata and has no browser-side mitigation against the XSS class found above. This is especially relevant because the project ships admin/agent static pages.

Recommended fix:

- Add production settings for docs/OpenAPI exposure.
- Add security headers middleware, at minimum CSP after inline script cleanup, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, frame policy and HSTS when behind HTTPS.
- Consider serving admin/agent UI behind auth-gated routes only.

### M2 - docker-compose is unsafe if treated as production

Severity: **Medium**
Files:

- `docker-compose.yml:5-6`
- `docker-compose.yml:29-37`
- `docker-compose.yml:46-50`
- `docker-compose.yml:59-70`
- `docker-compose.yml:73-76`

Evidence:

- Ollama, Postgres, Redis, Jaeger and app are published to host ports.
- Postgres has fallback password `${POSTGRES_PASSWORD:-rag_dev_password}`.
- App environment does not set `RAG_ENV=production`; it relies on `.env` and defaults.

Impact:

This is fine for local dev, but risky if someone runs compose on a reachable host. In that mode production fail-fast checks for CORS/secrets may never activate, and DB/Redis/Jaeger become network-exposed.

Recommended fix:

- Label compose explicitly as local-dev only in README and compose comments.
- Bind services to `127.0.0.1` or move infra ports behind profiles.
- Add a production compose override only if needed, with `RAG_ENV=production` and no default DB password.

### M3 - Alembic auto-migration fails open on startup

Severity: **Medium**
File: `api/app.py:1460-1486`

Evidence:

- `_run_alembic_upgrade()` defaults `AUTO_MIGRATE=true`.
- On any migration exception, startup logs a warning and continues.
- Lifespan always calls it before vector initialization (`api/app.py:1503`).

Impact:

In production, a failed migration can leave the app serving traffic against an incompatible schema. The CI migration round-trip gate reduces probability, but not runtime failure impact.

Recommended fix:

- In `RAG_ENV=production`, fail startup on migration failure unless an explicit `AUTO_MIGRATE_FAIL_OPEN=true` is set.
- Or disable auto-migrate in production and require a separate migration job as the Helm/CI contract.

### M4 - Central modules remain large and under-covered

Severity: **Medium**
Evidence:

- Largest tracked Python modules:
  - `agent/graph.py`: 1,824 LOC
  - `api/app.py`: 1,633 LOC
  - `api/routers/conversation.py`: 837 LOC
  - `config/settings.py`: 798 LOC
  - `vectordb/_base_manager.py`: 727 LOC
- Fresh coverage weak spots:
  - `api/app.py`: 55%
  - `agent/tools.py`: 37%
  - `auth/oidc.py`: 44%
  - `api/routers/admin_review.py`: 52%
  - `api/routers/analytics.py`: 56%
  - `channels/email_channel.py`: 54%
  - ingestion modules around 54-59%

Impact:

The test suite is broad, but risk concentrates in orchestration, auth/SSO, ingestion, admin review and legacy app helpers. These are exactly areas where regressions can be expensive.

Recommended fix:

- Continue extracting `api/app.py` into startup, health, vector-store, regression/admin service modules.
- Add focused tests for uncovered branches instead of only raising the global threshold.
- Put module-level coverage targets on auth/SSO, admin review and agent tools.

### L1 - Deprecation warnings should be closed before upstream breaks

Severity: **Low**
Files:

- `agent/graph.py:213-222`
- `llm/providers/ollama.py:104-122`
- `scripts/restore_verify.py:202-203`
- `auth/oidc.py:12-15`

Evidence from pytest:

- LangChain deprecates `Ollama` / `ChatOllama` imports used by the project.
- Authlib warns `authlib.jose` is deprecated in favor of `joserfc`.
- Python 3.14 will change default `tar.extractall` filtering.
- Coverage warns that the C tracer is unavailable in the local Python 3.13 environment.

Impact:

No current failure, but these warnings are calendar-driven maintenance debt.

Recommended fix:

- Move Ollama integrations to `langchain-ollama`.
- Track Authlib/Joserfc migration path.
- Pass an explicit safe tar extraction filter or member validation.
- Check local coverage wheel/install if coverage runtime matters on Windows.

### L2 - Durable state docs are stale relative to current HEAD

Severity: **Low**
Files:

- `AGENT_STATE.md:7-17`
- `AGENT_STATE.md:29-31`
- `next-session-3-subagents.md`

Evidence:

- Current HEAD is `4d60479`.
- `AGENT_STATE.md` still records branch source through `a86b44c`, baseline HEAD `415d4c8`, and 697 tracked files.
- Current tracked file count is 698.
- `next-session-3-subagents.md` also describes the state as closed through `a86b44c`.

Impact:

This is not a runtime defect, but it is likely related to the previous impossible compact: future agents reading durable state can incorrectly chase stale work or stale HEAD assumptions.

Recommended fix:

- Update durable state after this audit only if autonomous handoff docs are still expected to be source of truth.
- Prefer durable docs that avoid volatile HEAD/file-count assertions unless the file is explicitly a snapshot.

### L3 - Local ignored artefacts are large and some cache dirs are inaccessible

Severity: **Low**
Evidence:

- `.mypy_cache`: 22,136 files, 438.75 MB
- `docs-site/node_modules`: 21,262 files, 309.82 MB
- `.tmp`: 1,881 files, 173.42 MB
- `data`: 677 files, 117.99 MB
- `htmlcov`: 108 files, 9.23 MB
- `git status --ignored` and `rg` report permission denied for many `tests/pytest-cache-files-*` directories and one `data/tmp...` directory.

Impact:

This slows audits and creates noisy permission errors. It also makes file-count baselines hard to compare.

Recommended fix:

- Add a documented local cleanup command or script that only targets ignored caches.
- Do not delete data/reports automatically; require explicit operator opt-in for runtime data.

## Strengths

- Full Python test suite is large and green on Python 3.13.
- Coverage gate is honest and currently passes.
- Python dependency lock is hash-based and audited.
- CI covers lint, type-check, unit/integration matrix, migrations, Helm, Bandit, pip-audit and regression eval when prompt/settings/experiment inputs change.
- Production settings validate CORS, JWT secret, session secret, admin password hash, DB encryption key and paid-provider credentials.
- Helm chart has stronger production guardrails than compose: required secrets and `CORS_ORIGINS` fail-fast.
- Tenant-aware tests exist across sessions, vector store, review queue, analytics and admin surfaces.
- Upload handling sanitizes filenames, rejects dotfiles and enforces upload byte limits.
- PII redaction exists for trace state snapshots via `tracing.sqlite_trace`.
- Observability is broad: Prometheus metrics, component health, retry/circuit-breaker metrics, alert rules, trace/audit retention.

## Prioritized Remediation Plan

1. Fix `static/agent.html` XSS and add a regression test.
2. Add CSP/security headers after inline-script constraints are understood.
3. Update `docs-site` dependencies and add `npm audit` to CI.
4. Decide production policy for `/docs`, `/redoc`, `/openapi.json`.
5. Make Alembic startup failure policy production-safe.
6. Mark `docker-compose.yml` as dev-only and bind infra ports more narrowly.
7. Close deprecation warnings before LangChain/Authlib/Python 3.14 changes become breaking.
8. Refresh or simplify durable handoff docs to avoid compact-resume drift.
9. Continue breaking down `api/app.py` and add focused tests for low-coverage critical modules.

## Final Assessment

Current readiness: **strong local/CI readiness with two security fixes required before public production exposure**.

Backend quality is materially better than the static UI and docs-site supply-chain posture. I would not expose the admin/agent UI on an untrusted network until H1 is fixed and browser security headers are added. For internal/local use, the project is operationally solid and well verified.

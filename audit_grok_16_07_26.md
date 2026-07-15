# Аудит RAG_Support_Assistant — 16.07.26 (Grok)

**Аудитор:** Grok 4.5 (xAI)  
**Дата:** 2026-07-16  
**HEAD:** `0b0234c` (`test(ci): align docs-site npm-audit assertion with critical-only gate`)  
**Ветка:** `master` = `origin/master` (синхронизирована)  
**Remote:** `https://github.com/brownjuly2003-code/RAG_Support_Assistant.git`  
**Последний коммит:** 2026-06-18 (~4 недели без новых code-коммитов на момент аудита)

---

## 0. Методология и границы

Аудит **доказательный**: сверка с кодом, git, lock-файлами, прошлыми аудитами (`docs/audits/*`), handoff (`AGENT_STATE.md`, `FLANT_DOGFOOD_FINDINGS.md`), live-прогон статических гейтов.

### Что прогонялось вживую

| Проверка | Результат | Комментарий |
|---|---|---|
| `ruff check .` (конфиг проекта: E/F/W + B904/B905/B009/RUF012/UP/I) | **PASS** | All checks passed |
| `bandit -r … -ll` | **0 High**, **7 Medium** | 19 191 LOC; medium — B608 placeholders + B310 urlopen |
| `python -c "from api.app import app; app.openapi()"` | **71 path**, **67 /api** | приложение собирается |
| OpenAPI route inventory | 72 endpoint-декоратора в исходниках | согласуется с README |
| Alembic chain | **17 ревизий, 1 head** (`017`) | linear ✔ |
| Light pytest (`test_module_layout`, `test_docs_quality`, entrypoint) | 29 pass / **1 fail** | fail — env-mismatch (см. §0.1) |
| Сверка findings аудитов 03.06 и dogfood 18.06 | построчно по коду | §4 |

### Что НЕ гонялось на этой Windows-машине (и почему)

- Полный `pytest` / coverage / mypy strict на production-пакетах — **глобальный Python 3.13.7** без project venv; lock рассчитан на **Python 3.11 + Linux x86_64** (Docker/`python:3.11-slim`).  
- `pip-audit` по lock — сетевой; состояние CVE берётся из `AGENT_STATE` + pinned versions в lock.  
- Live RAGAS / full-corpus embed / rerank — **>1 GiB RAM**, запрещено локальным resource guard; heavy — Mac/Colab/Kaggle.  
- Источник истины для unit/integration/mypy — **CI** на Linux 3.11 + hashed locks.

### 0.1. Локальный env-mismatch (не баг продукта)

| | Project lock (CI) | Локальный global |
|---|---|---|
| Python | 3.11 | 3.13.7 |
| fastapi | **0.136.1** | 0.138.1 |
| starlette | **1.0.1** | 0.50.0 |

На 0.138 nested-роутеры лежат как `_IncludedRouter` **без** `.path` на top-level `app.routes` → `test_api_namespace_is_populated` (смотрит flat `app.routes`) падает с «0 /api routes», хотя OpenAPI содержит **67** `/api/*`. На CI с lock это, с высокой вероятностью, зелёное. **Риск:** при будущем bump fastapi тест станет хрупким — лучше считать пути через `app.openapi()["paths"]` или рекурсивный walk.

---

## 1. Executive Summary

Проект — **зрелый production-grade multi-tenant RAG support assistant** (FastAPI + LangGraph + Chroma + provider routing + Postgres/Redis + Helm). За 1.5 месяца с аудита 03.06.26 закрыты почти все code-level findings того аудита, прогнан data-backed adaptive-retrieval workstream (NO-SHIP), закрыт external dogfood (Deckhouse/Flant), docs-site доведён до live E20.

**Самооценка: 8.9 / 10** (локальное инженерное качество).  
Потолок по-прежнему держит **доказанное end-to-end качество на live LLM + CI quality gate**, плюс **свежий dep-CVE backlog** (aiohttp/cryptography) и **single-worker topology** как архитектурный потолок scale-out.

### Топ-5 прямо сейчас

| # | ID | Severity | Суть |
|---|---|---|---|
| 1 | **D1** | **HIGH (ops/sec)** | Locked deps: `aiohttp==3.14.0` (8 CVE → fix 3.14.1), `cryptography==47.0.0` (GHSA → fix 48.0.1). `AGENT_STATE` помечает CI `security`+`pre-commit` красными. Чинить focused lock-regen. |
| 2 | **Q1** | **HIGH (product)** | RAGAS baseline есть (2026-06-05), но **context_precision ≈ 0.51** — слабое звено; **нет blocking quality-gate в CI**. Regression-eval informational + path-filtered. |
| 3 | **A1** | **MEDIUM** | Single worker / single replica by design (in-process session, confirm-actions, caches, CB). Helm HPA disabled. Scale-out = отдельный workstream (Redis/Postgres state). |
| 4 | **S1** | **MEDIUM (defense-in-depth)** | Bearer-токен admin/agent всё ещё в `localStorage` (XSS → session theft). CSP уже есть — хорошо, но cookie httpOnly сильнее. |
| 5 | **C1** | **MEDIUM (maintainability)** | `agent/graph.py` ~2317 LOC, `api/app.py` ~1570, `settings.py` ~1029, `_base_manager.py` ~1100. Декомпозиция не доведена; mypy для app/vectordb — `--follow-imports=skip`. |

### Что изменилось к лучшему с 03.06

- F1 fire-and-forget → `utils.background_tasks.spawn_tracked` + guard-тест.  
- F2 CSP → shipped (`Content-Security-Policy` + inline JS → `/static/*.js`).  
- R6 device → `RAG_DEVICE` / `_resolve_device()` (не hardcoded CPU).  
- F6 lint ratchet → ruff select расширен (I, B904/B905/B009, RUF012, UP).  
- R7 частично закрыт: free-RAGAS 100 aircargo cases (см. §7).  
- Adaptive-retrieval F1–F4 + Phase-5: **opt-in factcard, default NO-SHIP по данным**.  
- Dogfood 5 findings → code fixes (commit `1343323`), defaults unchanged.  
- Type-hardening: почти все prod-пакеты в mypy strict-scope.  
- Remote embeddings backend (`RAG_EMBEDDING_BACKEND=remote`).  
- Ask wall-budget (`RAG_ASK_BUDGET_SEC`).  
- Headless-safe `main.py` (`UVICORN_RELOAD` default off).

---

## 2. Состояние репозитория

| Параметр | Значение |
|---|---|
| HEAD / branch | `0b0234c` on `master`, tracking `origin/master` |
| Worktree dirty (untracked) | `FLANT_DOGFOOD_FINDINGS.md`, `presentation.html`, `plan_for_pres.md`, `rag_new_explanation.md`, `docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`, `_ref_presentation3.html` — **не секретные**, в основном презентация/dogfood notes |
| История | **499** коммитов; автор почти целиком `JuliaEdom` |
| Python src (без tests/scripts/archive) | ~**19k LOC** bandit-scan; **162** src-модуля, **~37k LOC** если считать scripts+config |
| Тесты | **151** `test_*.py`, **826** `test_*` функций (+ integration 7 сценариев) |
| Endpoints | **72** decorator sites; OpenAPI **71** path (**67** `/api/*`) |
| Alembic | **17** revisions, single head `017` ✔ |
| Крупнейшие модули | `agent/graph.py` ~2317 · `api/app.py` ~1570 · `vectordb/_base_manager.py` ~1100 · `config/settings.py` ~1029 · `api/routers/conversation.py` ~960 · `tracing/_base_trace.py` ~901 |
| scripts/ | **41** файла ~416 KB — ops CLIs, вне coverage/mypy |
| docs/audits | 8 предыдущих аудитов (opus/claude/codex/kimi/mm) |
| TODO/FIXME в prod | **0** (placeholder `XXXXXX` в Bitrix example URL — не TODO) |

---

## 3. Архитектура

```text
User / Email / Widget / Telegram
        │
        ▼
  FastAPI (api.app) + Auth (JWT / OIDC / API-Key / RBAC)
        │
        ▼
  LangGraph agent (agent/graph.py)
    classify → transform(+HyDE) → retrieve → grade_docs (batch CRAG)
    → generate → verify_facts → evaluate → route|retry (Self-RAG)
        │
        ├── ChromaDB per-tenant + BM25 hybrid + RRF + cross-encoder
        ├── Optional: graph retrieval / factcard strategy (opt-in)
        ├── GraceKelly / Ollama / Mistral provider runtime + failover
        ├── Postgres (sessions, audit, copilot, analytics, experiments)
        ├── Redis cache
        ├── SQLite traces + OTel + Langfuse + Prometheus
        └── Channels: email, Bitrix, Telegram
```

### Сильные стороны дизайна

1. **Retrieval stack 2026-уровня:** hybrid (vector+BM25+RRF), multilingual reranker `BAAI/bge-reranker-v2-m3`, structural/parent expansion (D2), semantic chunking default on, contextual headers, fact verification, Self-RAG with bounded iterations.  
2. **Provider abstraction:** profiles (`gracekelly-primary`, `local-first`, `external-mistral`, `gracekelly-mixed`), daily cost limit, failover chain, changeme-key → missing.  
3. **Tenant isolation:** JWT claim, per-tenant Chroma collections `rag_docs_{tenant}`, cache keys, admin filters — dogfood подтвердил чистую изоляцию.  
4. **Production fail-fast:** `Settings.validate()` в production отвергает CORS `*`, dev JWT secret, short secrets, missing `DB_ENCRYPTION_KEY`.  
5. **Ops maturity:** Helm chart + cronjobs (eval, review, backlog, backup, restore-verify, thresholds), graceful shutdown (ready→503 drain), liveness/readiness split, request-id, rate limits, circuit breaker.  
6. **Knowledge loops:** nightly eval, online evaluators (7 checks), KB gap detector, KB builder drafts, review queue, improvement backlog, stale-doc freshness.  
7. **Evidence culture:** adaptive-retrieval закрыт **NO-SHIP по данным** (Phase-5), а не «забыли зашиппить» — это редкая и правильная дисциплина.

### Архитектурные ограничения (осознанные)

| Ограничение | Где задокументировано | Риск |
|---|---|---|
| **1 worker / 1 replica** | Dockerfile CMD, Helm `replicaCount: 1`, HPA off, `docs/DEPLOYMENT.md` | Horizontal scale невозможен без выноса session/confirm/caches/CB в Redis/Postgres |
| Windows + local BGE-M3 | 1 GiB process guard; dogfood | Heavy ingest/search — Mac/remote only; смягчено `RAG_EMBEDDING_BACKEND=remote` |
| Graph retrieval default `off` | settings + plan 2026-06-05 | Корректно до threshold/connectivity gate |
| Factcard default off | Phase-5 NO-SHIP | Opt-in only; auto-route не включать без новых данных |

---

## 4. Сверка findings прошлых аудитов

### 4.1. Аудит Claude 03.06.26

| Finding | Тогда | Сейчас (16.07) | Доказательство |
|---|---|---|---|
| **R7** RAGAS not run at scale | HIGH open | **частично ЗАКРЫТ** | `reports/ragas/20260605T214926Z-…`: 100 cases, free-ragas, mistral-small; **faithfulness 0.77, answer_relevancy 0.83, context_precision 0.51, context_recall 0.92**. CI gate всё ещё нет → остаток как **Q1** |
| **F1** bare `create_task` | MEDIUM | **ЗАКРЫТ** | `utils/background_tasks.spawn_tracked`; audit/conversation/admin_* используют его; lifespan tasks явно named; `tests/test_background_tasks.py` |
| **F2** no CSP | MEDIUM | **ЗАКРЫТ** | `api/app.py` `_SECURITY_HEADERS["Content-Security-Policy"]`; inline → `static/*.inline.js` (commit `67dc286`) |
| **F3** blocking FS in async | LOW | **OPEN (minor)** | wide ruff ASYNC240 ×4 — не блокер |
| **F4** asyncio.run+dispose in pipeline | LOW | **OPEN (latent)** | online evaluators path; dogfood noise mitigated separately |
| **F5** silent except/pass | LOW | **OPEN, вырос** | ~65 sites outside tests (conversation.py 15, app.py 12, graph 7…) |
| **F6** narrow ruff select | LOW process | **частично ЗАКРЫТ** | select расширен; wide scan всё ещё 882 findings (RUF001 unicode RU, RUF100 unused-noqa 162, B008 119…) |
| **F7** mypy `--follow-imports=skip` | LOW | **OPEN, осознанно** | api/routers + vectordb; memory/timeout tradeoff, документирован |
| **R6** reranker CPU hardcoded | LOW | **ЗАКРЫТ** | `_resolve_device()` + `RAG_DEVICE` |
| Bearer in localStorage | residual | **OPEN** | admin/agent/analytics JS |

### 4.2. Dogfood Flant 18.06 → commit `1343323`

| Finding | Статус | Как закрыто |
|---|---|---|
| #1 contextual headers progress/concurrency | **FIXED (opt-in levers)** | progress logs + `INGESTION_CONTEXTUAL_CONCURRENCY`; default headers **не** выключали (metadata path без LLM — уточнение в plan) |
| #2 online-eval Postgres noise | **FIXED** | per-process warn dedup (`_online_eval_first_time`) |
| #3 hang without wall budget | **FIXED (opt-in)** | `RAG_ASK_BUDGET_SEC` default 0; route `"timeout"` |
| #4 remote embeddings | **FIXED (opt-in)** | `RAG_EMBEDDING_BACKEND=remote` + `_RemoteEmbeddings` |
| #5 reload=True flap | **FIXED** | `UVICORN_RELOAD` default false |

### 4.3. Adaptive retrieval (июнь 2026)

| Track | Статус |
|---|---|
| F1–F4 factcard lane | **SHIPPED opt-in** (`RAG_RETRIEVAL_STRATEGY=factcard`, hybrid fallback) |
| R1 router classifier | **SHIPPED**, не в дефолте |
| Phase 3 auto-route / R2 / Phase 4 | **NO-SHIP-to-default** |
| Phase 5 delta | **ПРОГНАН:** composite FULL 79 vs D2 97 (Δ−18); needs-slice 19 regressions; augment safe but marginal |  
| Residual MISS `customs-clearance-fields` | **зафиксирован** (MISS→PART only on keyword metric) |

Вердикт корректен: не ломать работающий D2 (FULL 96–97) ради 1–4 кейсов.

---

## 5. Гейты и verification

| Gate | Ожидание | Статус на 16.07 |
|---|---|---|
| ruff (project config) | clean | **PASS** locally ✔ |
| mypy strict scope | auth/db/llm/agent/… + skip for api/vectordb | CI-enforced; local heavy not run |
| pytest unit | ignore integration | CI; local env unsuitable |
| pytest integration | timeout thread | CI |
| coverage `fail_under=70` | ~70%+ | gate in pyproject; last honest baseline 70.02% (2026-04-29) |
| bandit med+ | 0 high | 0 high / 7 medium (known patterns) |
| pip-audit --strict | lock clean modulo ignores | **D1 risk:** aiohttp/cryptography need bump; ignores: CVE-2026-45829 (chroma no fix), GHSA-f4j7…, CVE-2025-3000 (torch) |
| pre-commit | ruff + pip-audit synced | ignore set 4-site sync (ci/pre-commit/local-gate/autopilot) |
| regression-eval | path-filtered, **non-blocking** | quality не гейтит merge |
| RAGAS in CI | — | **отсутствует** |
| docs-site Pages | separate workflow | last known: E20 live screenshot + npm-audit critical-only alignment |

**Process strength:** multi-site sync guards for mypy/pip-audit ignore sets — отличная anti-drift гигиена.

**Process gap:** quality metrics (RAGAS / keyword FULL-PART-MISS) не блокируют merge; regression mock легко проходит.

---

## 6. Безопасность

### 6.1. Что сделано хорошо

- JWT + refresh, OIDC Google/Microsoft, X-API-Key, RBAC roles.  
- Production secret validation (JWT length, no dev default, encryption key required).  
- CORS reject `*` in production.  
- Security headers: nosniff, DENY frame, Referrer-Policy, Permissions-Policy, **CSP**, HSTS in production.  
- Upload size limits, body size middleware, rate limits (ask/upload/login).  
- pgcrypto column encryption + `DB_ENCRYPTION_KEY`.  
- Docker non-root `USER app`, healthcheck, hashed lock install.  
- Helm secrets via K8s Secret / existingSecret; no default production passwords.  
- Compose ports bound to `127.0.0.1`.  
- Bandit 0 high; SQL B608 sites use **placeholder IN (?,?)** patterns (false-positive class).  
- Cost guard / paid API opt-in for benchmarks.

### 6.2. Открытые security findings

#### D1 — Stale transitive CVEs in lock — **HIGH (ops)**

| Package | Locked | Issue | Fix target (per AGENT_STATE) |
|---|---|---|---|
| `aiohttp` | 3.14.0 | CVE-2026-54273…54280 (8) | **3.14.1** |
| `cryptography` | 47.0.0 | GHSA-537c-gmf6-5ccf | **48.0.1** |
| `chromadb` | 1.5.9 | CVE-2026-45829 no fixed_in | ignore (accepted) |
| `torch` | 2.11.0 | CVE-2025-3000 no fix | ignore (accepted) |
| `pypdf` | 6.13.2 | previously bumped | ✔ |

**Remediation:** `uv pip compile` with `--upgrade-package aiohttp cryptography` + hashes on both locks; re-run pip-audit; sync ignore list only if residual unfixed.

#### S1 — Tokens in localStorage — **MEDIUM**

Admin/agent UIs: `localStorage` stores bearer tokens. CSP mitigates inline XSS, but any future `innerHTML` regression or compromised third-party script (`cdn.jsdelivr.net` for Chart.js in CSP) elevates impact.  
**Prefer:** httpOnly Secure SameSite cookies (cookie bridge middleware already exists for `access_token`).

#### S2 — Bandit B608 / B310 residual — **LOW**

- B608 in `api/_shared.py`, `tracing/_base_trace.py`, `api/app.py` — f-string SQL with **bound placeholders** (IDs from DB, not raw user SQL). Review once, keep pattern.  
- B310 `urlopen` in `settings.validate` Ollama health — ensure scheme allowlist (`http`/`https` only).

#### S3 — Dev defaults — **INFO (controlled)**

`session_secret_key` falls back to `dev-secret-change-in-production!` outside production; validate() blocks production. Compose default `POSTGRES_PASSWORD=rag_dev_password`. Acceptable for local, never for exposed hosts.

#### S4 — Single-process authz state — **LOW/ops**

Confirm-action pending state in memory: restart loses pending confirmations; multi-replica would break isolation of confirm flows. Documented; still a reliability footgun under deploy churn.

---

## 7. Качество RAG (product truth)

### 7.1. Измеренные baseline (evidence on disk)

**Free-RAGAS, aircargo, 100 cases, 2026-06-05** (`reports/ragas/20260605T214926Z-e728353a-aircargo-ragas.md`):

| Metric | Score | Комментарий |
|---|---:|---|
| faithfulness | **0.766** | приемлемо, не «отлично» |
| answer_relevancy | **0.833** | хорошо |
| context_precision | **0.509** | **слабое звено** — в top-k много шума |
| context_recall | **0.920** | отлично |

**Retrieval keyword (D2 baseline, Phase-0/5):** FULL ~96–97 / PART ~2–3 / MISS 1 (`customs-clearance-fields`).

**Cross-domain dogfood (Flant/Deckhouse, 12 questions):** answers coherent, quality self-scores 85–98, route=auto, no empty answers — domain transfer without code changes works.

### 7.2. Gaps

1. **context_precision ~0.5** — rerank/top_k/grade_docs могут резать шум сильнее; нужен targeted A/B, не «ещё один retrieval strategy».  
2. **No CI quality floor** — commercial plan RQ-2 (precision≥0.8, faithfulness≥0.85) **не реализован**.  
3. **Live full-graph latency** (dogfood): median ~190s on CPU+external provider; worst hangs without budget — mitigated only if `RAG_ASK_BUDGET_SEC` set.  
4. **Default fact verification / multi-step Self-RAG** = high LLM fan-out cost; model routing default **off**.  
5. Factcard path proven for list-style residual MISS but **loses exact keyword forms** when replacing D2 chunks.

### 7.3. Рекомендация по quality roadmap

1. Зафиксировать RAGAS numbers в README/OPERATIONS как official baseline.  
2. Working item: improve **context_precision** (rerank_k, grade threshold, parent-window chars) with offline A/B on same 100 cases.  
3. Optional nightly RAGAS job (Helm cron already has eval snapshot pattern) with drift alert — not necessarily PR-blocking first.  
4. Keep factcard opt-in; do not auto-route.

---

## 8. Код и maintainability

### 8.1. Hygiene — excellent

- 0 TODO/FIXME in production.  
- Canonical layout (`agent/*`, routers extracted).  
- Deprecations tracked (`DEPRECATIONS.md`).  
- Magic numbers → `config/settings.py` (with tests).  
- Guard tests for CI/pre-commit/mypy sync, docs quality, module layout.  
- Changelog + AGENT_STATE discipline (dense, sometimes superseding — acceptable for autopilot).

### 8.2. Complexity debt — open

| Module | LOC | Note |
|---|---:|---|
| `agent/graph.py` | ~2317 | god-module: nodes + session + online-eval + routing |
| `api/app.py` | ~1570 | still holds lifespan, middleware, re-exports, router wiring |
| `vectordb/_base_manager.py` | ~1100 | embed/rerank/hybrid/chunk/factcard-adjacent |
| `config/settings.py` | ~1029 | env surface very large (good docs, heavy discoverability) |
| `api/routers/conversation.py` | ~960 | ask/stream/chat paths |

**Prior art target (old Step 8):** app.py ≤600 — not met.

### 8.3. Lint debt beyond project gate

Wide ruff (`B,RUF,S110,ASYNC`) snapshot: **882** issues. Top clusters:

- RUF001/002/003 — Cyrillic in strings/docs/comments (noise for RU project; don't auto-fix blindly).  
- RUF100 ×162 — unused `# noqa` (safe cleanup).  
- B008 ×119 — function calls in defaults (FastAPI `Depends()` — often intentional).  
- S110 ×46 — try/except/pass.  
- ASYNC240/230 — blocking path/open in async.

**Recommendation:** autfix RUF100 only; treat B008 FastAPI Depends as baseline; gradually log critical-path silent `pass`.

### 8.4. Type system

- Production packages largely **mypy strict** (auth, db, llm.providers, agent core, tasks, utils, monitoring, channels, tracing, ingestion, evaluation, api routers).  
- `api.app` + `vectordb` via `--follow-imports=skip` — intentional memory/timeout tradeoff on Windows/CI.  
- Residual: integrations/ may be thinner; scripts/ excluded.

### 8.5. Test portfolio

| Layer | Assessment |
|---|---|
| Unit breadth | **Strong** — 150+ files covering auth, tenant, providers, graph helpers, security headers, helm, docker-compose, docs guards |
| Integration | Present (upload, concurrency, conversation, streaming, escalation, ingestion) |
| Coverage gate | 70% floor — honest but leaves critical modules thinner (historically tools/oidc/app) |
| Live eval | Opt-in only; correct for paid APIs |
| Fragility | `test_api_namespace_is_populated` coupled to FastAPI route object layout |

---

## 9. Observability & operations — strongest pillar (~9.8/10)

- ~50 Prometheus metrics, HTTP route templates, component health.  
- OTel spans on graph nodes / LLM (provider, model, tokens, cost, duration).  
- SQLite step traces + Langfuse optional.  
- Alert rules, chaos drill script, backup/restore with integrity verify + encryption tests.  
- Helm CronJobs: eval snapshot, review queue, improvement backlog, weekly report, threshold analysis, curated staleness, backup integrity.  
- Circuit breaker + retry observability.  
- Request correlation ID end-to-end.  
- Online evaluators (citation coverage, length anomaly, hit rate, tool efficiency, refusals, PII, language mismatch) — no judge LLM.  

**Do not “improve” this area with drive-by refactors.** Focus remaining ops energy on **D1 CVE lock** and optional RAGAS drift job.

---

## 10. Dependencies & supply chain

| Item | State |
|---|---|
| Hash-pinned locks (uv) | ✔ requirements.lock + dev |
| Docker `--require-hashes` | ✔ |
| pip-audit in CI + pre-commit | ✔ (with documented ignores) |
| Transitive CVE process | Mature (pypdf, pyjwt, mako, aiohttp bumps in history) |
| **Current red risk** | **aiohttp 3.14.0, cryptography 47.0.0** |
| Chroma no-fix CVE | accepted ignore |
| Torch no-fix CVE | accepted ignore |
| LangChain surface | large; pins on langchain-core/langsmith/starlette documented |

---

## 11. Documentation & knowledge management

| Asset | Quality |
|---|---|
| README | Strong landing after restructure; points to CONFIGURATION/OPERATIONS/DEPLOYMENT/QUICKSTART |
| CONFIGURATION.md / .env.example | Comprehensive, aligned with settings |
| AGENT_STATE.md | Extremely dense handoff (~132KB); excellent for autopilot, hard for humans — archive older blocks more aggressively |
| docs/audits | Good institutional memory |
| commercial-upgrade-plan.md | Still has unchecked RQ-2/RQ-3 quality CI items — **stale relative to shipped RAGAS reports** |
| Untracked presentation artifacts | Should stay untracked or move to docs-site; not product core |
| docs-site | Separate product surface; E20 live path completed 2026-06-16 |

---

## 12. Runtime topology & deploy readiness

| Check | Status |
|---|---|
| Production entrypoint `api.app:app` | ✔; `main.py` thin alias |
| Legacy unauth `/ask` etc. | Removed (guarded by tests) |
| Docker non-root + healthcheck | ✔ |
| Compose = local only | ✔ documented |
| Helm production secrets required | ✔ empty defaults force operator input |
| Migrations linear | ✔ 17 |
| Multi-replica ready | **NO** (by design) |
| Graceful shutdown | ✔ |
| Data encryption at rest | pgcrypto + key validation |

**Commercial deploy checklist residual:** set secrets, explicit CORS, rebuild vector collections with production embed model, enable/understand single-replica limit, set `RAG_ASK_BUDGET_SEC` for non-HTTP runners, decide remote vs local embeddings for capacity.

---

## 13. Backlog reality check

| Source | Claims | Audit view |
|---|---|---|
| `BACKLOG.md` / Autopilot queue | empty safe tasks | Consistent with code freeze on product features |
| AGENT_STATE (2026-06-16) | only open item = **dep-CVE** | **Still true** on lock pins |
| Adaptive-retrieval | closed NO-SHIP | Confirmed |
| Type-hardening | exhausted | Confirmed (strict scope covers prod packages) |
| Fable-hardening | empty | Not re-audited deep; no counter-evidence |
| commercial-upgrade-plan RQ-* | open | Partially obsolete (RAGAS exists offline); CI gate still open |

**Autonomous work safe candidates (priority order):**

1. Lock regen: aiohttp + cryptography (+ pip-audit green).  
2. Harden `test_api_namespace_is_populated` to OpenAPI paths (FastAPI-version proof).  
3. Document official RAGAS baseline + open precision workstream.  
4. Optional: RUF100 noqa cleanup.  
5. Optional: httpOnly cookie auth for admin UI (S1).  
**Do not:** flip factcard to default; enable multi-worker; silent broad refactors of graph.py.

---

## 14. Findings registry (2026-07-16)

### Critical / High

| ID | Sev | Area | Finding | Evidence | Remediation |
|---|---|---|---|---|---|
| **D1** | HIGH | deps | aiohttp 3.14.0 + cryptography 47.0.0 CVEs in lock | `requirements.lock`; AGENT_STATE 2026-06-16 | uv upgrade packages, regenerate hashes, verify pip-audit, PR |
| **Q1** | HIGH | RAG quality | context_precision ≈0.51; no CI quality floor | RAGAS report 2026-06-05; ci.yml regression informational | precision A/B + optional nightly RAGAS drift; later PR gate with mock/smoke floors |

### Medium

| ID | Sev | Area | Finding | Evidence | Remediation |
|---|---|---|---|---|---|
| **A1** | MED | architecture | Single worker/replica hard limit | Dockerfile, helm values, DEPLOYMENT.md | Explicit roadmap to externalize session/confirm/cache/CB before HPA |
| **S1** | MED | security | Bearer tokens in localStorage | `static/admin*.js`, `agent.inline.js` | Prefer httpOnly cookies (bridge middleware already exists) |
| **C1** | MED | maintainability | God-modules graph/app/settings/base_manager | LOC counts | Incremental node split; continue router extraction; settings grouping |
| **Q2** | MED | latency | Full graph on CPU+external can run minutes; budget opt-in default 0 | dogfood + `RAG_ASK_BUDGET_SEC` | Document recommended prod values; consider non-zero default for non-dev |
| **T1** | MED | tests | Route-count test fragile to FastAPI internals | fail on 0.138 flat routes vs OpenAPI 67 | Assert `len(app.openapi()["paths"])` / recursive walk |

### Low / Info

| ID | Sev | Finding | Note |
|---|---|---|---|
| **L1** | LOW | Silent `except: pass` ~65 outside tests | Prefer logger on retrieval/LLM critical paths |
| **L2** | LOW | mypy skip for api/vectordb | Accept until memory allows full graph |
| **L3** | LOW | Wide ruff debt (RUF100, etc.) | Incremental; RU unicode noise |
| **L4** | LOW | Bandit B608 false-positive class | Placeholders OK; keep review |
| **L5** | LOW | Blocking path ops in async | ASYNC240 ×4 |
| **I1** | INFO | 4 weeks no product commits | Healthy freeze vs bitrot of deps (D1) |
| **I2** | INFO | AGENT_STATE very large | Archive older START HERE blocks |
| **I3** | INFO | commercial-upgrade-plan stale vs RAGAS | Refresh checkboxes |
| **I4** | INFO | Chart.js from jsDelivr in CSP | Pin SRI if tightening trust boundary |

---

## 15. Scorecard

| Dimension | 03.06 (Claude) | **16.07 (Grok)** | Delta |
|---|---:|---:|---|
| Code / lint / types | 9.0 | **9.2** | +0.2 spawn_tracked, ruff ratchet, type-hardening done |
| RAG design | 9.0 | **9.1** | +0.1 factcard lane, remote embed, dogfood fixes |
| RAG proven quality | 6.5 | **7.4** | +0.9 RAGAS 100-case numbers exist; precision still weak; no CI gate |
| Security | 8.5 | **8.7** | +0.2 CSP; − residual D1 CVEs & localStorage |
| Architecture / complexity | 7.5 | **7.4** | −0.1 app still large; scale-out wall clearer |
| Tests | 8.0 | **8.2** | +0.2 more tests (826 fn); T1 fragility |
| Observability / ops | 9.8 | **9.8** | flat excellence |
| Process / evidence culture | 8.5 | **9.3** | Phase-5 NO-SHIP data discipline, dogfood→fixes |
| **Overall** | **8.8** | **8.9** | solid incremental maturation |

---

## 16. Remediation plan (ROI order)

### This week (must)

0. **D1** — lock bump `aiohttp` + `cryptography`, dual lock hashes, pip-audit green, push (CI security red is the only declared Windows backlog residue).  
1. **T1** — make namespace test OpenAPI-based (1h, prevents false red on FastAPI bump).

### This month

2. **Q1a** — publish RAGAS baseline in OPERATIONS/README; open precision-focused A/B (rerank_k / grade / window) against same 100 cases.  
3. **Q2** — recommend production `RAG_ASK_BUDGET_SEC` + provider read timeouts documentation; consider safer defaults for non-dev.  
4. **S1** — cookie-based admin session (optional product work).  
5. **L3** — RUF100 cleanup PR (auto-fix).

### Quarter

6. **Q1b** — nightly RAGAS/drift job (Helm cron pattern exists) + alert.  
7. **A1** — design doc for multi-replica: session store, confirm-actions, shared breaker/cache.  
8. **C1** — split `agent/graph.py` into `agent/nodes/*` without behavior change.  
9. Evaluate PR quality gate only after precision moves above ~0.7 and variance understood.

### Explicit non-goals (unless new data)

- Default-on factcard / auto-router.  
- GraphRAG on by default below corpus thresholds.  
- Multi-worker uvicorn without state externalization.  
- Broad “rewrite LangChain” initiatives.

---

## 17. Final verdict

**RAG_Support_Assistant is a strong, commercially close multi-tenant RAG platform** with unusually mature ops, security fail-fast, evaluation tooling, and evidence-driven ship/no-ship decisions. The June workstreams (type-hardening, adaptive-retrieval closure, dogfood fixes, docs-site E20) improved an already high baseline.

What keeps it from a clean 9.5+:

1. **Dependency bitrot (D1)** after a 4-week code freeze — fixable in one focused PR.  
2. **Retrieval precision / quality CI** — the product works, but precision ~0.5 and non-blocking eval mean regressions can merge quietly.  
3. **Scale-out architecture** — honest single-replica design is correct today, but is a hard commercial ceiling.  
4. **Module size** — operable, but expensive for new contributors.

**If only one thing is done after this audit:** clear **D1** (aiohttp + cryptography lock bump) and re-green security CI.  
**If only one product bet is made:** attack **context_precision** with measured A/B on the existing 100-case aircargo harness — not new retrieval strategies without data.

---

## 18. Appendix — commands & artifacts used

```text
HEAD:        0b0234c
ruff:        All checks passed
bandit:      0 high / 7 medium (B608/B310)
openapi:     71 paths (67 /api)
alembic:     17 revisions, head 017
tests:       826 test_* functions / 151 files
src LOC:     ~19k (bandit packages) / ~37k incl. scripts
locks:       aiohttp==3.14.0 cryptography==47.0.0 fastapi==0.136.1
RAGAS:       reports/ragas/20260605T214926Z-e728353a-aircargo-ragas.md
closure:     docs/operations/2026-06-14-adaptive-retrieval-closure.md
             docs/operations/2026-06-15-phase5-factcard-delta.md
dogfood:     FLANT_DOGFOOD_FINDINGS.md + commit 1343323
prior audit: docs/audits/audit_claude_03_06_26.md
```

**Environment caveat:** local Python 3.13 + unpinned global site-packages ≠ CI 3.11 lock. Treat local pytest/mypy anomalies as environment until reproduced under project lock.

---

*Аудит выполнен 2026-07-16. Результат записан в `audit_grok_16_07_26.md` (корень репозитория). Файл untracked до явного коммита владельцем.*

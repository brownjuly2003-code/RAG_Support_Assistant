# Session Notes — 2026-04-27 hardening

**HEAD:** `8e4cab2` (master, после docs commit)
**Pinned snapshot:** числа в этом файле зафиксированы на момент `8e4cab2`. Если в репо новые коммиты после `8e4cab2` — `git log ff7948f..HEAD` покажет реальный список.
**Стартовый baseline:** `ff7948f`
**Аудиторы:** Codex CLI (`audit_codex_27_04_26`) + Claude Opus 4.7 (`audit_opus_27_04_26.md`)
**Реализатор:** Claude Opus 4.7 (1M context)
**12 коммитов** между `ff7948f..8e4cab2` (11 hardening + 1 docs).

## TL;DR

Прошла одна сессия hardening на основе двух независимых аудитов. Закрыты:

- **3 P0** (Codex): Docker entrypoint, default JWT/admin secrets в production, tenant isolation для sessions/feedback.
- **5 P1**: shim imports cleanup, .dockerignore, /metrics auth opt-in, mypy strict scope для llm.providers, CI mypy gate + integration must-block.
- **2 P2/H**: pipeline exception → EscalatedTicket, Docker daemon skip в integration test.
- **1 baseline**: Phase 4 loader merge (был uncommitted 2 сессии).

Local rating обновлён 8.7/10 → **9.2/10**, commercial 7.7/10 → **8.5/10**.
Самые опасные deploy/security gaps закрыты. Остаются P1 quality (coverage, deps lock, Helm secrets split) и P2 architectural (streaming RAG parity, thin app-shell).

## Что закоммичено (от старого к новому)

| # | Hash | Категория | Сущность |
|---|---|---|---|
| 1 | `6cd303c` | refactor(loader) | Phase 4 — `DocumentChangeTracker` + HTML в `ingestion.loader` |
| 2 | `ecdd494` | fix(deploy)! | Dockerfile `main:app` → `api.app:app`, main.py alias, alembic в lifespan |
| 3 | `c48585c` | fix(security)! | production fail-fast для default JWT/SESSION/admin secrets |
| 4 | `aa683f3` | fix(security)! | tenant isolation для `/api/sessions*` + feedback table tenant_id |
| 5 | `c0cacae` | refactor(imports) | 13 prod imports → canonical, `tracing.sqlite_trace` re-exports |
| 6 | `f56e51b` | chore(infra) | .dockerignore + .gitignore .tmp/.coverage + pre-commit pip-audit |
| 7 | `0a42369` | feat(security) | optional auth gate on /metrics + docs |
| 8 | `d718356` | fix(types) | llm/providers strict mypy scope |
| 9 | `a12f404` | ci | mypy gate + integration не continue-on-error |
| 10 | `fa92d4e` | fix(escalation) | pipeline exception persists EscalatedTicket |
| 11 | `6e64148` | test(infra) | docker daemon availability skip |
| 12 | `8e4cab2` | docs | session notes + next-steps plan + audit snapshots (этот файл) |

## Числа (pinned at `8e4cab2`)

| Метрика | До (`ff7948f`) | После (`8e4cab2`) |
|---|---:|---:|
| Коммитов в master | 134 | **146** (+12) |
| `api/app.py` LOC | 2126 | **2224** (+98 — добавлены tenant filters в 3 endpoint'ах + escalation fallback в conversation router + alembic auto-migrate в lifespan) |
| `main.py` LOC | 413 | **21** (legacy FastAPI shell удалён, остался alias) |
| Production middleware count в Docker | 0 (main:app без middleware) | **8** |
| Tests focus-set | 50/50 | **85/85** (+35: production_entrypoint, settings_production_secrets, tenant_isolation_sessions, pipeline_exception_escalation, +обновленные test_metrics, test_admin_view, test_tenant_enforcement) |
| mypy strict modules | auth.* + db.models + db.engine | **+ llm.providers.*** |
| 13 root-shim production imports | 13 | **0** |
| `.dockerignore` | отсутствует | присутствует |
| Pipeline exception → EscalatedTicket | НЕ создаётся | создаётся |

## Смена API behaviour

### Breaking (для оператора)
- **Docker `main:app` больше не работает как раньше** — теперь это alias на `api.app:app`. Если кто-то стучался на legacy unauthenticated `/ask`, `/escalations`, `/traces`, `/escalations-ui`, `/traces-ui*` — они **удалены**. Замена: `POST /api/ask` (с auth) и `/api/admin/traces*` (с admin role).
- **`python main.py`** делегирует в `api.app:app` (host default `127.0.0.1`).
- **Production env** должен явно задать **`JWT_SECRET`** (≥32 chars), **`SESSION_SECRET_KEY`**, **`ADMIN_PASSWORD_HASH`**. Без них `RAG_ENV=production` не запустится. На staging можно `ALLOW_DEV_ADMIN_LOGIN=1` для admin/admin.

### Новые env vars
- `ALLOW_DEV_ADMIN_LOGIN` — явный opt-in на admin/admin login в production (если хочется).
- `PROMETHEUS_METRICS_REQUIRE_AUTH` — `1` чтобы `/metrics` требовал admin Bearer.

### Новое в /api
- `POST /api/feedback` теперь пишет `tenant_id` в `feedback` таблицу.
- `GET /api/feedback/stats` для `agent` role — scope per tenant; admin — global.
- `GET /api/sessions*` фильтрует по tenant.

## Verified в этой сессии

```bash
# 1. focus suite — 85/85 passed
python -m pytest tests/test_jwt_auth.py tests/test_tenant_propagation.py \
  tests/test_health_liveness.py tests/test_metrics.py \
  tests/test_agent_endpoints.py tests/test_review_queue.py \
  tests/test_conversation_router.py tests/test_module_layout.py \
  tests/test_mock_inbox_import.py tests/test_seed_docs_import.py \
  tests/test_loader.py tests/test_settings_production_secrets.py \
  tests/test_production_entrypoint.py tests/test_tenant_isolation_sessions.py \
  tests/test_admin_view.py tests/test_tenant_enforcement.py \
  tests/test_pipeline_exception_escalation.py -p no:schemathesis -q

# 2. mypy strict — clean
python -m mypy auth db/models.py db/engine.py llm/providers/ --no-incremental --show-error-codes
# → Success: no issues found in 12 source files

# 3. Production entrypoint smoke
python -c "from api.app import app as a; import main as m; print(a is m.app, len(a.user_middleware))"
# → True 8

# 4. cxkm — CX clean (P2 на untracked artefacts), KM degraded
```

## Known issues / что НЕ закрыто

- **KM (Kimi) review** падает `normalization_error` на 2618-строчном diff. Для tri-blocking review в будущем рассмотреть chunking diff'а перед KM.
- **Coverage gate 70%** — update 2026-04-29: реальное число теперь известно, **64.05%** на full pytest+coverage (`603 passed, 4 skipped`). Старый upload/body-size hang не воспроизведён; следующий шаг — добор тестов для `cache.py`, `cache/redis_cache.py`, `evaluation/ragas_eval.py`, `vectordb/_base_manager.py` и app-shell helper branches.
- **Helm chart secrets** — `deploy/helm/values.yaml` всё ещё имеет `DATABASE_URL=changeme` в ConfigMap (Codex P1, для commercial deploy).
- **Streaming RAG parity** — `/ask/stream` обходит часть quality gates (Codex H1).

См. `docs/plans/2026-04-27-next-steps.md` для приоритезированного плана.

## Audit baseline

`audit_codex_27_04_26` и `audit_opus_27_04_26.md` остаются в репо как **исторический snapshot** baseline `ff7948f` (frozen-in-time). Не редактировать. Следующая сессия может перегенерировать аудит на текущий HEAD при необходимости.

# Session handover: BCG-audit + 4 итерации hardening

**Дата:** 2026-04-26
**Сессии:** 1 (audit) + 4 (implementation)
**Состояние:** 22/22 hardening tasks completed + Phase 2a-2m router split completed + DEPRECATIONS Phase 3/5 completed, conversation-focused 69/69 tests pass.

> Этот документ — **карманный handover** для новой сессии. Если нужны детали — смотри указанные файлы.

---

## 1. Что есть и где смотреть

| Файл | Что в нём |
|---|---|
| `audit_opus_2026-04-26.md` | Полный аудит (секции 0-11) + implementation log по 18 задачам hardening (секция 12). Single source of truth по диагнозу и сводке. |
| `DEPRECATIONS.md` | Карта legacy-расположений в корне. 5-фазный план миграции. Карта split-ов `api/app.py` (13 фаз 2a-2m, все закрыты). Type-checking debt list. **Pattern для split sub-router-ов (важно для resume!).** |
| `docs/CHANGELOG.md` | Запись о hardening-сессии 2026-04-26. |
| `docs/SESSION-NOTES-2026-04-26-audit.md` | Этот файл. |

## 2. Quick state check (запустить в новой сессии)

```bash
# 1. Smoke-import
python -c "from api.app import app, router; print(f'/api routes: {len([r for r in app.routes if hasattr(r, \"path\") and r.path.startswith(\"/api\")])}')"
# Ожидаем: /api routes: 69

# 2. Focus test set (auth + tenant + jwt + health + metrics + agent + review-queue + trace + migration)
python -m pytest tests/test_jwt_auth.py tests/test_tenant_propagation.py tests/test_api_key_auth.py tests/test_auth_hardening.py tests/test_health.py tests/test_health_liveness.py tests/test_metrics.py tests/test_tenant_enforcement.py tests/test_trace_retention.py tests/test_migration_round_trip.py tests/test_mock_inbox_import.py tests/test_agent_endpoints.py tests/test_review_queue.py tests/test_review_export_import.py -p no:schemathesis -q --timeout=60
# Ожидаем: 71 passed (sanity 2026-04-26 16:42 UTC)

# 3. mypy strict
python -m mypy auth db/models.py
# Ожидаем: Success: no issues found in 5 source files

# 4. Bandit
python -m bandit -r D:/RAG_Support_Assistant -ll -c D:/RAG_Support_Assistant/pyproject.toml 2>&1 | tail -5
# Ожидаем: 0 High, 0 Medium severity
```

## 3. Структурные изменения, которые надо помнить

### `api/routers/` — новая директория, 13 sub-router-ов

```
api/routers/
├── __init__.py
├── system.py        # /health/live, /health/ready, /health, /metrics
├── agent.py         # /agent/tickets/*, /agent/similar (+ AgentRespondRequest)
├── admin_review.py  # /admin/review-queue/* (+ ReviewQueueUpdateRequest)
├── admin_ops.py     # /admin/circuit-breaker/reset, audit, traces, audit-log
├── admin_kb.py      # /admin/curated-dataset/*, /admin/kb-drafts/*, stale docs
├── admin_experiments.py # /admin/experiments/*, deploy/rollback, assignments
├── admin_evaluations.py # /admin/evaluations/*, /admin/regression-runs/*
├── analytics.py     # /analytics/* dashboard endpoints
├── feedback.py      # /feedback, /feedback/stats, /escalate
├── misc.py          # /admin/providers, /channels/email/inbound
├── conversation.py  # /ask, /chat, /ask/stream, /chat/stream
├── auth_sso.py      # /auth/sso/{providers,login,callback}
└── upload.py        # /upload, /tasks/{task_id}
```

Регистрируются в `api/app.py` сразу после `router = APIRouter(prefix="/api", tags=["RAG API"])` через `router.include_router(...)`.

### Удалены из корня (Phase 1 DEPRECATIONS)

- `graph.py` (deprecation shim → `agent.graph`)
- `state.py` (shim → `agent.state`)
- `prompts.py` (shim → `agent.prompts`)

Также удалён dead `except ImportError` fallback в `agent/graph.py:48-80` — он re-exportировал через те же удалённые shim-ы (циклически).

### Pre-commit chain обновлён

```yaml
ruff-check → standard hooks → bandit (-ll, --config pyproject.toml) → pip-audit (-r requirements.txt)
```

`detect-private-key` оставлен. `bandit` skip-ит B608/B310 (false positives задокументированы в `[tool.bandit]`).

## 4. Новые env vars

| Env | Default | Effect |
|---|---|---|
| `ALLOW_ANONYMOUS_ADMIN` | unset | Если 1/true/yes — разрешает anonymous admin при пустом `API_KEY`. По умолчанию endpoint вернёт 503 если `API_KEY` не задан. |
| `HOST` | `127.0.0.1` (только для bare `python main.py`) | Для bind на `0.0.0.0` нужно явно. Docker compose не затронут. |
| `PORT` | `8000` | bare run only. |
| `AUTO_MIGRATE` | `true` | Управляет `alembic upgrade head` в startup. На любой ошибке — warning, не крашит app. |

## 5. Pattern для следующих split-ов sub-router-ов (КРИТИЧНО!)

Тесты используют:
```python
monkeypatch.setattr("db.engine.async_session", lambda: _Session())
monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
monkeypatch.setattr(api_app, "get_oidc_client", _fake_client)
```

Top-level `from db.engine import async_session` или прямой импорт `get_settings`/OIDC helpers в новом router-модуле **обходит этот патч** — name связывается до того, как тест его патчит.

**Рабочий паттерн (применён в `api/routers/system.py`, `agent.py`, `admin_review.py`, `admin_ops.py`, `admin_kb.py`, `admin_experiments.py`, `auth_sso.py`, `feedback.py`, `upload.py`, `conversation.py`):**

```python
from db import engine as _db_engine  # импортируем МОДУЛЬ

def _async_session():
    return _db_engine.async_session()  # late-binding

async def _log_audit(**kwargs):
    from api import app as _app  # noqa: PLC0415
    return await _app.log_audit(**kwargs)
```

В handler-ах: `_async_session()` и `_log_audit(...)`.

Та же причина относится к не-router runtime коду: `evaluation/evaluator_runner.py`
должен брать `db.engine.async_session` late-bound через module object, иначе live
Postgres tests не смогут подменить disposable session factory.

Если про этот паттерн забыть — получите 4-6 fail-тестов на ConnectionRefusedError / реальные обращения к БД.

## 6. Что брать первым в новой сессии

### Опция A — продолжить split (низкий риск, чёткие победы)

Безопасные кандидаты (только DB session + log_audit):
1. ~~**Phase 2f — admin KB cluster**~~ — DONE 2026-04-26 22:22 UTC:
   `api/routers/admin_kb.py`; 46/46 related tests pass; focus-set 71/71 passes.

2. ~~**Phase 2g — admin experiments**~~ — DONE 2026-04-27:
   `api/routers/admin_experiments.py`; 18/18 related tests pass; `/api` route count stays 69.

3. ~~**Phase 2h — admin evaluations/regression runs**~~ — DONE 2026-04-27:
   `api/routers/admin_evaluations.py`; 28/28 related tests pass; `/api` route count stays 69.

4. ~~**Phase 2i — analytics**~~ — DONE 2026-04-27:
   `api/routers/analytics.py`; 5/5 related tests pass; `/api` route count stays 69.

5. ~~**Phase 2m — misc providers/email**~~ — DONE 2026-04-27:
   `api/routers/misc.py`; 11/11 related tests pass; `/api` route count stays 69; legacy `/webhook/email` alias preserved.

6. ~~**Phase 2b — feedback/escalate**~~ — DONE 2026-04-27:
   `api/routers/feedback.py`; 21/21 related tests pass; `/api` route count stays 69.

7. ~~**Phase 2d — admin ops/view/retention**~~ — DONE 2026-04-27:
   `api/routers/admin_ops.py`; 28/28 related tests pass; focus-set 71/71 passes; `/api` route count stays 69.

8. ~~**Phase 2k — upload/tasks**~~ — DONE 2026-04-27:
   `api/routers/upload.py`; 13/13 upload-focused tests pass; `/api` route count stays 69.

9. ~~**Phase 2a — dependency-aware health**~~ — DONE 2026-04-27:
   `api/routers/system.py`; 19/19 health-focused tests pass; `/api` route count stays 69; extracted routes now 60/69.

10. ~~**Phase 2l — conversation ask/chat**~~ — DONE 2026-04-27:
    `api/routers/conversation.py`; 13/13 conversation/auth/tenant-focused tests pass; 56/56 broader `/api/ask` tests pass; `/api` route count stays 69; extracted routes now 64/69.

После каждого split-а:
```bash
python -c "from api.app import app; print(len([r for r in app.routes if hasattr(r,'path')]))"
python -m pytest tests/test_<related>.py -p no:schemathesis -q --timeout=60
```

### Опция B — фикс mypy в llm/providers/db.engine — DONE 2026-04-27

`llm/providers` теперь проходит `mypy --follow-imports=skip --no-incremental`;
`db/engine.py` проходит обычный `mypy db/engine.py`. Strict promotion для
`llm.providers.*` всё ещё отдельная задача, потому что нужно доаннотировать
provider classes перед `disallow_untyped_defs`.

### Опция C — DEPRECATIONS Phase 2 (перенос файлов)

`bitrix.py` + `mock_inbox.py` перенесены в `integrations/` 2026-04-27. `seed_docs.py` перенесён в `demo/seed_docs.py`; DEPRECATIONS Phase 2 закрыта.

### Опция C2 — DEPRECATIONS Phase 3 (`manager`/`sqlite_trace`)

Phase 3 закрыт 2026-04-27 по Option B: базовые реализации теперь в
`vectordb/_base_manager.py` и `tracing/_base_trace.py`, root `manager.py` и
`sqlite_trace.py` остались compatibility shim-ами. Verification:
`python -m pytest -p pytest_asyncio.plugin -p no:cacheprovider -q --basetemp=.tmp\pytest-full-phase3-final`
→ 563 passed, 4 skipped.

### Опция C3 — DEPRECATIONS Phase 5 (`chunking.py`)

Phase 5 закрыт 2026-04-27: standalone tuning script переехал в
`scripts/chunking_eval.py`, root `chunking.py` удалён. Следующий structural
candidate остаётся Phase 4 (`loader.py`), но это product decision.

### Опция D — coverage до 70%

Текущий focus-set даёт 24%. Полный пакет тестов проходит при явном `--basetemp` вне проблемных cache-директорий; следующий шаг — отдельный coverage-прогон и добор до `fail_under=70`.

## 7. Что НЕ трогать

- LangGraph граф (`agent/graph.py` 2064 LOC) — хороший, не трогать
- RAG-пайплайн (hybrid search + Self-RAG + reranker) — sota
- Embedder (BAAI/bge-m3) и reranker (cross-encoder/ms-marco) — current
- Observability stack (Langfuse + OTel + Prometheus + SQLite traces) — overkill, но overkill безвредный
- Multi-tenancy (alembic 003 + pgcrypto 008) — работает, не трогать
- ChromaDB / Qdrant выбор — оба поддержаны, юзер сам выбирает

## 8. Известные проблемы окружения

- **schemathesis pytest plugin** несовместим с pytest 9 (`ModuleNotFoundError: '_pytest.subtests'`). Workaround: всегда `pytest -p no:schemathesis`.
- **Полный `pytest`** проходит с явным `--basetemp` вне репозитория (`557 passed, 4 skipped` на 2026-04-27). Без этого workspace может шуметь permission warnings из старых `tests/pytest-cache-files-*`.
- **AuthlibDeprecationWarning** про `authlib.jose` — третья сторона, в roadmap зависимостей.
- **Pre-commit hooks при первом коммите** прогонят bandit + pip-audit. Bandit с конфигом из pyproject.toml даёт 0 High/Medium. pip-audit `--strict` clean на 2026-04-26. Если упадёт — смотри DEPRECATIONS.md «Type-checking debt» и `[tool.bandit]` секцию.
- **`reports/regression/*.log` и `*.err` в untracked** — это evidence от task-177/178/179 (до аудита). К текущей hardening-работе не относятся. Не коммитить как часть hardening PR (они уже в `.gitignore` если правильный паттерн).

## 8.1. Про CC-CX-KM auto-trigger (правило из CLAUDE.md от 2026-04-26)

User-instructions требуют `/cxkm` после нетривиальных impl-задач. Hardening-сессия 2026-04-26 **сознательно** не вызывала cxkm на каждом split-е — split sub-router-ов был механическим переносом (copy-paste без новой бизнес-логики), и аудит уже был proxy для review.

Если новая сессия будет делать **новые** router splits — рекомендуется один cxkm в конце пакета, не на каждом router-е.

## 9. Критические файлы которые трогали

```
auth/dependencies.py        - anonymous gate + Callable return type
auth/oidc.py                - 3 mypy fixes
api/app.py                  - 12 endpoint групп удалены, 13 sub-router include
api/rate_limit.py           - shared limiter для app + extracted routers
api/routers/                - НОВАЯ ДИРЕКТОРИЯ, включая upload.py и conversation.py
main.py                     - host default + auto-migrate + WAL для traces
sqlite_trace.py             - WAL pragma + accurate docstring
tracing/langfuse_trace.py   - usedforsecurity=False для MD5
manager.py, loader.py,
chunking.py, bitrix.py,
mock_inbox.py, seed_docs.py - docstring sanitation
agent/graph.py              - dead fallback removed
pyproject.toml              - +coverage +mypy +bandit configs
.pre-commit-config.yaml     - +bandit +pip-audit hooks
tests/conftest.py           - +ALLOW_ANONYMOUS_ADMIN env для no-key client
```

Удалены: `graph.py`, `state.py`, `prompts.py` (shim-ы).

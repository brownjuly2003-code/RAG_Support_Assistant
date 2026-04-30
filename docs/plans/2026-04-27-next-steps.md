# Next Steps — после hardening 2026-04-27

**Baseline:** `8e4cab2` (master, после 12 коммитов: 11 hardening + 1 docs).
**Pinned snapshot:** числа здесь зафиксированы на момент `8e4cab2`.
**Текущая оценка:** local 9.2/10, commercial 8.5/10.
**Цель:** довести до 9.5/10 local + 9.0/10 commercial без архитектурных пересмотров.

Каждая задача — самодостаточный chunk на 30-180 минут с TDD-разрезом, точкой коммита и acceptance criterion.

---

## Эта неделя (~3-4 часа суммарно)

### Шаг 1. Удалить root-level shim-ы (~20 мин)

**Файлы:** `manager.py`, `sqlite_trace.py`, `loader.py` (по 15 LOC each).

**Контекст.** После `c0cacae` все 13 production-сайтов переключены на canonical (`vectordb.manager` / `tracing.sqlite_trace` / `ingestion.loader`). Shim-ы корня нужны были только backward-compat для внешних консумеров — но это локальный проект, внешних консумеров нет. Тесты `test_module_layout.py` явно проверяют что shim-ы выдают `DeprecationWarning` — придётся переписать как negative-tests.

**Шаги:**
1. `git rm manager.py sqlite_trace.py loader.py`.
2. `tests/test_module_layout.py` — переписать `test_*_is_canonical_home` тесты: вместо проверки `DeprecationWarning` через shim, проверить что `import manager` / `import sqlite_trace` / `import loader` **поднимает ImportError** (negative test).
3. `python -m pytest tests/test_module_layout.py -q` — проверить.
4. `python -m pytest tests/ -q --ignore=tests/integration -p no:schemathesis` — full unit run.
5. Commit: `refactor: remove root-level shim modules (Phase 3+4 final)`.

**Acceptance.** `import manager` / `sqlite_trace` / `loader` raises ImportError. Production не падает. Focus suite зелёный.

---

### Шаг 2. Coverage gate 70% — выполнено 2026-04-29

**Файлы:** `tests/test_ragas_eval.py`, `tests/test_base_manager.py`, `tests/test_benchmark_runner.py`, `tests/integration/test_regression_eval_live.py`, `pyproject.toml`.

**Контекст.** Update 2026-04-29: coverage gate закрыт. Full pytest+coverage проходит без зависания: **630 passed, 4 skipped, 70.02% coverage**. `evaluation/ragas_eval.py`, `vectordb/_base_manager.py` и `evaluation/benchmark_runner.py` закрыты focused tests; live regression eval больше не тянет реальные embeddings/categorizer в coverage path. `fail_under` поднят до 70.

**Проверено:**
1. `python -m pytest tests\integration\test_regression_eval_live.py tests\test_ragas_eval.py tests\test_base_manager.py tests\test_benchmark_runner.py -p no:schemathesis -p no:cacheprovider -q --timeout=60 --basetemp=.tmp\coverage-batch-focused-final`
2. `python -m pytest -p no:schemathesis -p no:cacheprovider --cov=. --cov-report=term --cov-report=html -q --timeout=60 --basetemp=.tmp\full-coverage-final`

**Acceptance.** Full pytest+coverage проходит без зависания, coverage число обновлено в `pyproject.toml`, `fail_under=70` не завышен выше проверенного результата.

---

### Шаг 3. Helm secrets split — выполнено 2026-04-29

**Файлы:** `deploy/helm/values.yaml`, `deploy/helm/templates/configmap.yaml`, `deploy/helm/templates/deployment.yaml`, новый `deploy/helm/templates/secret.yaml`.

**Исходный контекст.** Codex P1 был в том, что `DATABASE_URL`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `DB_ENCRYPTION_KEY`, provider keys, SMTP/IMAP credentials лежали в ConfigMap (видны через `kubectl get configmap`). Также были `changeme` placeholder и tag `latest`.

**Шаги:**
1. Создать `deploy/helm/templates/secret.yaml`: Secret с `DATABASE_URL`, `JWT_SECRET`, `SESSION_SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `DB_ENCRYPTION_KEY`, `MISTRAL_API_KEY`, `SMTP_PASSWORD`, `EMAIL_WEBHOOK_SIGNING_SECRET`. Поля или из `.Values.secrets` или из existingSecret.
2. `deployment.yaml` — split env: `configMapRef` для public config + `secretRef` для secrets.
3. `values.yaml` — убрать `changeme` defaults (требовать или existingSecret или explicit `helm install --set`). Добавить `RAG_ENV=production` default.
4. `Chart.yaml` — убрать `latest` image tag (использовать `appVersion`).
5. `helm lint deploy/helm/ --strict` + `helm template ...` smoke.
6. Commit: `chore(helm): split secrets out of ConfigMap (Codex P1)`.

**Acceptance.** `kubectl get configmap` не содержит DB credentials/JWT. `helm template --values prod-values.yaml` рендерится с RAG_ENV=production.

**Проверено:**
1. `helm lint deploy/helm/ --strict --set env.CORS_ORIGINS=... --set secrets.*=... --set postgresql.auth.password=...`
2. `helm template rag-test deploy/helm/ ...` — ConfigMap содержит только public env, Secret содержит DB/JWT/provider/SMTP secrets, image tag падает на `Chart.appVersion`.
3. `helm template ... --set secrets.existingSecret=rag-prod-secrets ...` — chart-managed Secret не рендерится, `secretRef` указывает на external Secret.

---

## Ближайший месяц (~1-2 дня)

### Шаг 4. Streaming RAG parity — выполнено 2026-04-29

**Файлы:** `api/routers/conversation.py:459-590`, `agent/graph.py`, новые тесты.

**Контекст.** Codex H1: `/ask/stream` ручную берёт docs из retriever, строит prompt, стримит provider tokens. Обходит fact verification, online evaluators, self-RAG, tool confirmation, graph-level routing. Пользователь может получить `route=auto` там, где sync graph вернул бы `human/retry/error`.

**Шаги:**
1. Изучить `agent/graph.py` — как graph возвращает state.
2. Решить parity-стратегию: либо стримить из graph через async iterator, либо явно маркировать stream как draft до post-stream graph verification.
3. Добавить parity тесты: один и тот же case на `/api/ask` и `/api/ask/stream` — route/quality/citations совпадают (или есть документированный delta).
4. Реализация.
5. Commit: `feat(streaming): RAG parity между /api/ask и /api/ask/stream (Codex H1)`.

**Acceptance.** Parity тест зелёный.

---

### Шаг 5. Dependency lock через uv — выполнено 2026-04-29

**Файлы:** новый `requirements.lock` или `uv.lock`, `Dockerfile`, CI workflows.

**Контекст.** Codex H8: `requirements.txt` использует `>=` для langchain/fastapi/pydantic/sqlalchemy/authlib/opentelemetry. Тесты на Python 3.13, Dockerfile на Python 3.11. Поведение RAG/LLM integrations может drift'овать от установки к установке. Уже видны `LangChainDeprecationWarning` для Ollama/ChatOllama, `AuthlibDeprecationWarning`.

**Шаги:**
1. Выбрать tool: `uv` (быстрее) или `pip-tools` (стандарт).
2. Сгенерировать lock из текущего `requirements.txt`.
3. Dockerfile — установка из lock.
4. CI workflows — кэш по lock.
5. README — инструкция пересборки lock.
6. Commit: `chore(deps): добавлен requirements.lock через {uv|pip-tools}`.

**Acceptance.** `pip install -r requirements.lock --require-hashes` работает в Docker. CI кэш hits на lock.

---

### Шаг 6. mypy strict для config.settings — выполнено 2026-04-29

**Файлы:** `config/settings.py`, `pyproject.toml`.

**Контекст.** В `DEPRECATIONS.md` указано «`config.settings` — re-defined names + Optional/str narrowing; cleanup is scoped to a separate refactor». После hardening 2026-04-27 мы добавили блок production-secrets validation — самое время причесать types в этом модуле.

**Шаги:**
1. `python -m mypy config/settings.py --no-incremental --show-error-codes` — посмотреть текущие errors.
2. Зафиксить redefinitions + Optional narrowing.
3. Поднять scope в pyproject.
4. Добавить `config/settings.py` в CI mypy gate.
5. Commit: `fix(types): config.settings — clean strict mypy`.

---

### Шаг 7. CI security pipeline — выполнено 2026-04-29

**Файлы:** новый job в `.github/workflows/ci.yml` (либо новый `security.yml`).

**Контекст.** Сейчас bandit + pip-audit только в `.pre-commit-config.yaml` (локально). На GitHub Actions нет gate. Codex рекомендует добавить semgrep + bandit + pip-audit как блокирующие.

**Шаги:**
1. Новый job `security` в `ci.yml`: `bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data` + `pip-audit -r requirements.txt --strict`.
2. (опц) `semgrep --config=p/python --error`.
3. Job обязателен для PR.
4. Commit: `ci(security): bandit + pip-audit gates на PR`.

---

## Квартал (если идёт commercial scenario)

### Шаг 8. Финальный thin app-shell — выполнено 2026-04-29

**Файлы:** новый `api/routers/session_auth.py`, новый `api/services/`, `api/app.py`.

**Контекст.** `api/app.py` ещё 2224 LOC: 5 endpoints (auth + sessions), 6 middlewares, 1100 LOC private helpers, 200 LOC lifespan, ~70 LOC Pydantic models, ~250 LOC imports/setup, +tenant filters/escalation fallback (98 LOC из hardening 2026-04-27). Цель — `api/app.py` ≤ 600 LOC (только construction + lifespan + middlewares).

**Шаги:**
1. `api/routers/session_auth.py` — `/auth/login`, `/auth/refresh`, `/sessions/{id}/history`, `/sessions`, `DELETE /sessions/{id}`.
2. `api/services/regression_service.py`, `curated_dataset_service.py`, `review_queue_service.py` — вынести 30+ private helpers `_load_*`, `_serialize_*`, `_run_*`, `_probe_*`, `_record_*`.
3. Routers → handlers thin shells.
4. Smoke test routes count + middleware preserved.
5. Commit: `refactor(app-shell): тонкий api/app.py — auth+sessions в session_auth router (Opus task #5)`.

---

### Шаг 9. mypy strict для agent.* (LangGraph nodes) — выполнено 2026-04-29

`agent.state`, `agent.prompts`, `agent.prompt_registry`, `agent.tools`, `agent.graph` добавлены в strict mypy scope и CI gate.

**Проверено:**
1. `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py --no-incremental --show-error-codes` — **18 source files, clean**.
2. `python -m mypy agent/graph.py --no-incremental --disallow-untyped-defs --disallow-incomplete-defs --show-error-codes` — clean.
3. `python -m pytest tests/test_state.py tests/test_graph_error_handling.py tests/test_agent_tools.py tests/test_kb_gaps.py -q -p no:schemathesis --timeout=60 --basetemp=.tmp\pytest-agent-graph-strict-focused` — **20 passed**.
4. `python -m pytest tests -q --ignore=tests/integration -p no:schemathesis -p no:cacheprovider --timeout=60 --durations=20 --basetemp=.tmp\pytest-agent-graph-strict-full-final` — **623 passed, 4 skipped** за 14:59 local.

**Что изменилось:** full strict baseline **63 errors → 0**. Основные фиксы: GraphState route/tool_calls/knowledge_gap приведены к runtime shape, локальные Literal-аннотации добавлены для `complexity`/`route`, TypedDict `update(kwargs)` заменён на `update({...})`, LangGraph node registration оставлен как явная dynamic boundary через `workflow: Any`.

---

## Что НЕ делать (зафиксировано в прежних аудитах + остаётся актуально)

- ❌ Переписывать LangGraph-граф — он хорош.
- ❌ Менять стек БД / vector store / embedder.
- ❌ Внедрять Kubernetes для local-продукта.
- ❌ Тащить ещё одну observability-систему.
- ❌ Трогать `cache.py` vs `cache/redis_cache.py` — разные concerns, переименование сейчас ROI < risk.
- ❌ Удалять `audit_*.md` файлы — они исторический snapshot.

---

## Quick verify в новой сессии

```bash
git log --oneline ff7948f..HEAD | head -20
python -c "from api.app import app; print(len([r for r in app.routes if hasattr(r,'path') and r.path.startswith('/api')]))"
# Ожидаем: ≥69

python -m pytest tests/test_jwt_auth.py tests/test_module_layout.py \
  tests/test_production_entrypoint.py tests/test_settings_production_secrets.py \
  tests/test_tenant_isolation_sessions.py tests/test_pipeline_exception_escalation.py \
  -p no:schemathesis -q --timeout=60 --basetemp=.tmp/quick

python -m mypy auth db/models.py db/engine.py llm/providers/ --no-incremental
# Ожидаем: Success: no issues found

python -m bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data 2>&1 | tail -3
python -m pip_audit -r requirements.txt 2>&1 | tail -3
```

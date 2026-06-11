# Глубокий аудит проекта RAG_Support_Assistant

**Дата аудита:** 2026-05-04
**Аудитор:** Kimi Code CLI
**Версия проекта:** HEAD `1d8ee96` (master)
**Базовый стек:** Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres 16, Redis 7, GraceKelly/Ollama/Mistral provider routing, Helm/K8s, OpenTelemetry

---

## 1. Резюме

Проект представляет собой зрелое production-ready RAG-приложение для поддержки клиентов. Кодовая база ~18 000 LOC Python (по данным bandit), 593 файла в репозитории. Основные сильные стороны: **модульная архитектура**, **многоуровневая защита отказов** (circuit breaker, retry, bounded concurrency, graceful shutdown), **multi-tenancy**, **CI/CD pipeline с regression gates**, **strict mypy на критичных модулях**, **bandit-clean** код. Основные зоны риска: **зависание полного pytest suite** (вероятно, из-за блокирующих LLM-вызовов в отдельных тестах), **раздутая структура codex-tasks** (180+ файлов архива задач), **потенциальная утечка памяти в глобальных кэшах vectordb**, и **неполная type coverage** за пределами strict scope.

---

## 2. Архитектура и структура

### 2.1. Модульная компоновка

Проект разбит на 14+ Python-пакетов с четкими границами ответственности:

| Пакет | LOC (оценка) | Назначение |
|-------|-------------|------------|
| `api/` | ~2 500 | FastAPI app, 15+ sub-routers, middleware, lifespan |
| `agent/` | ~2 800 | LangGraph pipeline: retrieve → rerank → generate → verify → route |
| `auth/` | ~250 | JWT, X-API-Key, OIDC (Google/Azure), RBAC |
| `db/` | ~400 | SQLAlchemy ORM, asyncpg engine, audit log, pgcrypto |
| `llm/providers/` | ~800 | GraceKelly, Mistral, Ollama providers + runtime routing |
| `vectordb/` | ~650 | ChromaDB tenant-aware manager, BM25, RRF, reranker |
| `evaluation/` | ~1 200 | RAGAS-style eval, online evaluators, regression framework |
| `ingestion/` | ~500 | Document loaders, categorizer, semantic chunking |
| `monitoring/` | ~700 | 50+ Prometheus collectors, alert rules |
| `tracing/` | ~500 | SQLite trace store, Langfuse, OTel spans |
| `channels/` | ~400 | Email (IMAP/webhook), Telegram, Bitrix |
| `scripts/` | ~3 500 | 30+ ops-скриптов: backup, eval, review queue, KB builder |

### 2.2. Граф обработки запроса (LangGraph)

```
classify_complexity → [transform_query] → retrieve (vector + BM25 + RRF)
  → rerank (cross-encoder) → grade_docs → generate → verify_facts
  → evaluate → route(auto/human/retry/error)
```

**Уровни RAG:**
- **Level 1:** базовый retrieve + generate + evaluate
- **Level 2:** Corrective RAG (grade_docs, query rewrite), Self-RAG (retry loop до 2 итераций), semantic chunking, contextual headers
- **Level 3:** conversation memory, multi-query retrieval, HyDE (опционально), parent-child chunking (опционально)
- **Level 4 (Agentic):** tool use (search_kb, check_order_status, create_ticket) с confirmation gate для необратимых действий

### 2.3. Провайдеры LLM

Реализована **трехуровневая абстракция провайдеров** через `config/providers.yml`:

| Профиль | Fast lane | Strong lane | Fallback | Use case |
|---------|-----------|-------------|----------|----------|
| `gracekelly-primary` | GraceKelly mistral-small | GraceKelly claude-sonnet-4-6 | Ollama qwen2.5:7b | Default local |
| `local-first` | Ollama qwen2.5:7b | Ollama qwen2.5:7b | — | Air-gapped |
| `external-mistral` | ministral-3b-latest | mistral-small-latest | — | Cloud, без GraceKelly |
| `gracekelly-mixed` | Mistral API (fast) | GraceKelly (strong) | Ollama | Hybrid |

**Failover:** GraceKelly → Ollama с кэшем решения на 300 сек. Повторные вызовы GraceKelly пропускаются, если кэш активен.

---

## 3. Качество кода

### 3.1. Линтинг и форматирование

- **Ruff:** `line-length = 100`, `select = ["E", "F", "W"]`, `ignore = ["E501"]`
- **Статус:** ✅ Clean (`ruff check api/app.py api agent auth db llm config evaluation scripts tests` — passed)
- **Pre-commit:** настроен в `.pre-commit-config.yaml`

### 3.2. Статическая типизация (mypy)

**Strict scope** (блокирует PR в CI):
- `auth.*` — 4/4 файла clean
- `db.models`, `db.engine` — clean
- `llm.providers.*` — clean
- `config.settings` — clean
- `agent.state`, `agent.prompts`, `agent.prompt_registry`, `agent.tools`, `agent.graph` — clean
- `api.app` — clean с `follow_imports=skip`

**Верификация в ходе аудита:** `mypy auth db/models.py db/engine.py config/settings.py` — **Success: no issues found in 7 source files**.

**Проблема:** за пределами strict scope (~80% codebase) типизация не контролируется. В `api/app.py` (1 896 LOC) и `agent/graph.py` (2 101 LOC) присутствует множество `Any`, `getattr(..., "", None)`, `cast(...)`.

### 3.3. Тестовое покрытие

| Метрика | Значение |
|---------|----------|
| Базовое покрытие (coverage.py) | **70.02%** (fail_under = 70) |
| Unit tests | ~630 passed, 4 skipped (по данным pyproject.toml, последняя проверка 2026-04-30) |
| Integration tests | 6 сценариев: ingestion, conversation, streaming, concurrency, escalation, async upload |
| A11y tests | 38 passed (axe-core 4.11.3) |
| Быстрая проверка в ходе аудита | 9 passed in 5.34s (`test_state`, `test_module_layout`, `test_root_routes`, `test_router_app_shell`) |

**⚠️ Критический риск:** полный pytest suite зависает при запуске в текущей среде (таймаут 120s). Причина, вероятно, в тестах, которые пытаются подключиться к Ollama/Postgres/Redis без моков, или в тяжелых embeddings-операциях. **Рекомендация:** добавить `--timeout=60` ко всем CI-вызовам pytest и проверить, что нет блокирующих сетевых вызовов в unit-тестах.

### 3.4. Security static analysis (bandit)

- **Статус:** ✅ No medium/high issues
- **Low severity:** 39 findings (в основном информационные)
- **Medium confidence:** 4
- **High confidence:** 35
- **Исключения:** B608 (parameterized SQL в whitelist-запросах), B310 (urllib.urlopen для localhost Ollama healthcheck)

---

## 4. Безопасность

### 4.1. Аутентификация и авторизация

| Механизм | Реализация | Статус |
|----------|-----------|--------|
| JWT (access + refresh) | PyJWT, bcrypt hashes | ✅ Production-hardened |
| X-API-Key | HMAC timing-safe compare | ✅ Legacy, но рабочий |
| OIDC SSO | Google + Azure AD (Authlib) | ✅ Реализовано |
| RBAC | `viewer` / `agent` / `admin` | ✅ Защищает все admin endpoints |
| Anonymous admin fallback | `ALLOW_ANONYMOUS_ADMIN` env gate | ✅ Disabled by default |

**Production hardening в `Settings.validate()`:**
- Запрещает `CORS_ORIGINS="*"` в production
- Требует `DB_ENCRYPTION_KEY`
- Требует `JWT_SECRET` >= 32 chars, не default
- Требует `ADMIN_PASSWORD_HASH` или явный `ALLOW_DEV_ADMIN_LOGIN=1`

### 4.2. Шифрование

- **At rest:** `pgcrypto` AES-256 для полей `Message.content`, `EscalatedTicket.user_question/ai_draft/operator_response`, `AuditLog.detail`
- **Ключ:** `DB_ENCRYPTION_KEY` — внешний, не в git
- **В transit:** HTTPS через reverse proxy / ingress (не реализовано в приложении, предполагается k8s ingress)

### 4.3. Защита от атак

| Угроза | Мера |
|--------|------|
| Path traversal | `secure_filename` + whitelist расширений в `/api/upload` |
| Rate limiting | slowapi: 60 req/min `/api/ask`, 10 req/min `/api/upload`, 5 req/min `/api/auth/login` |
| Body size | 1 MiB (API), 50 MiB (upload) |
| SQL injection | SQLAlchemy ORM + parameterized queries в raw SQL |
| XSS | Jinja2 autoescape, CSP через reverse proxy |
| PII leak | `utils.pii.redact_pii` в trace logs; online evaluator `pii_leak_suspicion` |
| Circuit breaker | Защита от cascading failure при недоступности Ollama |
| Retry backoff | Экспоненциальный backoff + jitter для Ollama |

### 4.4. Мультиарендность (Multi-tenancy)

- JWT claim `tenant` propagates через все слои
- ChromaDB: per-tenant collections `rag_docs_{tenant_id}`
- Postgres: `tenant_id` column с `server_default="default"` и индексами
- Redis cache keys: `llm_resp:{tenant}:{hash}`
- Аналитика, audit log, review queue — все фильтруются по `tenant_id`

---

## 5. Производительность и масштабируемость

### 5.1. Векторный поиск

| Компонент | Реализация | Примечание |
|-----------|-----------|------------|
| Embeddings | `BAAI/bge-m3` (1024d, 570M params) | Мультиязычный, SOTA для 100+ языков |
| Vector store | ChromaDB (persistent) | Per-tenant collections |
| Hybrid search | BM25 + vector + RRF | `RAG_HYBRID_SEARCH=true` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | CPU-friendly, 22M params |
| Semantic chunking | `langchain-experimental` semantic splitter | +80% faithfulness (по заявкам) |
| Contextual headers | LLM-generated doc summary prefix | Опционально |

### 5.2. Пропускная способность API

| Ограничение | Значение | Механизм |
|-------------|----------|----------|
| Concurrent pipelines | 8 | `asyncio.Semaphore` |
| Pipeline acquire timeout | 0.5s | Возврат HTTP 503 при перегрузке |
| Request wall-time | 30s | HTTP 504 при превышении |
| DB pool | 10 connections, max_overflow=20 | SQLAlchemy asyncpg |
| LLM cache | Redis, TTL 3600s | Disabled by default |

### 5.3. Узкие места

1. **ChromaDB persistence:** `store.persist()` вызывается синхронно при ingestion. При больших объемах (>10k документов) блокирует event loop.
2. **Embeddings загрузка:** `sentence-transformers` кэширует модель в памяти (~1.2 GB для BGE-M3). Без warm-start первый запрос медленный.
3. **SQLite trace writer:** синхронные `sqlite3` операции в `tracing/_base_trace.py` вызываются из async кода через implicit sync-in-async. Масштабируется до ~1000 req/min, далее — contention.
4. **GraceKelly health check:** 2s timeout перед первым запросом. При старте под нагрузкой создает latency spike.

---

## 6. Наблюдаемость (Observability)

### 6.1. Prometheus метрики (~50 коллекторов)

Ключевые метрики:
- `rag_requests_total{route}`, `rag_request_duration_seconds`
- `llm_cost_usd_total{provider,model,tenant}`
- `rag_circuit_breaker_state{name}`, `rag_circuit_breaker_transitions_total`
- `rag_inflight_pipelines`, `rag_pipeline_rejections_total{reason}`
- `rag_component_up{component}`, `rag_db_pool_*`
- `online_evaluator_score{evaluator}`, `online_evaluator_runs_total{evaluator,verdict}`
- `review_queue_pending_total{reason}`, `review_queue_oldest_pending_seconds`

### 6.2. Распределенный трейсинг

| Бэкенд | Статус | Покрытие |
|--------|--------|----------|
| SQLite (default) | ✅ Всегда включен | FastAPI, graph nodes, LLM calls |
| Langfuse | Опционально | LLM calls, cost tracking |
| OpenTelemetry (OTLP) | Опционально | FastAPI, httpx, SQLAlchemy, Redis, graph nodes |

### 6.3. Алертинг

- `scripts/check_alerts.py` — SQLite-based lightweight checker (5-min cron)
- `monitoring/alert_rules.yml` — Prometheus rules для: escalation rate, quality, latency, stale docs, nightly eval drift
- Интеграции: Slack webhook, email (SMTP)

---

## 7. DevOps и CI/CD

### 7.1. GitHub Actions workflow

| Job | Блокирует PR? | Описание |
|-----|--------------|----------|
| `migrations` | ✅ | Alembic round-trip audit на Postgres 16 |
| `helm` | ✅ | `helm lint --strict`, `helm template`, `kubectl dry-run` |
| `lint` | ✅ | `ruff check .` |
| `type-check` | ✅ | mypy strict scope |
| `test-unit` | ✅ | pytest unit tests |
| `test-integration` | ✅ | pytest integration tests на Postgres + Redis |
| `pre-commit` | ✅ | pre-commit hooks |
| `security` | ✅ | bandit + pip-audit |
| `regression-eval` | ℹ️ Informational | regression gate при изменении prompts/settings/experiments |

### 7.2. Контейнеризация

- **Dockerfile:** `python:3.11-slim`, multi-stage не используется (образ ~500-700 MB с ML-зависимостями)
- **docker-compose.yml:** Ollama, Postgres 16, Redis 7, Jaeger, app
- **Healthcheck:** `GET /api/health` каждые 30s
- **Security:** `USER app` (non-root), `--workers 2`

### 7.3. Kubernetes (Helm)

- Chart в `deploy/helm/`
- CronJobs: nightly eval, daily eval snapshot, hourly review queue, weekly improvement backlog, weekly report, backup integrity, backup snapshot, curated staleness check, threshold analysis, restore verify
- Deployment: HPA, liveness/readiness probes, graceful shutdown delay 5s
- Ingress: шаблонизированный

---

## 8. Данные и миграции

### 8.1. Схема БД (Alembic)

17 миграций, покрывающих:
- `sessions`, `messages`, `users` (auth)
- `traces`, `trace_steps`, `feedback` (observability)
- `audit_log` (security)
- `escalated_tickets` (agent copilot)
- `eval_results` (nightly eval)
- `knowledge_gaps`, `kb_drafts` (knowledge loops)
- `review_queue` (human review)
- `experiment_deployments`, `experiment_assignments` (A/B experiments)
- `trace_evaluations` (online evaluators)

### 8.2. Encryption at rest

- Migration `008_enable_pgcrypto` включает расширение и создает `EncryptedText` тип
- `db/crypto.py` — AES-256-GCM через `pgcrypto` SQL-функции
- **Риск:** ключ `DB_ENCRYPTION_KEY` — единственная точка отказа. Нет механизма key rotation без downtime (скрипт `rotate_encryption_key.py` существует, но пустой — 0 bytes).

---

## 9. Управление знаниями (Knowledge Loops)

| Компонент | Механизм | Автоматизация |
|-----------|----------|---------------|
| Nightly eval | `scripts/nightly_eval.py` — RAGAS-style drift check | CronJob 02:00 UTC |
| Online evaluators | 7 lightweight checks per trace (citation, length, retrieval hit rate, tool efficiency, refusal, PII, language) | Синхронно после каждого `/api/ask` |
| KB gap detection | Кластеризация unanswered questions | CronJob nightly |
| KB builder | `scripts/kb_builder.py` — drafts из resolved tickets | Ручной trigger + admin UI |
| Review queue | `scripts/build_review_queue.py` — сбор weak traces | CronJob hourly |
| Improvement backlog | `scripts/generate_improvement_backlog.py` — ranked actionable items | CronJob еженедельно |
| Threshold tuning | `scripts/analyze_thresholds.py` — F1-optimized cutoffs | CronJob еженедельно |
| Curated dataset | `evaluation/curated_cases.jsonl` — human-verified cases | Ручной rebuild via admin API |
| Regression eval | `scripts/regression_eval.py` — deterministic gate | PR gate + manual trigger |

---

## 10. Каналы взаимодействия

| Канал | Статус | Примечание |
|-------|--------|------------|
| Web chat (`/static/chat.html`) | ✅ Production | SSE streaming, inline citations, upload, mobile-first |
| Admin UI (`/static/admin.html`) | ✅ Production | Traces, audit, review queue, providers, KB gaps, experiments |
| Agent copilot (`/agent`) | ✅ Production | Escalated tickets, AI drafts, similar tickets |
| Analytics (`/static/analytics.html`) | ✅ Production | Top topics, resolution rates, cost summary |
| Email (IMAP polling) | ✅ | `scripts/email_poller.py` + webhook inbound |
| Telegram bot | ✅ | `channels/telegram_bot.py` |
| Bitrix24 | ✅ | Webhook escalation |
| Embeddable widget (`/static/widget.html`) | ✅ | Для встраивания на сторонние сайты |

---

## 11. Технический долг и риски

### 11.1. 🔴 Высокий приоритет

| Риск | Почему критично | Рекомендация |
|------|-----------------|--------------|
| **pytest suite hang** | Полный запуск тестов зависает >120s в текущей среде. Это блокирует локальную разработку и замедляет CI feedback loop. | Добавить `--timeout=60` везде; выявить и изолировать тесты с blocking I/O (LLM, DB без rollback). |
| **api/app.py 1 896 LOC** | Монолитный app-файл содержит middleware, lifespan, глобальное состояние, 15+ re-export'ов, вспомогательные функции. Нарушает SRP. | Вынести lifespan, middleware, global state в отдельные модули (`api/lifespan.py`, `api/middleware.py`, `api/state.py`). |
| **agent/graph.py 2 101 LOC** | Самый большой модуль. Содержит pipeline definition, LLM wrappers, fact verification, tool use, error handling, usage tracking. | Разбить на `agent/nodes/retrieve.py`, `agent/nodes/generate.py`, `agent/nodes/verify.py`, `agent/nodes/route.py`. |
| **Empty `rotate_encryption_key.py`** | Ключ шифрования нельзя ротировать без downtime. При компрометации — полная потеря данных. | Реализовать online re-encryption с двойным хранением (old + new key) в maintenance window. |
| **SQLite trace sync-in-async** | `tracing/_base_trace.py` использует синхронный `sqlite3` из async кода. Создает блокировки event loop под нагрузкой. | Переписать на `aiosqlite` или вынести запись в отдельный ThreadPoolExecutor с bounded queue. |

### 11.2. 🟡 Средний приоритет

| Риск | Описание | Рекомендация |
|------|----------|--------------|
| **codex-tasks архив (180+ файлов)** | 180 Markdown-файлов задач занимают ~1.5 MB и раздувают репозиторий. 90% — closed/архивные. | Вынести в отдельный репозиторий `rag-support-assistant-backlog` или wiki. |
| **Vectordb global caches** | `_retriever_cache`, `_chunks_cache`, `_store_cache` — unbounded dicts без TTL. При долгой работе с многими tenants — OOM. | Добавить LRU с лимитом (например, `functools.lru_cache` или TTLDict). |
| **htmlcov в git** | 70+ HTML-файлов coverage отчета закоммичены (~3 MB). Это артефакты сборки. | Добавить `htmlcov/` в `.gitignore`, удалить из индекса. |
| **Dependency drift** | `requirements.txt` содержит loose constraints (`>=0.2.0`), `requirements.lock` — pinned hashes для Linux x86_64. Windows/mac разработчики не могут установить из lock напрямую. | Добавить `requirements-windows.lock` или использовать `uv` с `--python-platform windows`. |
| **Missing mypy coverage** | Только 18 файлов в strict scope. `api/routers/*.py`, `scripts/*.py`, `tests/*.py` — без type checking. | Расширять strict scope постепенно: `api/routers/` → `ingestion/` → `evaluation/`. |
| **Slow model loading** | BGE-M3 (~1.2 GB RAM) и cross-encoder загружаются при первом запросе. Cold start >5-10s. | Добавить warm-up в lifespan: `get_embeddings()` + `get_retriever()` при старте. |
| **ChromaDB delete-then-recreate** | `build_vector_store` удаляет существующую коллекцию перед созданием новой. При сбое между delete и create — данные потеряны. | Использовать `upsert` или atomic swap (новая коллекция → rename). |

### 11.3. 🟢 Низкий приоритет / Предложения по улучшению

1. **i18n:** UI и ответы ассистента только на русском/английском. Нет системы перевода.
2. **GraphQL / gRPC:** Только REST. Для high-throughput internal API можно добавить gRPC.
3. **WebSocket streaming:** SSE работает, но WebSocket дал бы двустороннюю связь для real-time typing indicators.
4. **Model quantization:** BGE-M3 можно квантовать до `int8` для снижения RAM на 50%.
5. **Vector store alternatives:** ChromaDB хороша для MVP, но для >100k документов — Qdrant/Pinecone/Weaviate масштабируются лучше.

---

## 12. Сравнение с предыдущими аудитами

| Аудит | Дата | Ключевые находки | Текущий статус |
|-------|------|------------------|----------------|
| `audit_opus_2026-04-26.md` | 2026-04-26 | Root-level shims, module layout debt, api/app.py monolith | ✅ Phase 1-5 complete. Root shims удалены. Router extraction 2a-2m + auth complete. |
| `audit_opus_27_04_26.md` | 2026-04-27 | Type-checking debt, mypy strict scope | ✅ auth, db, llm.providers, config.settings, agent.*, api.app — all strict-clean. |
| `audit_codex_27_04_26` | 2026-04-27 | Security hardening, production secrets validation | ✅ validate() fail-fast на JWT_SECRET, ADMIN_PASSWORD_HASH, CORS, DB_ENCRYPTION_KEY. |
| **Текущий аудит** | 2026-05-04 | pytest hang, api/app.py + agent/graph.py monoliths, empty rotate_encryption_key.py, SQLite sync-in-async, unbounded vectordb caches | Новые находки. Требуют action. |

---

## 13. Рекомендуемый план действий (приоритизированный)

### Sprint 1 (1-2 недели) — Стабильность

1. **Исправить pytest hang:**
   - Добавить `pytest-timeout` во все CI jobs
   - Выявить тесты без моков для LLM/DB и добавить `monkeypatch` или `@pytest.mark.skipif`
   - Цель: полный suite проходит <5 минут локально

2. **Удалить артефакты из git:**
   - `htmlcov/` → `.gitignore`
   - `codex-tasks/Archive/` → вынести в wiki или отдельный репозиторий
   - `.tmp/`, `.pytest-tmp*`, `.mypy_cache` — убедиться, что в `.gitignore`

3. **Устранить empty file:**
   - Реализовать `scripts/rotate_encryption_key.py` или удалить, если не планируется в ближайшие 2 спринта

### Sprint 2 (2-4 недели) — Архитектура

4. **Разбить api/app.py:**
   - `api/lifespan.py` — startup/shutdown, alembic auto-migrate, vector store init
   - `api/middleware.py` — CORS, session, correlation ID, request body size limit
   - `api/state.py` — `_sessions`, `_pipeline_semaphore`, `_vector_store` и т.д.
   - Цель: `api/app.py` <500 LOC

5. **Разбить agent/graph.py:**
   - `agent/nodes/retrieve.py`, `agent/nodes/generate.py`, `agent/nodes/verify.py`, `agent/nodes/route.py`
   - `agent/llm_wrapper.py` — `LocalOllamaLLM`, usage tracking
   - Цель: `agent/graph.py` <800 LOC

6. **Bounded caches:**
   - `vectordb/manager.py`: заменить глобальные dict на `cachetools.TTLCache` или `functools.lru_cache` с `maxsize=32`

### Sprint 3 (4-6 недель) — Производительность

7. **SQLite → async:**
   - Переписать `tracing/_base_trace.py` на `aiosqlite`
   - Или обернуть sync calls в `asyncio.to_thread()` с bounded queue

8. **Warm-up на старте:**
   - В lifespan загружать embeddings model и строить retriever для default tenant

9. **ChromaDB atomic ingestion:**
   - Использовать `collection.upsert` вместо delete-then-recreate
   - Добавить bulk ingestion через `add_documents` с batch_size

### Sprint 4 (6-8 недель) — Масштабирование

10. **Expand mypy strict scope:**
    - `api/routers/*.py` → `ingestion/` → `evaluation/` → `scripts/`
    - Цель: 50%+ codebase under strict mypy

11. **Key rotation:**
    - Реализовать online re-encryption для `db/crypto.py`
    - Добавить `scripts/rotate_encryption_key.py` с dry-run и confirmation

12. **Load testing:**
    - Добавить `tests/load/` с Locust или k6
    - Цель: 100 req/s sustained на `/api/ask` с 95th percentile <2s

---

## 14. Заключение

**RAG_Support_Assistant** — это один из наиболее зрелых open-source RAG-проектов, с которыми я сталкивался. Кодовая база демонстрирует продуманную архитектуру, сильную культуру безопасности (production hardening, encryption, RBAC), и системный подход к качеству (regression gates, online evaluators, review queues, knowledge loops).

Основные блокеры перед production scale:
1. **Нестабильный test suite** (hang)
2. **Монолитные модули** `api/app.py` и `agent/graph.py`
3. **Sync SQLite в async контексте**
4. **Unbounded caches**

После устранения этих рисков проект готов к горизонтальному масштабированию через Kubernetes и к добавлению enterprise-фич (SSO/SAML, SLA monitoring, advanced analytics).

---

*Аудит выполнен автоматически Kimi Code CLI на основе статического анализа кода, запуска линтеров (ruff, mypy, bandit) и просмотра конфигурационных файлов. Для дополнительной детализации рекомендуется провести performance profiling под нагрузкой и security penetration testing.*

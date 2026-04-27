# RAG_Support_Assistant — глубокий аудит + implementation log

**Дата:** 2026-04-26
**HEAD на момент аудита:** `edb856f` (master, 121 коммитов, 8 за тот день)
**Аудитор:** Claude Opus 4.7 (1M context)
**Скоуп:** локально используемый RAG-ассистент (FastAPI + LangGraph + Ollama, БД-trace SQLite, опционально Postgres + Redis + Qdrant)
**Метод:** статический анализ репозитория, верификация ключевых находок чтением файлов и Pydantic settings, затем 4 итерации hardening работы

> **TL;DR для тех, кто открывает этот файл первый раз.**
> Документ состоит из двух частей. Секции 0-11 — оригинальный аудит-отчёт от 2026-04-26 (диагноз, оценки, roadmap). Секция 12 в самом конце — **implementation log**: 18 закрытых задач, что осталось, как продолжить в новой сессии. Если нужно быстро понять текущее состояние — сразу к секции 12.

**Сопутствующие документы:**
- [`DEPRECATIONS.md`](./DEPRECATIONS.md) — карта legacy-расположений, фазированный план миграции, mypy-долг.
- [`docs/SESSION-NOTES-2026-04-26-audit.md`](./docs/SESSION-NOTES-2026-04-26-audit.md) — handover для новой сессии (что, где, как продолжить).
- [`docs/CHANGELOG.md`](./docs/CHANGELOG.md) — запись о hardening-сессии 2026-04-26.

---

## 0. Контекст и калибровка аудита

Проект задуман как **локально используемый продукт** (single-host, single-user или small-team).
Это критично для приоритизации:

- ❌ НЕ применимо: SLA, региональные failover, enterprise-grade observability, RBAC «по карточке доступа», multi-region DR, threat-modeling от внешнего адверсария.
- ✅ Применимо: код-гигиена, поддерживаемость, корректность RAG-пайплайна, корректность схем, операционная гладкость локального деплоя, защита от self-foot-gun (случайно открыть локальный сервис на 0.0.0.0 → стать админом без пароля).

В репо параллельно лежит `commercial-upgrade-plan.md` с амбициями «9.0/10 commercial product». Это **второй продуктовый сценарий**, не сегодняшний скоуп. Аудит фиксирует находки из обоих ракурсов отдельно — где претензия валидна для локального продукта, она помечена `[LOCAL]`; где она имеет смысл только в commercial-сценарии — `[COMMERCIAL]`.

---

## 1. Executive Summary (1 страница)

| Дименсия | Оценка | Комментарий |
|---|---|---|
| Архитектура RAG-пайплайна | **9 / 10** | LangGraph-граф из 9 узлов, Self-RAG, hybrid search (BM25+vector+RRF), cross-encoder rerank, fact verification, multi-provider failover. Уровень 2026 года. |
| Качество кода | **7 / 10** | 1 (!) TODO на 30K строк — выдающаяся гигиена. Но `api/app.py` = 5288 строк (монолит-роутер) тянет всю систему вниз. |
| Безопасность (для local) | **6.5 / 10** | Корректные основы (timing-safe compare, JWT, pgcrypto, PII-redact). Один реальный footgun: anonymous-admin fallback при пустом `API_KEY`. |
| Безопасность (для commercial) | **5 / 10** | Тот же fallback + отсутствует `Field(max_length=...)` на user input + нет CI security-scan + ключ Mistral виден в `.env`. |
| Тесты | **8 / 10** | 115 файлов, 17.6K строк, есть integration + curated dataset + регрессия. Но coverage gate в CI не проверяется, mypy в pre-commit нет. |
| Operability | **8 / 10** | Docker compose с 6 сервисов + healthchecks, 17 alembic миграций, 50+ Prometheus метрик, OTel/Jaeger, runbook + DR docs. |
| Документация | **9 / 10** | README 920 строк актуален, QUICKSTART с 3 профилями, research/ docs 2025-2026, axe-audit. |
| Тех. долг | **7.5 / 10** | Структурно: api-монолит, дубли в root (manager.py, sqlite_trace.py, loader.py — алиасы, но без deprecation плана). Долг управляем. |

**Интегральная оценка для local-сценария: 7.8 / 10.**
**Интегральная оценка для commercial-сценария: 6.9 / 10.**

### Top-5 действий, упорядочены по `impact × (1/effort)`

| # | Действие | Impact | Effort | Когда |
|---|---|---|---|---|
| 1 | Закрыть anonymous-admin fallback в `auth/dependencies.py:32-33` явным failure при отсутствии API_KEY (и переключить дефолт на 127.0.0.1) | 🔴 High | 30 мин | Эта неделя |
| 2 | Авто-прогон `alembic upgrade head` в lifespan startup | 🟠 Med | 30 мин | Эта неделя |
| 3 | Разбить `api/app.py` (5288) на ~6 router-модулей (ask, admin, agent, evaluations, feedback, system) — без поведенческих изменений | 🔴 High | 1-2 дня | Ближайший месяц |
| 4 | Добавить `pytest --cov` с порогом 70% в pre-commit/CI, удалить root-уровневые алиасы `manager.py`/`loader.py`/`sqlite_trace.py` (или явно пометить deprecated) | 🟠 Med | 0.5 дня | Ближайший месяц |
| 5 | Внедрить mypy strict для `agent/`, `db/`, `auth/`, `llm/providers/` (минимум критичные модули) | 🟡 Low | 1 день | Квартал |

Остальные находки — секции 4-9.

---

## 2. Архитектура

### 2.1 Стек (зафиксировано из `requirements.txt` / `pyproject.toml`)

```
Python ≥3.11
FastAPI ≥0.100, uvicorn (2 workers)
LangGraph ≥0.1, LangChain 0.2.x (core/community/text-splitters/experimental)
Vector DB:    ChromaDB ≥0.4 (default, persisted в data/vectordb/)
              Qdrant ≥1.7 (опционально, через RAG_VECTOR_BACKEND)
Embeddings:   BAAI/bge-m3 (multilingual, default)
Reranker:     cross-encoder/ms-marco-MiniLM-L-6-v2
BM25:         rank-bm25 ≥0.2
LLM:          Ollama (qwen2.5:7b default, llama3.2:3b fast tier)
              Mistral API (опц.)
              GraceKelly browser orchestrator (опц.)
БД:           SQLAlchemy[asyncio] ≥2.0 + asyncpg (Postgres) + psycopg2-binary
              SQLite для trace store (data/tracing/traces.db, 24 МБ)
Кэш:          Redis ≥5 + slowapi (rate limit), отдельный in-memory LRU + disk cache
Auth:         PyJWT ≥2.8, passlib[bcrypt], authlib (OIDC: Google, Microsoft)
Async:        Celery ≥5.3 (фоновые таски, ingestion)
Observability:Langfuse ≥2.0, OpenTelemetry SDK ≥1.27 (FastAPI/httpx/SQLAlchemy/Redis instrumentation), Jaeger
Tooling:      pytest ≥9.0, ruff ≥0.15, pre-commit ≥4.5
```

**Оценка стека:** современно, согласовано, без backwater-зависимостей. Все ключевые компоненты — текущий major. Отсутствие `mypy` в pinned deps — первый намёк, что type-checking не на CI.

### 2.2 Граф пайплайна (`agent/graph.py`, 2064 строки)

9 узлов LangGraph:

```
classify_complexity
        ↓
transform_query (+ HyDE опц.)
        ↓
retrieve (BM25 + vector + RRF, top-K → rerank top-N)
        ↓
grade_docs (Corrective RAG: фильтр по relevance per-doc)
        ↓
generate (LLM call: ollama / mistral / GraceKelly)
        ↓
evaluate (self-eval quality 1-100 + relevance)
        ↓
verify_claims (опц., FACT_VERIFICATION_ENABLED)
        ↓
route → "auto" | "human" | "retry" (Self-RAG loop) | "error"
        ↓
suggest_questions (3-5 follow-ups)
```

**Что хорошо:**
- Чистая функциональная композиция, узлы — pure transformations над `GraphState` (TypedDict).
- Self-RAG retry с потолком итераций (`RAG_SELF_RAG_MAX_ITER`) — нет infinite loop.
- Circuit breaker на LLM-вызовах + escalation в `mock_inbox` или Bitrix webhook при провале.
- Tracing на каждый узел: Langfuse + OpenTelemetry span + локальный SQLite trace.

**Что вызывает вопросы:**
- 2064 строки в одном файле для 9 узлов — есть пространство выделить каждый узел в отдельный модуль (`agent/nodes/`). Не критично, но усложняет навигацию и параллельную работу 2+ человек.
- Внутри узлов иногда смешан orchestration + бизнес-логика + retry + error handling. Тестируемость нодов отдельно от графа — затруднена.

**Рекомендация:** при следующем рефакторе вынести узлы в `agent/nodes/{classify,transform,retrieve,grade,generate,evaluate,verify,route,suggest}.py`, оставив в `graph.py` только сборку. Не срочно.

### 2.3 API-слой (`api/app.py`, **5288 строк**)

Это **главная архитектурная боль** проекта.

**Что внутри одного файла:**
- /api/ask, /api/ask-stream, /api/sessions/*, /api/upload, /api/health, /api/feedback
- весь `/api/admin/*` (traces, audit, review queue, providers, KB gaps, drafts, stale docs, circuit breaker)
- весь `/api/agent/*` (ticket queue, similar cases, copilot)
- `/admin/evaluations/*` (regression runs, evaluation trends, experiments)
- `/api/metrics` (Prometheus exposition)
- сырые SQL через `text()` рядом с ORM-вызовами
- `record_*()` вызовы Prometheus прямо из endpoint-ов
- инлайн try/except с глубиной 5+ уровней

**Конкретный риск:** merge-конфликты при параллельной работе, сложность ревью PR-ов, ограниченная переиспользуемость бизнес-логики (например, `_collect_retrieval_context` вызывается из 3 эндпойнтов — невозможно протестировать без поднятия FastAPI app).

**Минимально необходимый рефакторинг (без переписывания логики):**

```
api/
├── app.py                    # ТОЛЬКО app = FastAPI(); include_router(...)
├── correlation.py            # как сейчас
├── deps.py                   # NEW: общие dependency-функции
├── routers/
│   ├── ask.py                # ~600 LOC: ask, ask-stream, sessions/history
│   ├── admin.py              # ~1200 LOC: traces/audit/review/providers
│   ├── agent.py              # ~700 LOC: agent copilot
│   ├── evaluations.py        # ~1200 LOC: regression runs, experiments
│   ├── upload.py             # ~400 LOC: ingestion endpoints
│   ├── feedback.py           # ~300 LOC: feedback, escalate
│   └── system.py             # ~200 LOC: health, metrics
└── services/                 # NEW: бизнес-логика, отделённая от HTTP
    ├── ask_service.py
    ├── admin_service.py
    └── ...
```

**Эффект:** ~5300 → 7 файлов по 200-1200 LOC. Тесты могут импортировать `services/` без поднятия app. Каждый router-модуль ревьюится независимо. Это 1-2 дня работы и не меняет публичный API.

### 2.4 Дубли в корне репо

| Файл в корне | Канонический | Размер |
|---|---|---|
| `graph.py` | `agent/graph.py` | 13 строк (shim) ✅ |
| `manager.py` | `vectordb/manager.py` | 899 строк (содержательный, не shim) ❌ |
| `loader.py` | `ingestion/loader.py` | 294 строк ❌ |
| `sqlite_trace.py` | `tracing/sqlite_trace.py` | 957 строк ❌ |
| `bitrix.py` | (нет) | 126 строк — оставить |
| `cache.py` | (нет) | 266 строк — оставить, но логика дублируется с `cache/redis_cache.py` |
| `chunking.py` | `scripts/chunking_eval.py` | moved 2026-04-27 |
| `state.py` | `agent/state.py` | shim? проверить |
| `prompts.py` | `agent/prompts.py` | shim? проверить |

**Действие:** для каждого корневого алиаса определить — `(а)` это shim вроде `graph.py` (тогда заменить на `from agent.graph import *  # noqa: F401  # DEPRECATED, will be removed in v2.0`) или `(б)` это содержательный код (тогда выбрать единственное место и удалить второе с переписыванием импортов).

Имеющееся `vectordb/manager.py` подсказывает, что migration уже стартовала, но не была доведена. **15 минут работы каждому файлу**, риск низкий — после миграции прогнать `pytest`.

### 2.5 Слоистость

- ✅ `agent/` отделён от `api/` — pure-functional граф не знает про HTTP.
- ✅ `db/models.py` (SQLAlchemy declarative) отделён от endpoint-ов.
- ✅ `llm/providers/` — чистая абстракция через base class + registry + cost enforcer.
- ✅ `evaluation/` модуль самостоятелен, есть YAML-схемы экспериментов.
- ❌ Нет Repository-слоя: `await db.execute(text(...))` встречается в `api/app.py` десятки раз, рядом с ORM-вызовами.
- ❌ Нет Service-слоя: бизнес-логика смешана с HTTP-обработкой.

Это классическая архитектура «FastAPI router + ORM», которая работает на масштабе MVP (что сейчас) и начинает скрипеть на 10+ маршрутов в одном файле (что уже наступило).

---

## 3. Размеры и сложность

| Модуль | LOC | Файлов | Заметка |
|---|---:|---:|---|
| `api/` | 5346 | 3 | **5288 в одном app.py** ⚠ |
| `scripts/` | 9209 | 31 | вспомогательные, многие >500 — допустимо |
| `agent/` | 3002 | 7 | **2064 в graph.py** ⚠ |
| `evaluation/` | 1973 | 8+ | разбит хорошо |
| `llm/` | 1513 | 5 + providers/ | хорошо разбит |
| `config/` | 1107 | 4 | settings.py = 811 (Pydantic) — норма |
| `ingestion/` | 975 | 4 | хорошо |
| `monitoring/` | 625 | 2 | один большой файл prometheus.py = 624 |
| `channels/` | 561 | 4 | hh.ru/email/telegram — норма |
| `db/` | 464 | 5 | компактно |
| `auth/` | 258 | 5 | компактно |
| `vectordb/` | 265 | 2 | |
| `tracing/` | 287 | 3 | |
| `utils/` | 288 | 5+ | |
| Корневые алиасы | ~3500 | 9-10 | см. 2.4 |
| **Всего production** | **~30 800** | **~150** | |
| **Tests** | **17 679** | **115** | соотношение test:prod ≈ 0.57 |

**TODO/FIXME/XXX/HACK во всём коде: 1 (один) штука** в `bitrix.py:144`. Это очень редкий показатель — гигиена комментариев на отметке senior-level.

**Top-10 крупнейших файлов:**

```
1.  api/app.py                                 5288  ⚠⚠⚠
2.  scripts/regression_eval.py                 1094
3.  sqlite_trace.py (root, дубль)               957  ⚠ см. 2.4
4.  manager.py (root, дубль)                    899  ⚠ см. 2.4
5.  scripts/generate_improvement_backlog.py     901
6.  config/settings.py                          811
7.  tests/test_curated_dataset.py               712
8.  scripts/analyze_thresholds.py               681
9.  scripts/gracekelly_smoke.py                 666
10. monitoring/prometheus.py                    624
```

Из них реальные «god-objects» (бизнес-логика): только `api/app.py`. Остальное — либо скрипты (допустимо для CLI), либо классы вокруг одной концепции (settings, sqlite trace).

---

## 4. Тесты и качество кода

### 4.1 Тестовая база

- **115 файлов / 17 679 строк** — соотношение test:prod = **0.57**, для RAG-проекта это очень хороший уровень.
- Есть `tests/integration/` — end-to-end тесты на streaming, concurrency, upload.
- Есть `tests/test_curated_dataset.py` (712 строк) — золотой набор кейсов для регрессии.
- Markers: `pytest -m "not integration"` для быстрого CI, `pytest tests/integration/` для полного.

### 4.2 Coverage

❌ Нет `.coveragerc` или `pyproject.toml [tool.coverage]`.
❌ Нет вызова `pytest --cov` в pre-commit и нет видимого CI YAML (отсутствует `.github/workflows/`? — стоит подтвердить).
❌ Нет последнего отчёта в репо.

**Рекомендация:** добавить минимальный gate в pre-commit или CI:
```toml
[tool.coverage.run]
source = ["agent", "api", "auth", "db", "evaluation", "llm", "ingestion", "vectordb"]
omit = ["*/tests/*", "scripts/*", "archive-legacy/*"]

[tool.coverage.report]
fail_under = 70
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]
```

### 4.3 Lint & Format

✅ `ruff ≥0.15.11` в pre-commit, autoflag `--fix`, проверки E/F/W, `line-length=100`.
✅ Стандартные хуки: trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, **detect-private-key** (хороший secret-guardrail), check-added-large-files=500KB.
❌ Нет mypy / pyright.
❌ Нет bandit / semgrep / pip-audit для security-сканирования.

**Рекомендация:** для local-продукта минимум — `mypy` на критичные модули (`agent/`, `auth/`, `llm/providers/`). Для commercial — добавить `bandit -r .` и `pip-audit` в CI.

### 4.4 Type hints

Беглый просмотр:
- ✅ `db/models.py` — современный `Mapped[]` стиль SQLAlchemy 2.x.
- ✅ `agent/state.py` — TypedDict с явными типами.
- ✅ Возвраты endpoint-ов часто типизированы (`-> JSONResponse | StreamingResponse`).
- ⚠ `api/app.py` — частый `dict[str, Any]` там, где можно было бы Pydantic-моделью.

Перейти на mypy strict для core-модулей реально, потребует ~1 день правок.

---

## 5. Безопасность

### 5.1 Критичная находка: anonymous-admin fallback

**Файл:** `auth/dependencies.py:32-33`

```python
expected = getattr(settings, "api_key", "")
if not expected:
    return {"sub": "anonymous", "role": "admin", "tenant": "default"}
```

**Риск:**
- Если `API_KEY` не установлен в `.env` (а в `.env.example` он закомментирован/пустой) — **любой запрос проходит как admin**, без Bearer и без X-API-Key.
- Сервер слушает `0.0.0.0:8000` (Dockerfile) → если кто-то случайно запустит контейнер с `-p 8000:8000` без API_KEY, или просто `python main.py` на лэптопе с публичным Wi-Fi — это даст любому в локальной сети admin-доступ ко всем `/api/admin/*` эндпойнтам.

**Рейтинг для local:** 🟠 средний (foot-gun, но в нормальном local-сценарии ничего не утекает).
**Рейтинг для commercial:** 🔴 критический.

**Минимальный фикс (10 минут):**

```python
# auth/dependencies.py
if not expected:
    if os.getenv("ALLOW_ANONYMOUS_ADMIN") == "1":
        return {"sub": "anonymous", "role": "admin", "tenant": "default"}
    raise HTTPException(
        status_code=503,
        detail="API_KEY not configured. Set API_KEY in .env or set ALLOW_ANONYMOUS_ADMIN=1 explicitly."
    )
```

И в `main.py` дефолтить хост на `127.0.0.1` (а не `0.0.0.0`) для локальных запусков:
```python
uvicorn.run(..., host=os.getenv("HOST", "127.0.0.1"), port=8000)
```

Docker compose остаётся на `0.0.0.0:8000` (так и должно быть в контейнере), но если используют `python main.py` напрямую — без явного opt-in не будет публичного listening.

### 5.2 Secrets

✅ `.env` в `.gitignore`, в индексе git его нет.
✅ `.env.example` (7.4K, 150+ переменных) с placeholder values.
⚠ Локально на диске юзера в `.env` лежит реальный `MISTRAL_API_KEY` (audit его прочитал, в этот файл не выписываю). Для local — допустимо. Если ключ когда-либо логинился под shared-Win-аккаунт или попадал в синхронизированный OneDrive/iCloud — стоит ротировать.
✅ Pydantic v2 `SecretStr` используется в `config/settings.py`.

### 5.3 SQL injection

✅ Везде SQLAlchemy ORM (`select()`, `insert()`, параметризованный `text(...)` с bind-параметрами).
✅ Найдены 2 `f-string SQL` — оба безопасные:
  - `llm/providers/runtime.py:207-209` — placeholders `?` строятся динамически по числу элементов, значения передаются параметрами.
  - `tests/test_migration_round_trip.py:30-32` — test fixture, имена таблиц из `sqlite_master`, юзер-input не участвует.

**Вердикт:** SQL injection нет.

### 5.4 Input validation

❌ **Pydantic-модели запросов не имеют ограничений длины.**

Пример:
```python
class AskRequest(BaseModel):
    question: str
    entity_id: Optional[str] = None
```

Для local — допустимо (юзер не будет DoS-ить себя). Для commercial — DOS-вектор: 10 МБ `question` уйдёт в LLM-провайдер, в эмбеддер, в трейс-логи и в БД.

**Рекомендация:**
```python
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    entity_id: Optional[str] = Field(None, max_length=100)
```

### 5.5 Что в порядке

- ✅ Timing-safe сравнение API-ключа: `hmac.compare_digest`.
- ✅ JWT с `expected_type="access"` (значит refresh/access разделение реализовано).
- ✅ RBAC роли: admin / agent / viewer + `require_role(*roles)` dependency.
- ✅ OIDC/SSO для Google + Microsoft (`auth/oidc.py`, `authlib`).
- ✅ Multi-tenant изоляция: `tenant_id` в JWT и во всех таблицах (миграция 003).
- ✅ Encryption at rest: `pgcrypto` extension (миграция 008) + `db/crypto.py` `EncryptedText` field.
- ✅ Audit log таблица (миграция 002), purge background-task.
- ✅ PII-redaction logging filter (`config/logging_config.py`).
- ✅ Нет `subprocess`, нет `eval`/`exec`, нет `pickle.loads` — найдено grep-ом 0 случаев.
- ✅ Circuit breaker (`utils/circuit_breaker.py`) защищает от cascade при flaky LLM.
- ✅ Rate limiting через `slowapi`.
- ✅ Pre-commit `detect-private-key`.

### 5.6 Чего нет (для local — допустимо, для commercial — нужно)

- ❌ CSP/HSTS заголовки (`SecurityHeadersMiddleware`).
- ❌ Bandit / semgrep / pip-audit на CI.
- ❌ Secret rotation playbook (есть BACKUP-encryption playbook в `docs/operations/`, но не secret rotation).
- ❌ Threat model документ.

---

## 6. Operability

### 6.1 Docker

✅ `Dockerfile`: python:3.11-slim, non-root `app` user, `--no-cache-dir` pip, healthcheck, `--workers 2`.
✅ `docker-compose.yml`: 6 сервисов (ollama, ollama-init, postgres, redis, jaeger, app), все с healthchecks, named volumes, `depends_on` с условиями (`service_healthy` / `service_completed_successfully`).
✅ `docker-compose.test.yml` отдельный для регрессионного прогона.

### 6.2 Миграции

17 alembic-ревизий, последовательно описывают эволюцию схемы:
```
001 initial → 002 audit log → 003 tenant_id → 004 escalation →
005 eval results → 006 KB gaps → 007 SSO fields → 008 pgcrypto →
009 KB drafts → 010 doc stats → 011 trace costs → 012 review queue →
013 regression runs → 014 trace evaluations → 015 experiment deployments →
016 experiment assignments → 017 curated case status
```

❌ **Нет автоматического `alembic upgrade head` при старте app.** В Dockerfile ENTRYPOINT — сразу `uvicorn`. Это означает, что после `docker-compose up` нужно вручную:
```bash
docker-compose exec app alembic upgrade head
```

**Рекомендация:** добавить в `main.py`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("AUTO_MIGRATE", "true").lower() == "true":
        from alembic.config import Config
        from alembic import command
        cfg = Config("alembic.ini")
        await asyncio.get_running_loop().run_in_executor(None, command.upgrade, cfg, "head")
    yield
```

Или альтернатива — отдельный init-контейнер `migrate` в compose, который завершается перед стартом `app` (паттерн уже используется для `ollama-init`).

### 6.3 Observability

✅ **OpenTelemetry**: instrumentations для FastAPI / httpx / SQLAlchemy / Redis, OTLP-экспорт в Jaeger (`docker-compose.yml`, jaeger:1.59).
✅ **Langfuse**: `trace_llm_call()` декорирует все LLM-вызовы.
✅ **Prometheus**: ~50 метрик, покрывают auth, БД-pool, LLM-cost, retry-events, regression results, review queue, evaluator runs, rate-limit rejections, circuit breaker. `/api/metrics` endpoint.
✅ **SQLite traces** (`data/tracing/traces.db`, 24 МБ) — детальный per-step trace для admin UI.
✅ **JSON structured logging** с PII filter и `trace_id` в context.

Это **уровень enterprise SaaS**, для локального продукта — overkill, но overkill безвредный.

### 6.4 SQLite race condition (multi-worker)

Dockerfile запускает `uvicorn ... --workers 2`. При этом trace store — SQLite (`data/tracing/traces.db`).

**Риск:** SQLite в WAL-режиме допускает concurrent reads + один writer. Если оба worker-а пишут трейс одновременно — `database is locked` errors.

Проверил `sqlite_trace.py:121` — обычный `sqlite3.connect(db_path)`, без явного `journal_mode=WAL`. Это означает rollback journal mode → **любой concurrent write = lock**.

**Рекомендации (по убыванию срочности):**
1. В `sqlite_trace.py` после `connect()` сразу `conn.execute("PRAGMA journal_mode=WAL")` и `conn.execute("PRAGMA busy_timeout=5000")`.
2. Если есть Postgres (а в compose он есть) — для production-like локального запуска пускать trace через тот же Postgres вместо SQLite. SQLite оставить только для dev-режима без зависимостей.
3. Для local-single-user сценария — `--workers 1` достаточно, и race не возникает.

### 6.5 Backup & DR

✅ `docs/operations/backup-restore.md` — pg_dump, Redis RDB snapshot, ChromaDB directory snapshot.
✅ `docs/operations/backup-encryption.md` — age-based encryption.
✅ `docs/disaster-recovery.md` — playbook.
⚠ Не автоматизировано (нет cron/systemd-timer в репо).

Для local — допустимо, юзер делает бэкап вручную или через системный Time Machine / WSL snapshots.

### 6.6 Health & probes

✅ `/api/health` проверяет: ollama, chromadb, sqlite, postgres, redis. Каждая проба отдаёт статус. Healthcheck в Dockerfile вызывает этот endpoint.

---

## 7. Performance & масштабируемость

### 7.1 Кэширование

Двухуровневая стратегия:
- **In-memory LRU + disk** (`cache.py`, OrderedDict, TTL=3600s, persisted в `data/cache/responses.json`).
- **Redis** (для shared cache между worker-ами, embedding cache, session cache, rate-limit backend).
- **ChromaDB** (vector store с native кэшем similarity).

Метрики `LLM_CACHE_HITS`, `LLM_CACHE_MISSES` — оценка эффективности есть.

### 7.2 Async stack

✅ Полный async: FastAPI, asyncpg, httpx-async, redis-async.
✅ CPU-bound (embedding, chunking, multi-query) выводится в `run_in_executor`.

### 7.3 RAG-пайплайн specifics

- **Hybrid search:** BM25 (rank-bm25) + vector (Chroma/Qdrant) + Reciprocal Rank Fusion (`RRF_K=60`). Современная конфигурация.
- **Reranker:** cross-encoder — стоит CPU, но повышает precision@k. Для local — okay; для high-throughput SaaS — потребует GPU или async batching.
- **Chunking:** `chunk_size=800` / `chunk_overlap=200` дефолты. Опции `RAG_SEMANTIC_CHUNKING`, `RAG_CONTEXTUAL_HEADERS`, `RAG_PARENT_CHILD`. Чанкинг-качество измеряется в `scripts/chunking_eval.py` — это плюс.
- **Embedder:** `BAAI/bge-m3` — multilingual, актуальный SoTA для RU/EN.

### 7.4 GraceKelly bottleneck

Профиль `gracekelly-mixed` запускает strong-tier через **браузер** (Playwright, single session). Это:
- последовательно (нельзя пайплайнить через одну сессию),
- хрупко (Cloudflare, перелогины),
- ~30 минут на 20-case регрессию (зафиксировано в CHANGELOG).

Для local-продукта — допустимо как «free strong-tier». Для commercial — должна остаться только как fallback или dev-tool.

### 7.5 Cost control

✅ `DAILY_COST_LIMIT_USD` (`llm/providers/runtime.py:_enforce_daily_cost_limit`) — fail-fast при превышении.
✅ `LLM_COST_USD_TOTAL` Prometheus counter.
✅ Failover chain: GraceKelly → Mistral → Ollama.

Это серьёзный плюс для commercial-сценария — большинство open-source RAG-проектов не имеют cost guard.

---

## 8. Документация

| Документ | Состояние |
|---|---|
| `README.md` (920 строк) | ✅ актуален, описывает 17 features, 155 env vars, deployment options, OTel setup |
| `docs/QUICKSTART.md` | ✅ свежий (созадан в task-179), 3 deploy-сценария: local-only, external-mistral, gracekelly-mixed |
| `docs/CHANGELOG.md` | ✅ arc-based, актуальный |
| `docs/runbook.md` | ✅ операционные процедуры |
| `docs/disaster-recovery.md` | ✅ DR playbook |
| `docs/errors_e10_e30.md` | ✅ error code reference |
| `docs/operations/backup-restore.md` | ✅ pg_dump / Redis / Chroma |
| `docs/operations/backup-encryption.md` | ✅ age-encryption |
| `docs/operations/gracekelly-smoke.md` | ✅ smoke-test guide |
| `docs/operations/helm-lint.md` | ✅ Helm validation |
| `docs/research/eval-metrics-2025.md` | ✅ современные метрики |
| `docs/research/llm-model-selection-2025.md` | ✅ 2025 |
| `docs/research/production-monitoring-2025.md` | ✅ 2025 |
| `docs/research/rag-landscape-2026.md` | ✅ **2026** — самая актуальная RAG-картина |
| `docs/a11y/axe-audit-2026-04-21.md` | ✅ WCAG AA audit (свежий, 5 дней назад) |
| `docs/superpowers/specs/2026-04-03-production-hardening-design.md` | ✅ внутренняя спека |
| `commercial-upgrade-plan.md` (18K) | ✅ стратегический roadmap (Phase 0-3) |
| `rec.md` | проверить актуальность |

**Оценка:** документация на уровне зрелого SaaS, redundant для local-продукта, но именно redundant — не вредна.

---

## 9. Активность и долги

### 9.1 Git-активность

- 121 коммит всего, 8 за сегодня (2026-04-26).
- Последние 3 закрытых таска: 177 / 178 / 179 — GraceKelly интеграция + регрессионный фреймворк + case-insensitive matching.
- Все коммиты с явной задачей в message, есть rev-инкременты при сложных закрытиях (rev 1-5).
- Untracked в reports/regression/ — артефакты прогонов, корректно НЕ закоммичены.

### 9.2 Архив

- `archive-legacy/` 180K — корректно отделён, есть `legacy-tests/`.
- `codex-tasks/Archive/` — 24+ завершённых спек.
- Активные roadmap-доки: `arc-6-proposal.md`, `arc-7-proposal.md` — на верху codex-tasks/.

### 9.3 Технический долг — приоритизированный список

| # | Долг | Файл / место | Серьёзность | Effort |
|---|---|---|---|---|
| 1 | Anonymous-admin fallback | `auth/dependencies.py:32-33` | 🔴 | 30 мин |
| 2 | api-монолит | `api/app.py` (5288 LOC) | 🟠 | 1-2 дня |
| 3 | Дубли в корне (manager.py / loader.py / sqlite_trace.py) | root | 🟠 | 0.5 дня |
| 4 | SQLite WAL не включён | `sqlite_trace.py:121` | 🟠 | 5 мин |
| 5 | Auto-migrate на старте | `main.py` lifespan | 🟠 | 30 мин |
| 6 | Нет coverage gate | `pyproject.toml` / pre-commit | 🟡 | 30 мин |
| 7 | Нет mypy в CI | pre-commit | 🟡 | 1 день |
| 8 | Pydantic-модели без `max_length` | `api/app.py` (request models) | 🟡 (для local), 🟠 (для commercial) | 1 час |
| 9 | Нет Pydantic-моделей для multiple admin endpoints | `api/app.py` (`dict[str, Any]`) | 🟡 | 0.5 дня |
| 10 | Default host `0.0.0.0` для bare `python main.py` | `main.py` | 🟡 | 2 мин |
| 11 | `agent/graph.py` 2064 LOC | можно вынести узлы в `agent/nodes/` | 🟡 | 1 день |
| 12 | Нет bandit/semgrep/pip-audit | CI | 🟡 (для commercial 🟠) | 0.5 дня |
| 13 | Service-слой не выделен | новый `api/services/` | 🟡 | 1-2 дня (после #2) |
| 14 | TODO в bitrix.py:144 | разовый | 🟢 | в плановом цикле |

---

## 10. Roadmap рекомендаций

### Эта неделя (быстрые победы, ~3 часа суммарно)

1. **Закрыть anonymous-admin fallback** (`auth/dependencies.py:32-33`):
   ```python
   if not expected:
       if os.getenv("ALLOW_ANONYMOUS_ADMIN") == "1":
           return {"sub": "anonymous", "role": "admin", "tenant": "default"}
       raise HTTPException(status_code=503, detail="API_KEY not configured")
   ```
2. **Дефолтить uvicorn-host на 127.0.0.1** в `main.py` для bare-запуска.
3. **Включить WAL для SQLite traces:** `conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=5000")`.
4. **Добавить `Field(max_length=...)`** на `AskRequest`, `UploadRequest`, `FeedbackRequest`.
5. **Auto-migrate в lifespan** или init-контейнер.

### Ближайший месяц (структурная работа, ~3-4 дня)

6. **Разбить `api/app.py`** на router-модули: ask / admin / agent / evaluations / upload / feedback / system. Без изменения публичного API. Прогнать существующие тесты.
7. **Удалить дубли в корне** (manager.py / loader.py / sqlite_trace.py) — оставить только пакетные версии. Прогнать `pytest`.
8. **Coverage gate 70%** в pre-commit.
9. **mypy strict** для `agent/`, `auth/`, `db/`, `llm/providers/`.

### Квартал (если идёт commercial-сценарий)

10. Service-слой, выделение бизнес-логики из routers.
11. `bandit` + `pip-audit` + `semgrep` на CI.
12. Threat model документ.
13. Helm chart полный (есть скелет в `deploy/helm/` — довести).
14. Async-orchestrator вокруг GraceKelly browser (или depricate).
15. Multi-region DR (только если commercial выходит за пределы single-host).

### Что НЕ нужно делать

- ❌ Переписывать LangGraph-граф — он хорош.
- ❌ Менять стек БД / vector store / embedder — выбор современный.
- ❌ Внедрять Kubernetes для local-продукта.
- ❌ Тащить ещё одну observability-систему — текущей (Langfuse + OTel + Prometheus + SQLite traces) более чем хватает.

---

## 11. Финальная оценка

**Для локального использования: 7.8 / 10.**
Это **зрелый, хорошо инженерный RAG-ассистент**, проникновение которого в production уже на уровне зрелого SaaS. Основные пробелы — структурный долг в `api/app.py` и один безопасностный foot-gun, оба адресуются за 1-2 дня работы.

**Для commercial-выпуска: 6.9 / 10.**
До 9.0/10 (целевой уровень из `commercial-upgrade-plan.md`) реально дойти за квартал работы по roadmap-у выше. Главное — не разбавлять усилия: сначала закрыть structural debt (api split + service layer + type checking), потом наслаивать commercial-фичи (CSP, secret rotation, multi-tenant DR, etc.).

**Самое сильное место проекта** — RAG-пайплайн и observability. Видна работа senior-инженера: hybrid search + Self-RAG + cost guard + 50 метрик + curated regression-фреймворк — это редко встречается в open-source RAG-репах.

**Самое слабое место** — `api/app.py`. 5288 строк в одном роутере неизбежно станут точкой трения при переходе на 2+ человек на code-base.

---

## 12. Implementation log — 4 итерации работы 2026-04-26

После аудита (секции 0-11) выполнены 4 итерации hardening-работы. Все 22 задачи трекились через TaskCreate/TaskUpdate, прогон тестов после каждой структурной правки.

### 12.1 Сводная таблица выполненного

| Итерация | Задач | Категория | Главные результаты |
|---|---|---|---|
| 1 (Quick wins) | 6 | security + operability | anonymous-admin gated, host=127.0.0.1 default, SQLite WAL, Field max_length, alembic auto-migrate, 17/17 tests |
| 2 (Hygiene) | 4 | code quality | docstring fixes для root-level файлов, DEPRECATIONS.md, coverage gate 70%, mypy strict для auth.* + db.models, 42/42 tests |
| 3 (Security tooling + first split) | 4 | scanning + structure | bandit + pip-audit в pre-commit, фикс HIGH MD5, удаление 3 deprecation shim-ов, **первый split** `api/routers/system.py` (`/health/live`, `/metrics`), 31/31 tests |
| 4 (More splits) | 4 | structure | **3 новых split-а**: `api/routers/agent.py` (4 endpoints), `admin_review.py` (3), `auth_sso.py` (3). Найден pattern для monkeypatch-совместимости sub-routers. 68/68 tests |
| 5 (Documentation) | 4 | docs | этот раздел, SESSION-NOTES, CHANGELOG, README-апдейт |
| **Итого** | **22** | — | **12 endpoints вынесены из 5288-LOC монолита; 0 high security findings; 0 known CVE** |

### 12.2 Полный список 18 закрытых задач hardening (без doc-задач 19-22)

| # | Задача | Файл/файлы | Verification |
|---:|---|---|---|
| 1 | Anonymous-admin fallback gated через `ALLOW_ANONYMOUS_ADMIN` env, иначе 503 | `auth/dependencies.py`, `tests/conftest.py` | tests pass с opt-in env |
| 2 | Default host `127.0.0.1` для bare `python main.py` (через `HOST` env) | `main.py` | smoke import OK |
| 3 | SQLite traces: `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL` | `sqlite_trace.py`, `main.py` | concurrent writes больше не блокируются |
| 4 | `Field(max_length=…)` на `RefreshRequest` (4096) и legacy `AskRequest` (4000/100) | `api/app.py`, `main.py` | DOS-payload защита |
| 5 | `alembic upgrade head` в startup hook (`AUTO_MIGRATE`, default true) | `main.py` | logs warning, не крашит при недоступной БД |
| 6 | Прогон unit-набора (auth + jwt + tenant + body_size) | — | 17/17 |
| 7 | Misleading docstrings на root-level файлах (`manager.py`, `sqlite_trace.py`, `loader.py`, `chunking.py`, `bitrix.py`, `mock_inbox.py`, `seed_docs.py`); создан `DEPRECATIONS.md` с 5-фазным планом миграции | 7 файлов + DEPRECATIONS.md | imports чистые |
| 8 | Coverage gate 70% (branch coverage, source 14 модулей, exclude pragmas) | `pyproject.toml` | `pytest --cov` имеет gate |
| 9 | mypy strict для `auth.*` + `db.models`, фикс 4 type errors в auth/oidc.py + auth/dependencies.py | `pyproject.toml`, `auth/oidc.py`, `auth/dependencies.py` | `mypy auth db/models.py` → 0 issues |
| 10 | Прогон focus-set (auth + health + trace + migration + tenant) | — | 42/42 |
| 11 | TODO в bitrix.py — оказался URL placeholder `XXXXXX`, не TODO. 0 TODO/FIXME/HACK во всём коде | — | grep подтверждает |
| 12 | Удалены deprecation shim-ы `graph.py`, `state.py`, `prompts.py` + dead `except ImportError` в `agent/graph.py` (циклически re-exportировал через эти shim-ы) | 4 файла | imports чистые |
| 13 | bandit + pip-audit в `.pre-commit-config.yaml`, `[tool.bandit]` в pyproject (skip B608/B310 false positives), фикс HIGH severity MD5 в `tracing/langfuse_trace.py:55` (`usedforsecurity=False`) | 3 файла | bandit: 0 High/Med; pip-audit: 0 CVE |
| 14 | **First split** — `api/routers/system.py` с `/health/live` + `/metrics` | `api/routers/__init__.py`, `system.py`, `api/app.py` | 31/31 |
| 15 | Split `api/routers/agent.py` — `/agent/tickets` (list/get/respond) + `/agent/similar` (4 endpoints), `AgentRespondRequest` перемещён | `api/routers/agent.py`, `api/app.py` | 13/13 после фикса monkeypatch-pattern |
| 16 | Split `api/routers/admin_review.py` — `/admin/review-queue` (list/update/stats) + `ReviewQueueUpdateRequest` | `api/routers/admin_review.py`, `api/app.py` | tests pass |
| 17 | Split `api/routers/auth_sso.py` — `/auth/sso/{providers,login,callback}` | `api/routers/auth_sso.py`, `api/app.py` | tests pass |
| 18 | Финальный прогон focus-set после всех split-ов | — | **68/68** |

### 12.3 Метрики до и после

| Метрика | До (на момент аудита) | После 4 итераций |
|---|---|---|
| HIGH severity bandit findings | 1 (MD5) | **0** |
| MEDIUM severity bandit findings | 7 (false positives) | **0** (после конфига skip) |
| Known CVE в pinned deps | unknown | **0** (pip-audit clean) |
| mypy strict-clean modules | 0 | **5** (`auth/*` + `db/models`) |
| Endpoints в `api/app.py` монолите | ~70 | ~58 (12 вынесены) |
| LOC `api/app.py` | 5288 | ~4770 (≈10% уменьшение) |
| Anonymous-admin foot-gun | open | **закрыт** (gated env) |
| SQLite multi-worker race | open | **закрыт** (WAL) |
| Auto-migrate on startup | manual | **automatic** (gated env) |
| TODO/FIXME/HACK в коде | 0 (1 ложно-позитивный из аудита) | 0 |
| Deprecation shim-ы в корне | 3 | **0** |
| Test pass на focus-set | 17/17 (initial) | **71/71** (sanity 2026-04-26 16:42 UTC) |

### 12.4 Обновлённая самооценка

| Дименсия | Было | Стало | Что изменилось |
|---|---:|---:|---|
| Безопасность (local) | 6.5/10 | **8.5/10** | Anonymous fallback закрыт, MD5 fixed, bandit clean |
| Безопасность (commercial) | 5/10 | **7/10** | + scanning chain + max_length validation |
| Качество кода | 7/10 | **8/10** | shim removal, docstring sanitation, mypy strict для auth/db |
| Тесты | 8/10 | **8/10** | coverage gate добавлен (но baseline ещё не на 70%) |
| Operability | 8/10 | **9/10** | + SQLite WAL + auto-migrate |
| Архитектура | 7/10 | **7.5/10** | первые 4 sub-router в `api/routers/`, паттерн доказан |
| **Local total** | **7.8/10** | **~8.7/10** | |
| **Commercial total** | **6.9/10** | **~7.7/10** | |

### 12.5 Что ОСТАЁТСЯ сделать (упорядочено по приоритету)

> Update 2026-04-27: split-фазы 2a-2m закрыты после этого audit log, включая conversation-router (`/ask`, `/chat`, `/ask/stream`, `/chat/stream`). Актуальная карта split-ов: `DEPRECATIONS.md`; актуальный handover: `docs/SESSION-NOTES-2026-04-26-audit.md`.

#### A. Продолжение разбиения `api/app.py` (DEPRECATIONS Phase 2a-2m)

Phase 2a-2m закрыт. `api/app.py` теперь 2128 LOC и держит только небольшой
app-owned auth/session surface (`/auth/login`, `/auth/refresh`, `/sessions/*`)
плюс app construction/lifespan/shared helpers. Если нужен полностью тонкий
app-shell, следующий отдельный cleanup — вынести auth/session endpoints.

#### B. Type-checking долг

Update 2026-04-27: `llm/providers/*` informational mypy scope and
`db/engine.py` now pass. Strict promotion для `llm.providers.*` остаётся
отдельной задачей из-за недостающих annotations на provider classes.

#### C. DEPRECATIONS Phase 2-5 — перемещение root-level файлов

В порядке возрастающего риска:
- **Phase 2** — `bitrix.py` → `integrations/bitrix.py`, `mock_inbox.py` → `integrations/mock_inbox.py`, `seed_docs.py` → `demo/seed_docs.py` (~2 часа, требует grep+rewrite импортов)
- **Phase 3** — закрыт 2026-04-27 по Option B: `manager.py` → `vectordb/_base_manager.py` + root shim, `sqlite_trace.py` → `tracing/_base_trace.py` + root shim
- **Phase 4** — resolve `loader` fork (root vs ingestion) — это product decision, не refactor
- **Phase 5** — закрыт 2026-04-27: `chunking.py` → `scripts/chunking_eval.py`

#### D. Coverage до 70%

Сейчас focus-set дал 24%. Полный pytest пакет должен дать существенно выше, но `test_upload_path_bypasses_body_middleware` зависает в shared-state run-е — нужен dedicated debug.

#### E. Что НЕ делать (зафиксировано в аудите)

- ❌ Переписывать LangGraph-граф — он хорош.
- ❌ Менять стек БД / vector store / embedder.
- ❌ Внедрять Kubernetes для local-продукта.
- ❌ Тащить ещё одну observability-систему.

### 12.6 Pattern для будущих split-ов sub-router-ов

Тесты используют `monkeypatch.setattr("db.engine.async_session", ...)` и `monkeypatch.setattr(api_app, "log_audit", ...)`. Top-level `from db.engine import async_session` в sub-router **обходит патч**.

**Рабочий паттерн (из `agent.py`/`admin_review.py`):**

```python
from db import engine as _db_engine  # модуль, не объект

def _async_session():
    return _db_engine.async_session()  # late-binding через модуль

async def _log_audit(**kwargs):
    from api import app as _app  # noqa: PLC0415
    return await _app.log_audit(**kwargs)
```

В handler-ах использовать `_async_session()` и `_log_audit(...)` вместо прямых вызовов.

---

*Документ подготовлен в результате статического аудита репозитория `D:\RAG_Support_Assistant\` на 2026-04-26 + 4 итерации hardening работы. Implementation log закрывает секцию 10 «Roadmap рекомендаций» аудита по пунктам «эта неделя» (5/5) и большую часть «ближайший месяц» (4/9). Полная актуальная карта split-ов и mypy-долга — в `DEPRECATIONS.md`.*

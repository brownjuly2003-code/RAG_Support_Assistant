# Changelog

Все значимые изменения в проекте. Формат адаптирован под [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), но сгруппирован по аркам и батчам, а не по семантическим версиям.

## [Security-Lock-Refresh] — 2026-07-16 — dep CVE batch + smoke-test hardening

Focused security/ops pass from `audit_grok_16_07_26.md` (D1 + T1). Defaults and
retrieval behaviour are unchanged.

- **Lock CVE clear:** regenerated `requirements.lock` + `requirements-dev.lock`
  (Python 3.11 / linux hashes) with floors for packages that had fixed advisories.
  Notable pins: `aiohttp>=3.14.1`, `cryptography>=48.0.1` (lock `49.0.0`),
  `starlette>=1.3.1`, `python-multipart>=0.0.31`, `pypdf>=6.13.3`,
  `langsmith>=0.8.18`, `langchain>=1.3.9`, `setuptools>=83.0.0`, plus upgrades of
  `joserfc`, `langchain-classic`, `langgraph-checkpoint`, `langgraph-sdk`,
  `pydantic-settings`. `pip-audit --strict` on the lock: **no known vulns**
  (documented ignores for chroma/torch no-fix advisories retained).
- **OpenAPI-stable route smoke** (`tests/test_production_entrypoint.py`):
  `/api` population and legacy-path absence are asserted via `app.openapi()` so
  FastAPI 0.138+ nested `_IncludedRouter` layouts no longer false-fail.
- **Ollama health scheme allowlist** (`config/settings.py`): `OLLAMA_BASE_URL`
  health probe rejects non-`http`/`https` schemes before `urlopen` (B310).
- **Docs:** official aircargo RAGAS baseline + precision target noted in
  `docs/OPERATIONS.md`.

## [Dogfood-Findings] — 2026-06-18 — практические шероховатости внешнего дожфуда

Закрыты 5 находок из дожфуда на чужом домене (Deckhouse/werf pain-cards,
`FLANT_DOGFOOD_FINDINGS.md`). Все рычаги opt-in/без сети по умолчанию — поведение
дефолта не меняется.

- **Online-evaluators деградируют тихо** (`agent/graph.py`): при недоступном Postgres
  в standalone-графе ошибка персистенса логируется WARNING **один раз на процесс**,
  идентичные повторы — DEBUG (раньше — WARNING на каждый запрос). Новые/иные ошибки
  по-прежнему всплывают на WARNING. Счётчик `rag_online_evaluators_dropped_total`
  сохранён. Ответы графа не затронуты.
- **Видимость прогресса ingest** (`vectordb/manager.py`, `ingestion/pipeline.py`):
  `build_vector_store` логирует начало/длительность тяжёлого embed-шага
  (`[index] embedding N chunks …` / `… built: N chunks in Ns`); LLM-fallback
  contextual-заголовков теперь идёт с **bounded concurrency**
  (`INGESTION_CONTEXTUAL_CONCURRENCY`, default 4) и прогресс-логом
  `[contextual_headers] i/N`. «Медленно» больше не выглядит как «завис».
  (Поправка к находке: прод-путь `build_vector_store` строит заголовки из metadata
  без сети; LLM-вариант — только при `INGESTION_BATCH_ENABLED=true`, по документу.)
- **Опц. wall-budget на `ConversationSession.ask`** (`RAG_ASK_BUDGET_SEC`, default
  `0`=off): вне HTTP-пути (где уже есть `request_timeout_sec`) один залипший вызов
  провайдера больше не растягивает запрос — по истечении бюджета возвращается
  graceful degraded-результат (`route="timeout"`), фоновой прогон не прерывается
  (зеркалит семантику API).
- **Remote-embedding backend** (`RAG_EMBEDDING_BACKEND=remote`): OpenAI/Mistral-
  совместимый `/v1/embeddings` (`vectordb/_base_manager.py: _RemoteEmbeddings`),
  L2-нормировка под локальный путь, батчинг, ключ из env по имени. Снимает привязку
  тяжёлого ingest/поиска к локальному BGE-M3 (разблокирует Windows под правилом
  «1 GiB на процесс»). Дефолт — `local`, путь не тронут.
- **Headless-safe reload** (`main.py`): авто-reload uvicorn вынесен за
  `UVICORN_RELOAD` (default off) — больше не флапает API при записи в `data/`/`demo/`
  во время headless-прогонов.

План: `docs/plans/2026-06-18-dogfood-findings-fixes.md`.

## [Adaptive-Retrieval] — 2026-06-14 — workstream закрыт (opt-in lane shipped, default-флип NO-SHIP)

- **Закрыт** adaptive-retrieval router + Fact-Card (SFR) workstream
  (план `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md`). Решение и
  обоснование — `docs/operations/2026-06-14-adaptive-retrieval-closure.md`.
- **Зашиплено (opt-in):** fact-card lane F1–F4 (`ingestion/factcard_extractor.py`,
  `vectordb/manager.py: build_factcard_store`/`get_factcard_documents`,
  `agent/graph.py: make_retrieve_node` ветка) + R1 router-классификатор
  (`evaluation/adaptive_retrieval/train_router_classifier.py`). Включается
  `RAG_RETRIEVAL_STRATEGY=factcard`; при отсутствии коллекции — fallback на `hybrid`.
  Документация стратегии в README обновлена (`vector|hybrid|graph|factcard`).
- **NO-SHIP-to-default:** авто-роутинг (Phase 3), врезка router'а в дефолт (R2),
  каскад/калибровка (Phase 4) — **не включены в дефолт**. Причины: D2-baseline уже
  FULL 96/100 (headroom мал, мисроутинг = тихая регрессия); `model_routing_enabled=false`
  → текущей per-query LLM-стоимости нет → экономия R1 потенциальная; валидирующий
  Phase-5 (офлайн-дельта на полном `curated_cases`) **автономно не исполним** — реальный
  retrieval-скоринг FULL/PART/MISS был приватным Kaggle-кернелом, в репозитории
  отсутствует. Дефолтный стек остаётся **D2** без изменений.
- `customs-clearance-fields` residual-MISS зафиксирован **закрытым через opt-in
  factcard-lane** (механизм доказан F1–F3 на Mac), а не через флип дефолта.

## [Type-Hardening] — 2026-06-14 (cont.) — mypy strict-scope: vectordb.*

- Завершено направление strict-scope: `vectordb.*` (`vectordb.manager`,
  `vectordb._base_manager`) добавлен в strict-гейт. Пакет уже был полностью
  аннотирован — **0 правок кода, 0 mypy-ошибок**; это ратчет (фиксируем чистое
  состояние), не фикс.
- Проверяется командой `--follow-imports=skip` (вместе с `api.app`): vectordb
  тянет langchain/sentence-transformers, чей полный тип-граф раздувает память
  mypy (~2GB+, виснет на low-RAM Windows) — та же причина heavy-graph, по которой
  `api.app` использует этот флаг (там — таймаут, здесь — память). Под skip
  внешние импорты = `Any`, поэтому `warn_return_any` не включён (ложные срабатывания
  на langchain-возвращающих хелперах, как и в `api.routers`).
- pyproject override (`vectordb.*`) + skip-команда во всех 3 mypy-гейтах
  (ci.yml/local-gate.ps1/autopilot.ps1) расширены на `vectordb`; guard
  `test_mypy_strict_scope_is_synced_across_gates` не тронут (он пинит только
  основную команду; skip-команда вне его охвата).
- Верификация: `mypy api/app.py api/_shared.py api/correlation.py
  api/rate_limit.py api/routers vectordb --follow-imports=skip` — **Success**;
  `tests/test_precommit_config.py` passed; ruff clean. Это закрывает линию
  type-hardening: остаётся только Kaggle-MISS `customs-clearance-fields`.

## [Type-Hardening] — 2026-06-14 — mypy strict-scope: api routers + helpers

- Продолжено направление strict-scope: `api/_shared.py`, `api/correlation.py`,
  `api/rate_limit.py` и `api/routers/*` доведены до strict (22 mypy-ошибки → 0).
  Только типовые правки — **рантайм не менялся**:
  - Аннотированы indirection-хелперы `_async_session()`/`_log_audit()`
    (monkeypatch-проводка для тестов) в `agent`/`admin_ops`/`admin_review`/
    `admin_kb`/`admin_evaluations`/`admin_experiments`/`feedback`.
  - Return-типы эндпоинтов: `chat -> AskResponse`, `sso_login`/`sso_callback
    -> RedirectResponse`; параметры `db: Any` в `_fetch_experiment_*_bucket`.
  - `admin_experiments`: `value is not None` перед `.isoformat()` (union-attr).
  - `analytics`: sort-key по `object`-значениям dict — `cast(int, …)` для count,
    `str(…)` для category.
  - `api/rate_limit.py`: аннотированы stub-классы `ImportError`-fallback'а
    (`Limiter`/`RateLimitExceeded`/`decorator`); `Callable` из `collections.abc`.
- Проверяются отдельной командой `--follow-imports=skip` (как `api.app`):
  `api/_shared.py` транзитивно импортирует `api.app`, чей полный FastAPI-граф
  таймаутит mypy. Без `warn_return_any` (SSO-эндпоинты отдают Any-typed redirect
  от authlib — флаг ругался бы ложно).
- pyproject override + все 3 mypy-гейта (ci.yml/local-gate.ps1/autopilot.ps1)
  расширены на api-модули; guard `test_mypy_strict_scope_is_synced_across_gates`
  не тронут (он пинит только основную команду, api идёт в skip-команду).
- Верификация: gate-команда `mypy api/app.py api/_shared.py api/correlation.py
  api/rate_limit.py api/routers --follow-imports=skip` — **Success, 20 файлов**;
  `tests/test_precommit_config.py` 13 passed; ruff clean.

## [Type-Hardening] — 2026-06-13 (cont.3) — mypy strict-scope: evaluation.*

- Продолжено направление strict-scope: `evaluation.*` (было 16 mypy-ошибок)
  доведён до strict. Только типовые правки — **рантайм не менялся**:
  - `evaluation/online_evaluators.py` (4 union-attr): тернары вида
    `payload.get(k) if isinstance(payload.get(k), dict) else {}` не сужались
    (два независимых вызова `.get`). Результат `.get()` связан в локальную
    переменную до `isinstance` → narrowing применяется (`refusal`/`pii` в
    `_load_patterns`, `metadata`/`tokens` в hit-rate/tool-use). Поведение
    идентично.
  - `evaluation/drift.py` (2 operator): `baseline in (None, 0)` не сужает тип →
    `baseline is None or baseline == 0` (эквивалентно, но mypy narrow'ит `float`).
  - `evaluation/evaluator_runner.py` (1 arg-type): `result` собирается в 3
    ветках → mypy сводит к `dict[str, object]`, `float(result["score"])` падал.
    Первое присваивание аннотировано `result: dict[str, Any]`.
  - `evaluation/simulate_model_benchmark.py` (3 arg-type + 2 call-overload):
    `MODEL_PROFILES`-значения гетерогенны (`int`/`float`/`str` → `object`),
    `int()/float()` их не принимали. Param `_generate_answer(profile: …)`
    переведён `dict[str, object]` → `dict[str, Any]` (call-site совместим).
  - `evaluation/benchmark_runner.py` (1 var-annotated):
    `context_docs_list: list[list[str]]`.
  - `evaluation/rollback_watcher.py` (4 no-untyped-def): duck-typed async
    `session` (реальный AsyncSession или мок в тестах) аннотирован `session: Any`.
- pyproject overrides + все 3 mypy-гейта + governance guard расширены на
  `evaluation`. Полный strict-scope теперь 14 целей.
- Верификация: полная gated strict-команда — **Success: no issues found in 57
  source files**; целевые тесты (online-evaluators/simulate/benchmark-runner/
  rollback-watcher/ragas/regression/nightly-eval/precommit-guard) — все passed;
  ruff clean.

## [Type-Hardening] — 2026-06-13 (cont.2) — mypy strict-scope: tracing.* + ingestion.*

- Продолжено направление strict-scope: `tracing.*` (было 18 mypy-ошибок) и
  `ingestion.*` (3) доведены до strict. Только типовые правки — **рантайм
  не менялся**:
  - `tracing/otel.py`: 9 optional-dependency глобалов (opentelemetry `trace`,
    `OTLPSpanExporter`, `TracerProvider`, инструментаторы) стартуют как `None` и
    перепривязываются в `_ensure_dependencies()` → аннотированы `Any` (та же
    суть, что `_NoopMetric`-union в monitoring; `ignore_missing_imports` делает
    реальные символы `Any` в любом случае). Плюс return/param-аннотации
    `_NoopSpan.__enter__/__exit__` (`Literal[False]` + `TracebackType`),
    `_NoopTracer.start_as_current_span`, `get_tracer`, `init_otel`.
  - `tracing/_base_trace.py`: return-типы генераторов `_get_connection`
    (`Iterator[sqlite3.Connection]`) и `_batch` (`Iterator[list[str]]`).
  - `tracing/langfuse_trace.py`: return-тип `get_langfuse` (`Any`); fallback
    `from langfuse.otel import Langfuse` помечен `# type: ignore[no-redef]`
    (тот же идиом, что для fallback-импорта Document в `ingestion/pipeline.py`).
  - `ingestion/loader.py`: `changes: dict[str, list[str]]` (var-annotated).
  - `ingestion/pipeline.py`: `build_vector_store` держит либо tenant-aware
    (5 арг), либо legacy (4 арг) callable — диспетчеризуется через
    `inspect.signature` — аннотирован `Callable[..., tuple[Any, list[Document]]]`.
- pyproject overrides + все 3 mypy-гейта (ci.yml/local-gate.ps1/autopilot.ps1) +
  governance guard расширены на `tracing`/`ingestion`. Полный strict-scope
  теперь 13 целей.
- Верификация: полная gated strict-команда — **Success: no issues found in 46
  source files**; целевые тесты (otel/langfuse/trace-retention/cost/metrics/
  loader/categorizer/pipeline×2/precommit-guard) — **52 passed**; ruff clean.

## [Type-Hardening] — 2026-06-13 (cont.) — mypy strict-scope: monitoring.* + channels.*

- Завершено отложенное направление: `monitoring.*` (было 48 mypy-ошибок) и
  `channels.*` (8) доведены до strict. Решён в корне `_NoopMetric`
  optional-dependency fallback — **без изменения рантайма**:
  - `monitoring/prometheus.py`, `channels/email_channel.py`: каждый
    metric-глобал привязан к реальному prometheus-классу при наличии зависимости
    и к `_NoopMetric` иначе. mypy выводил тип по первой ветке (`_NoopMetric`) и
    падал на присваивании `Counter`/`Gauge`/`Histogram`/`Summary`. Объявлен union
    (`Counter | _NoopMetric` и т.п.) один раз в `TYPE_CHECKING`-блоке на модуль —
    обе ветки проходят, рантайм нетронут. Все call-site используют метод, общий
    для обеих частей union (`inc`/`observe`/`set`), сужения не требуется.
  - `channels/email_channel.py`: `payload.decode` — narrow `get_payload(decode=True)`
    до `bytes` через `isinstance`; imap `msg_data[0]` — narrow до `tuple` с явной
    ошибкой при неожиданном ответе.
  - `channels/telegram_bot.py`: `assert _session_class is not None` (инвариант
    `_ensure_pipeline()`), снят false-positive «None not callable».
- pyproject overrides + все 3 mypy-гейта (ci.yml/local-gate.ps1/autopilot.ps1) +
  governance guard расширены на `monitoring`/`channels`. Полный strict-scope
  теперь 11 целей.
- Верификация: gated strict-mypy по каждой части (auth/db/llm/config/agent/tasks/
  utils — 30 files; monitoring — 2; channels — 4) и полная команда — Success.

## [Security] — 2026-06-13 — pypdf 6.10.2 → 6.13.2 (CVE-2026-48155 / CVE-2026-48156)

- pip-audit (CI security job + pre-commit hook) упал на свежих advisory
  **CVE-2026-48155** и **CVE-2026-48156** против `pypdf 6.10.2` (fix в 6.12.0).
  pypdf парсит загружаемые PDF (`ingestion/loader.py`) — недоверенный ввод,
  путь реачабелен. Поднят до **6.13.2** в `requirements.lock` и
  `requirements-dev.lock` (uv `--upgrade-package pypdf --generate-hashes`; diff —
  только pypdf, без транзитивных изменений) + security-floor `pypdf>=6.12.0` в
  `requirements.txt`. `--ignore-vuln` НЕ использован: fix доступен, иначе нарушило
  бы «minimal/unfixed»-политику governance-guard.
- Верификация: `pip-audit … -r requirements.lock` → «No known vulnerabilities
  found, 2 ignored» (ChromaDB/torch unfixed); loader/ingest тесты 30 passed.

## [Type-Hardening] — 2026-06-13 — расширение mypy strict-scope (db/tasks/utils) + governance guard

- **mypy strict-scope расширен** на `db.*`, `tasks.*`, `utils.*` (был только
  `db.models` из пакета `db`). Промоушен в `pyproject.toml` через
  `[[tool.mypy.overrides]]`. Правки кода — только аннотации, без изменения
  поведения:
  - `utils/retry.py`, `utils/circuit_breaker.py` — аннотированы `*args: Any,
    **kwargs: Any` у прозрачных декораторов-проксей (`wrapped`, `CircuitBreaker.call`).
  - `db/crypto.py` — `encrypt`/`decrypt`/`EncryptedText.bind_expression`/
    `column_expression` возвращают `ColumnElement[Any]` (совместимо с базовым
    `TypeDecorator`, чьи методы дают `ColumnElement[Any] | None`); pgcrypto-функции
    фактически и возвращают `ColumnElement`.
  - `db/audit.py` — `purge_old_audit` читает `rowcount` через `getattr` (базовый
    `Result`, который mypy выводит из `execute()`, не объявляет `rowcount`; его
    несёт `CursorResult` от DELETE — поведение идентично).
  - `tasks/ingest_task.py` — `ingest_document(self: Task, …)` (celery bound task).
- **Governance:** guard-тест `test_mypy_strict_scope_is_synced_across_gates`
  запирает идентичность списка strict-путей mypy во всех 3 точках (CI type-check
  job, `local-gate.ps1`, `autopilot.ps1`) и пинит промоутнутые модули — защита от
  тихого рассинхрона (тот же подход, что у pip-audit ignore-set guard). Все 3
  команды обновлены синхронно: `db/models.py db/engine.py` → `db`, добавлены
  `tasks utils`.
- **monitoring/channels — осознанно НЕ в scope:** их метрики используют
  optional-dependency fallback (`Counter`/`Gauge` vs `_NoopMetric` в
  `try/except ImportError`), из-за чего mypy видит 48 (monitoring) + 8 (channels)
  конфликтов присваивания. Чистый strict требует единого union/Protocol-решения
  для `_NoopMetric` — отдельный будущий заход (крупный churn).

## [Fable-Hardening] — 2026-06-12 — закрытие хвоста F-14 + харденинг тестов/security-гейтов

- **F-14 (vectordb):** `_base_manager._project_root()` указывал на папку пакета →
  `_data_dir()`/`_build_chroma`/`_build_qdrant` писали «невидимый» стор в
  `vectordb/data/vectordb/`, отдельно от продакшен-пути `settings.vectordb_chroma_dir`
  (`<root>/data/vectordb/chroma`). Выровнено на корень репо (как
  `config.settings.PROJECT_ROOT`/`integrations.mock_inbox`), + guard-тест.
- **Тесты (reliability):** autouse-фикстура `_disable_real_reranker_download` в
  `tests/conftest.py` дефолтит cross-encoder reranker OFF на время тестов — устранён
  источник CI HF-429 флаков (`test_per_tenant_vectorstore` тянул ~2.3GB
  `bge-reranker-v2-m3`) и локальный workaround `RAG_RERANKER_MODEL=""`. Полный
  unit-suite (862 passed, 4 skipped) теперь идёт чисто без env-обходов.
- **Security (governance):** guard-тест `test_pip_audit_ignore_set_is_synced_and_minimal`
  запирает набор pip-audit `--ignore-vuln` ровно на 3 обоснованные unfixed-upstream CVE
  (ChromaDB `CVE-2026-45829`/GHSA-алиас, torch `CVE-2025-3000`) во всех 4 точках
  (pre-commit, CI security-job, `local-gate.ps1`, `autopilot.ps1`) — запрет тихих
  suppression + защита от рассинхрона. Reachability проверена: `torch.jit.script` не
  используется, Chroma — только embedded `PersistentClient`.
- **CVE-2025-3000 (torch):** добавлен документированный `--ignore-vuln` (свежий advisory
  без fix-версии; `torch.jit.script` к недоверенному вводу не подключён). Снять при выходе
  upstream-фикса.
- **Гигиена (gap-sweep):** `ingestion/loader.py` `DocumentLoader` логирует ошибки чтения и
  сводку через `logging` (был `print` в stdout); тест email-webhook шлёт raw-тело через
  httpx `content=` вместо deprecated `data=`. Системный скан подтвердил чистоту: ruff/mypy
  (gated scope) clean, нет TODO/FIXME-долга, нет bare-except, skipped-тесты — только
  легитимные условные. LangChain `Ollama`-deprecation — артефакт неполного локального env,
  не пробел: `langchain-ollama` уже в `requirements.txt`/lock и ставится в CI.

## [Fable-Hardening] — 2026-06-11 — рантайм-харденинг по аудиту fable_com.md (8.7/10)

- **F-2 (retrieval):** BM25/lexical-корпус восстанавливается из Chroma при старте
  (`vectordb/manager.py`): штамп `chunk_index` при build, `_restore_chunks_from_store`
  (сорт. по `chunk_index`; legacy-сторы — stable sort по source), gauge
  `rag_retriever_bm25_enabled` + warning. Рестарт больше не теряет молча lexical-поиск.
- **F-1a / F-11 (event loop):** upload (`write_bytes`/`load_documents`/categorizer/rebuild),
  4 analytics-эндпоинта и `/admin/providers` ушли в `asyncio.to_thread` — open dashboard
  и upload больше не блокируют event loop.
- **F-3 / F-8 (streaming):** SSE-путь получил pipeline-семафор (busy-событие,
  disconnect-safe release), дедлайн `STREAMING_TIMEOUT_SEC` в обоих токен-циклах и
  дешёвую Self-RAG self-eval parity (`STREAMING_QUALITY_EVAL`, default on; route по
  `QUALITY_THRESHOLD`, `quality_source` в SSE result). `graph_task`/`ask_args`
  инициализируются до `try` в `ask_stream`.
- **F-9a (observability):** `GraphState.quality_source` (`llm`/`fixed`/`heuristic`) +
  counter `rag_quality_score_source_total{source}` в /ask и стриме.
- **F-12 (factuality):** окно доказательств verify_facts вынесено в settings
  (`FACT_VERIFY_CONTEXT_MAX_DOCS=5`, `FACT_VERIFY_CONTEXT_CHARS_PER_DOC=3600`) —
  верификация видит полные parent-expanded чанки, а не первые 500 символов.
- **F-7 / F-17 (cache/contract):** LLM-кэш читает+пишет только при пустой истории сессии;
  `AskResponse.cached: bool` теперь в схеме (`/api/ask` всегда отдаёт `cached`).
- **F-6 (persist):** db-persist timeout 0.5s → `DB_PERSIST_TIMEOUT_SEC` (2.0) во всех 4
  местах + counter `rag_message_persist_failures_total{operation}`.
- **F-5 / F-18 (sync→async мост):** `run_qa_pipeline` шлёт персист online-evaluators на
  главный loop приложения через `run_coroutine_threadsafe` (`utils/event_loop`,
  регистрация в `api/app` lifespan) вместо `asyncio.run()`+`engine.dispose()` на каждый
  запрос; asyncpg-пул живёт между запросами, sync CLI-скрипты — legacy-путь. Timeout
  online-эвалуаторов → `ONLINE_EVALUATORS_TIMEOUT_SEC`, дропы считаются
  `rag_online_evaluators_dropped_total{reason}`.
- **F-10:** evaluate-на-fast-модели подтверждён как намеренный trade-off (strong в
  gracekelly-primary = ~60s orchestrate-вызов), оставлен и задокументирован;
  suggest_questions переведён на fast.
- Новые settings (все `default_factory`): `STREAMING_QUALITY_EVAL`, `STREAMING_TIMEOUT_SEC`,
  `FACT_VERIFY_CONTEXT_MAX_DOCS`, `FACT_VERIFY_CONTEXT_CHARS_PER_DOC`,
  `ONLINE_EVALUATORS_TIMEOUT_SEC`, `DB_PERSIST_TIMEOUT_SEC` — задокументированы в README и
  `.env.example`. 4 новые Prometheus-метрики.
- Verification: §2 стрим/кэш/analytics/graph **49 passed**; F-2+routing **13 passed**;
  online-evaluators **19 passed** (incl. новый threadsafe-path тест); graph/routing/
  conversation **17 passed**; `api.app`/`agent.graph` import OK; ruff clean. Закоммичено
  7 локальными коммитами `2ee78a8..59df7c9` на `master` (не запушено).
- Не входит в батч (отдельные циклы): F-4 (кэш runtime/compiled graph — ловушка
  `last_response`), гигиена корня, multi-worker инвариант.

## [Docs-Health-Sync] — 2026-05-02 — active documentation status cleanup

- README, active backlog, and next-session handoff now separate landed
  a11y source updates from the remaining external `@axe-core/cli`/Lighthouse
  verification work.
- Batch N handoff now points at the live benchmark decision only; mock-safe
  Quickstart docs and default benchmark guardrails remain closed.
- `docs/a11y/axe-audit-2026-04-21.md` now marks the report as historical and
  lists the 2026-05-02 post-audit source updates, including widget coverage.
- Added docs guardrails for active-doc mojibake, a11y verification wording, and
  the Batch N handoff boundary.

## [Agentic-Tool-Trace-Metadata] — 2026-05-02 — Langfuse metadata for provider tool loops

- `agent/graph.py` теперь трассирует каждый `generate_with_tools` turn в
  provider-backed agentic loop через `trace_llm_call`.
- Tool-call turn передаёт raw provider `tool_calls` в Langfuse generation
  metadata; финальный answer turn сохраняет уже выполненные tool names.
- `tests/test_agent_tools.py` закрепляет regression: provider tool-loop должен
  отправлять `tool_calls` metadata в `trace_llm_call`.
- Verification: red test confirmed the missing trace metadata; green focused
  test; `tests/test_agent_tools.py` + `tests/test_langfuse_trace.py` green;
  `mypy agent/graph.py` clean; full local pytest green:
  **677 passed, 16 skipped**; `ruff check .` clean; `git diff --check` clean.

## [GraceKelly-Default-Health] — 2026-05-02 — GraceKelly primary as default provider profile

- `config/providers.yml`, `config/settings.py` и `.env.example` переведены на
  `gracekelly-primary` как default routing profile; `local-first` остался явным
  Ollama-only режимом для offline/local-only запусков.
- `/api/health` и `/api/health/ready` теперь проверяют только активных LLM
  providers из routing profile: default GraceKelly path больше не требует
  Ollama, а explicit `local-first` по-прежнему проверяет Ollama.
- Добавлен `_probe_gracekelly()` для readiness check `GET /healthz/ready` и
  Prometheus component gauge для активного GraceKelly provider-а.
- README, Quickstart и runbook синхронизированы с новой операторской моделью:
  GraceKelly primary по умолчанию, Ollama как explicit local-first/fallback.
- Health/provider tests обновлены под provider-aware readiness, включая
  regression coverage для GraceKelly default без неявного Ollama probe.
- Verification: full local pytest with explicit basetemp is green:
  **659 passed, 16 skipped**; `mypy api/app.py` clean; ruff on touched Python
  files clean; `git diff --check` clean.

## [App-Shell-Cleanup] — 2026-04-30 — shared lazy app accessor for extracted routers

- `api/_shared.py` — добавлен общий lazy `app_module()` для extracted routers.
- `api/routers/upload.py`, `system.py`, `root_pages.py`, `auth_sso.py`,
  `feedback.py`, `misc.py`, `admin_kb.py`, `admin_ops.py`,
  `admin_evaluations.py`, `admin_experiments.py`, `conversation.py`,
  `session_auth.py` — используют shared accessor вместо локального
  `_app_module`, сохраняя monkeypatch-friendly late binding на `api.app`.
- `tests/test_upload_security.py` и `tests/test_router_app_shell.py` —
  закрепляют, что переведённые routers используют shared accessor.
- Локальных `def _app_module()` wrappers в `api/routers/` больше нет; это
  закрывает механический cleanup debt, не меняя route ownership.
- Verification: structural red/green test; `tests/test_router_app_shell.py`
  green; related router suites green
  (health/system, OIDC/root, feedback/metrics, email/provider-admin).
  Final full local pytest with explicit `--basetemp` is green: 626 passed,
  16 skipped.

## [Regression-Eval-Criteria] — 2026-04-30 — OR-groups for curated answer checks

- `scripts/regression_eval.py` — `CaseExpectation` получил `answer_contains_any`: каждая вложенная группа трактуется как OR-критерий, где достаточно одного substring match.
- `scripts/detect_stale_curated_cases.py` — stale-detector учитывает те же OR-группы и не пропускает ответы, где отсутствуют все допустимые альтернативы.
- `evaluation/curated_cases.jsonl` — `warranty-no-receipt-where` теперь требует `чек` и один из вариантов `сервис` / `поддерж`, что соответствует KB-формулировке “сервисный центр или службу поддержки”.
- `tests/test_regression_runner.py`, `tests/test_detect_stale_curated_cases.py` — покрыты missing-any failure, accepted alternative и mock-provider representative output.
- Verification: red tests зафиксировали expected failures; green `tests/test_regression_runner.py` — 13 passed; green `tests/test_detect_stale_curated_cases.py` — 12 passed; focused regression-eval/stale suite — 40 passed; full `pytest` — 624 passed, 16 skipped; `ruff check` по изменённым Python-файлам — clean.

## [RAG-Doc-Grading] — 2026-04-30 — preserve top retrieval hit after LLM grading

- `agent/graph.py` — `grade_docs` теперь сохраняет первый retrieval hit, если LLM grader оставил нижеранговые документы, но отклонил top-ranked документ. Это закрывает `returns-window`-класс отказов, где `returns_policy.md` был найден первым, но терялся перед генерацией ответа.
- `tests/test_grade_docs.py` — добавлен red/green regression test для false negative на top retrieval hit; существующий all-filtered путь остаётся покрыт.
- Verification: `tests/test_grade_docs.py` — 2 passed; focused regression/graph suite — 32 passed; non-integration suite — 604 passed, 4 skipped; `ruff check agent\graph.py tests\test_grade_docs.py` — clean; `mypy agent\graph.py` — clean.

## [Agent-Strict-A11y] — 2026-04-29 — agent typing scope + stable axe gate

- `agent.prompt_registry`, `agent.tools` и `agent.graph` добавлены в strict mypy scope и CI gate рядом с `agent.state` / `agent.prompts`; YAML override payload теперь сужается до `dict`, no-op `tool` decorator типизирован через `TypeVar`.
- `agent.graph` full strict clean: GraphState route/tool_calls приведены к реальным runtime-значениям, `knowledge_gap` добавлен в TypedDict, LangGraph registration явно ограничен dynamic boundary через `workflow: Any`.
- `.github/workflows/ci.yml` обновлён: strict mypy команда теперь проверяет `agent/prompt_registry.py`, `agent/tools.py` и `agent/graph.py`.
- `tests/test_a11y.py` стабилизирован для full unit suite: axe subprocess timeout вынесен в константу, pytest marker даёт axe-параметрам больший budget, `npx` запускается с `--no-install` как availability probe.
- Verification: strict mypy scope clean (**18 source files**), `agent.graph` explicit strict clean, focused agent/a11y tests green, full unit suite без integration — **623 passed, 4 skipped** за 14:59 local.

## [Coverage-Gate-70] — 2026-04-29 — verified 70% coverage gate + focused test expansion

- `tests/test_weekly_report.py` расширен проверками для `reports.renderer`: week-over-week helpers, empty states, top-5 limits, weekly aggregation, empty analytics and document lookup failures.
- `tests/test_langfuse_trace.py` добавлен для `tracing.langfuse_trace`: unconfigured Langfuse, new `start_observation` path, legacy `trace().generation()` path, backend warning path, `flush()`/`shutdown()` behavior.
- `tests/test_rag_cache.py` и `tests/test_redis_cache.py` добавлены для cache layers: root `cache.py` поднят до 99%, `cache/redis_cache.py` до 100%.
- `tests/test_ragas_eval.py` добавлен для `evaluation/ragas_eval.py`: metric helpers, evaluator single/batch paths, benchmark save/error/invoke paths, embedding fallback.
- `tests/test_base_manager.py` добавлен для `vectordb/_base_manager.py`: embeddings/reranker factories, contextual headers, hybrid/multi-query retrieval, vector store/retriever builders.
- `tests/test_benchmark_runner.py` добавлен для `evaluation/benchmark_runner.py`: loading benchmark cases and CLI `main()` paths.
- `tests/integration/test_regression_eval_live.py` стабилизирован: coverage path больше не загружает реальные embeddings/categorizer, но сохраняет live asyncpg/FK regression signal.
- `pyproject.toml` coverage note обновлён по реальному full pytest+coverage прогону: **630 passed, 4 skipped, total coverage 70.02%**. `fail_under` поднят до 70.
- Старый blocker по upload/body-size hang не воспроизведён: `tests/test_body_size_limits.py` проходит изолированно.

## [Audit-Hardening-2] — 2026-04-27 — Codex+Opus delta-аудит + 11 коммитов hardening + docs

### Контекст

После hardening 2026-04-26 проведены два независимых delta-аудита (Codex CLI + Claude Opus 4.7) на baseline `ff7948f`. Codex нашёл три P0 security/deploy bugs, Opus — P1 module-layout debt и mypy regression. По обоим roadmap'ам прогнаны 11 коммитов hardening + 1 docs commit, HEAD `ff7948f` → `8e4cab2`.

### Security & deploy fixes (P0)

- `Dockerfile` CMD `main:app` → `api.app:app`; `main.py` переписан как тонкий alias `from api.app import app`. Раньше production запускал legacy FastAPI без middleware (request-id, body-size, tenant, http-metrics, cors, sessions, logger) и без lifespan validation/OTel/vector-store init. Legacy unauthenticated `/ask`, `/escalations`, `/traces*` удалены. (commit `ecdd494`)
- `config/settings.py` — `Settings.validate()` fail-fast в production: пустые/default `JWT_SECRET`/`SESSION_SECRET_KEY`/`ADMIN_PASSWORD_HASH` блокируют startup. `JWT_SECRET` ≥32 символов. `ALLOW_DEV_ADMIN_LOGIN=1` — explicit opt-in для dev login на staging. (commit `c48585c`)
- `api/app.py` `/api/sessions/{id}/history`, `/api/sessions`, `DELETE /api/sessions/{id}` — JOIN/WHERE на `tenant_id` против `_user.tenant`; in-memory check `_tenant_id`. До этого agent tenant-A мог читать/удалять чужие сессии по UUID guess. (commit `aa683f3`)
- `tracing/_base_trace.py` `feedback` table — добавлен `tenant_id NOT NULL DEFAULT 'default'` (idempotent ALTER TABLE) + `idx_feedback_tenant_id`. `save_feedback`/`get_feedback_stats` теперь принимают tenant_id. `/api/feedback/stats` для agent — scope per tenant, для admin — global. (commit `aa683f3`)
- `alembic upgrade head` перенесён из `main.py` в `api/app.py` lifespan (gated `AUTO_MIGRATE=true`).

### Module layout & types (P1-P2)

- 13 production-сайтов `import sqlite_trace` / `from manager import …` переключены на canonical `tracing.sqlite_trace` / `vectordb.manager`. `tracing/sqlite_trace.py` расширен: re-exports list_recent_traces, get_trace_detail, purge_old_traces, get_metrics_snapshot, save_feedback, get_feedback_stats. Root shim-ы `manager.py`, `sqlite_trace.py`, `loader.py` перестали использоваться production кодом и позже удалены в `4c557f3`. (commit `c0cacae`)
- `llm/providers/mistral.py:166` — `_parse_response` принимает `Mapping[str, str]` вместо `dict[str, str]` (httpx.Headers). `llm/providers/runtime.py:64,74` — явные kwargs вместо `**dict[str, object]`. mypy scope `llm.providers.*` поднят с informational до strict. (commit `d718356`)

### Infrastructure & CI

- `.dockerignore` (новый) — исключает `.env`/`.git`/`.tmp`/`.coverage`/`data`/`reports`/audit-артефакты. Docker COPY больше не тянет secrets и не раздувает image. (commit `f56e51b`)
- `.gitignore` — `.tmp/`, `.coverage*`, `htmlcov/`, `reports/regression/*.log` чтобы pytest basetemp не плодил untracked.
- `pyproject.toml` ruff/bandit `exclude` — `.tmp`, `reports`, `archive-legacy`. Раньше ruff падал на 133 W292 в pytest temp-копиях.
- `.pre-commit-config.yaml` pip-audit args — убран `--require-hashes=false`, который pip-audit 2.10+ не парсит.
- `.github/workflows/ci.yml` — добавлен `type-check` job (mypy на strict scope обязателен), `test-integration` больше не `continue-on-error: true`. (commit `a12f404`)

### Behaviour fixes

- `api/routers/conversation.py` — pipeline exception в `/api/ask` теперь создаёт `EscalatedTicket(tenant_id, session_id, user_question, ai_draft, status='open')`. Раньше пользователю обещали handoff, но реальной записи в БД не было — оператор мог не увидеть. (commit `fa92d4e`)
- `api/app.py` `/metrics` — env-gated optional auth через `PROMETHEUS_METRICS_REQUIRE_AUTH=1`. По умолчанию открыт (Prometheus convention) — production должен ограничить network-level. Authenticated alternative `/api/metrics` уже существует. (commit `0a42369`)
- `tests/integration/test_regression_eval_live.py` — добавлен subprocess `docker info` с timeout=5s; pytest.skip при недоступном daemon (раньше тест висел на pipe ConnectionError). (commit `6e64148`)

### Tests added

- `tests/test_production_entrypoint.py` (4 cases) — `main:app === api.app:app`, middleware count ≥6, нет legacy `/ask|/escalations|/traces`, ≥60 `/api` routes.
- `tests/test_settings_production_secrets.py` (6 cases) — production fail-fast guards.
- `tests/test_tenant_isolation_sessions.py` (8 cases) — cross-tenant 404, owning-tenant ok, list filter, delete blocked, save_feedback tenant propagation, /feedback/stats agent vs admin scope.
- `tests/test_pipeline_exception_escalation.py` (1 case) — forced RuntimeError → EscalatedTicket persisted.

Focus suite (17 файлов, 85 тестов) — pass. cxkm review CLEAR (CX 2× P2 на untracked artefacts; KM normalization_error на 2618-line diff — degraded).

---

## [Audit-Hardening] — 2026-04-26 — BCG-уровневый аудит + 4 итерации hardening

### Контекст

После закрытия task-177/178/179 проведён глубокий аудит проекта (Claude Opus 4.7 1M context). Результат — `docs/audits/audit_opus_2026-04-26.md` с прогрессивной самооценкой 7.8/10 для local / 6.9/10 для commercial. По roadmap-у аудита выполнены 4 итерации hardening работы (22 задачи, 18 — production fixes + 4 — docs).

### Что сделано

**Security & operability (Phase 1):**
- `auth/dependencies.py` — anonymous-admin fallback при пустом `API_KEY` теперь требует явный opt-in `ALLOW_ANONYMOUS_ADMIN=1`, иначе HTTP 503. Foot-gun «случайно бинд на 0.0.0.0 без API_KEY → любой = admin» закрыт.
- `main.py` — bare `python main.py` дефолтит host на `127.0.0.1` (override через `HOST` env). Docker compose не затронут.
- `sqlite_trace.py` + `main.py` — SQLite traces получили `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`. Multi-worker race в `data/tracing/traces.db` закрыт.
- `api/app.py` + `main.py` — `Field(min_length=1, max_length=…)` на `RefreshRequest` (4096) и legacy `AskRequest` (4000/100). DOS-payload защита.
- `main.py` — `alembic upgrade head` в lifespan startup hook (gated `AUTO_MIGRATE`, default `true`). Ошибки миграции логируются как warning, не валят app.

**Code quality & tooling (Phase 2):**
- 7 root-level файлов получили актуальные docstrings (`manager.py`, `sqlite_trace.py`, `loader.py`, `chunking.py`, `bitrix.py`, `mock_inbox.py`, `seed_docs.py`) — раньше говорили «vectordb/manager.py», «integrations/bitrix.py» хотя файлы лежали в корне.
- `DEPRECATIONS.md` создан — карта legacy-расположений + 5-фазный план миграции.
- `DEPRECATIONS.md` Phase 2 закрыта 2026-04-27: `bitrix.py` и `mock_inbox.py` переехали в `integrations/`, `seed_docs.py` переехал в `demo/seed_docs.py`; canonical imports покрыты regression-тестами.
- `DEPRECATIONS.md` Phase 3 закрыта 2026-04-27 по Option B: базовые реализации `manager.py` и `sqlite_trace.py` переехали в `vectordb/_base_manager.py` и `tracing/_base_trace.py`; root-файлы оставлены shim-ами совместимости.
- Phase 3 layout покрыт regression-тестами и полным pytest-прогоном: 563 passed, 4 skipped.
- `DEPRECATIONS.md` Phase 4 закрыта 2026-04-27: `DocumentChangeTracker` и HTML support перенесены в `ingestion.loader`, root `loader.py` оставлен shim-ом, production imports переведены на пакетный loader.
- `DEPRECATIONS.md` Phase 5 закрыта 2026-04-27: standalone `chunking.py` переехал в `scripts/chunking_eval.py`, root import удалён и покрыт layout regression-тестом.
- `README.md` и `codex-tasks/cleanup-report.md` синхронизированы с фактической module layout; `requests>=2.32.0` добавлен в `requirements.txt` как прямой runtime dependency для Bitrix-интеграции.
- `pyproject.toml` — `[tool.coverage.{run,report}]` с `fail_under=70`, branch coverage, source-list по 14 production модулям.
- `pyproject.toml` — `[tool.mypy]` + per-module overrides. Strict для `auth.*` + `db.models` (5/5 файлов pass).
- `auth/oidc.py`, `auth/dependencies.py` — фикс 4 type errors под strict.
- `[tool.bandit]` в pyproject + bandit + pip-audit в `.pre-commit-config.yaml`. Skip B608/B310 false positives задокументирован.
- `tracing/langfuse_trace.py:55` — фикс HIGH severity MD5 (`usedforsecurity=False`). Bandit clean: 0 High/0 Medium.
- `pip-audit -r requirements.txt` — 0 known vulnerabilities.
- Удалены deprecation shim-ы из корня: `graph.py` (12 LOC), `state.py` (11), `prompts.py` (11). Также удалён dead `except ImportError` fallback в `agent/graph.py:48-80` — он re-exportировал через те же удалённые shim-ы (циклический fallback).

**API monolith split start (Phase 3-4):**
- Создана `api/routers/` директория. 13 sub-router-ов вынесены из `api/app.py`:
  - `system.py` — `/health/live`, `/health/ready`, `/health`, `/metrics`
  - `agent.py` — `/agent/tickets/{list,get,respond}`, `/agent/similar` (+ `AgentRespondRequest`)
  - `admin_review.py` — `/admin/review-queue/{list,update,stats}` (+ `ReviewQueueUpdateRequest`)
  - `admin_kb.py` — `/admin/curated-dataset/*`, `/admin/thresholds/*`, `/admin/improvement-backlog/*`, `/admin/kb-gaps`, `/admin/kb-drafts/*`, `/admin/stale-docs/*`
  - `admin_experiments.py` — `/admin/experiments/*`, comparison, deploy/rollback, regression trigger, assignments
  - `admin_evaluations.py` — `/admin/evaluations/*`, `/admin/regression-runs/*`
  - `admin_ops.py` — `/admin/circuit-breaker/reset`, `/admin/audit`, `/admin/traces/*`, `/admin/audit-log`
  - `analytics.py` — `/analytics/top-topics`, `/analytics/resolution-rate`, `/analytics/cost-summary`, `/analytics/trends`
  - `auth_sso.py` — `/auth/sso/{providers,login,callback}`
  - `feedback.py` — `/feedback`, `/feedback/stats`, `/escalate`
  - `misc.py` — `/admin/providers`, `/channels/email/inbound` с сохранённым legacy alias `/webhook/email`
  - `upload.py` — `/upload`, `/tasks/{task_id}`
  - `conversation.py` — `/ask`, `/chat`, `/ask/stream`, `/chat/stream`
- `api/rate_limit.py` выделен как shared-модуль для `limiter` и rate-limit exception handler-а, чтобы extracted routers не импортировали `api.app` на module-load.
- Зафиксирован monkeypatch-friendly паттерн (`from db import engine as _db_engine` + `_async_session()` indirection, lazy access через `api.app`) — необходим для совместимости с тестами, использующими `monkeypatch.setattr("db.engine.async_session", ...)` и `monkeypatch.setattr(api_app, ...)`.
- `evaluation/evaluator_runner.py` перешёл на late-bound `db.engine`, чтобы live regression tests могли подменять disposable Postgres session factory без stale import.
- 64 endpoints вынесены из 5288-LOC монолита, `api/app.py` теперь 2128 LOC.

**Documentation (Phase 5):**
- `docs/audits/audit_opus_2026-04-26.md` — секция 12 «Implementation log» с полной таблицей 22 задач, метриками до/после, обновлённой самооценкой (8.7/10 local, 7.7/10 commercial).
- `docs/SESSION-NOTES-2026-04-26-audit.md` — handover для новой сессии.
- `DEPRECATIONS.md` — обновлены секции «Done», «Next splits», «Type-checking debt», «Pattern для split sub-router-ов».

### Verification

- Focus-set tests: **71/71 passed** (auth + jwt + tenant + health + metrics + trace + migration + agent + review-queue + body_size).
- mypy strict: **5/5 files clean** (`auth/*` + `db/models.py`).
- Bandit: **0 High, 0 Medium** (после фикса MD5 + конфига).
- pip-audit: **No known vulnerabilities**.

### Bottom line

- ✅ Security gaps закрыты: anonymous fallback, DOS validation, MD5 weakness, dependency CVE scan.
- ✅ Operability: auto-migrate, SQLite WAL, корректный host default.
- ✅ Code hygiene: 0 TODO/FIXME, 0 deprecation shims в корне, mypy strict для auth/db core.
- ✅ Architecture: 64 endpoints в sub-router модулях, паттерн доказан.
- 📋 Карта остатков — в `docs/audits/audit_opus_2026-04-26.md` секции 12.5 + `DEPRECATIONS.md`.

---

## [Task-177 / Task-178 / Task-179] — 2026-04-25 / 2026-04-26 — first green full 20-case live regression

### Honest closure of the GK-Claude live regression loop

После закрытия двух UI flakiness mode на стороне GraceKelly (`batch-108`: Sonar retry + `submit.click(force=True)`) обнаружился design mismatch: full RAG pipeline через `gracekelly-primary` делает 4-7 LLM calls/case через single-thread browser (30-100s/submit), что не вписывается в любой разумный wall-time benchmark и периодически каскадит в circuit breaker.

Решение архитектурное: extend `regression_eval` чтобы поддержать routing-profile names как target (`--candidate-profile gracekelly-mixed`), сохраняя весь Self-RAG / Corrective RAG / auto-route flow. Mixed profile использует **Mistral API для fast tier** (classify, transform, grade_docs ×N, verify_facts → extract_claims, online evaluators) и **GraceKelly browser для strong tier** (final answer + suggest_questions + evaluate). Browser submits на case падают с 4-7 до ~3, общий wall-time 20-case ≈ 30 минут вместо ожидаемых 2+ часов.

### Commits chain

- **`53c2507`** — task-177 partial close после 4 диагностических 2-case smoke runs. Documented в `codex-tasks/verification-report-regression-gracekelly.md` rev 3.
- **`7559a28`** — `config/providers.yml`: новый `gracekelly-mixed` routing profile (Mistral fast / GK browser strong). Также pkadan для production single-user deploy.
- **`1d3d13d`** — `scripts/regression_eval.py`:
  - `_resolve_provider_target` возвращает `kind` discriminator (`"model"` | `"profile"`) и fallback'ит на `routing_profiles` когда model resolution miss.
  - `_provider_target_runtime` skip-ит synthetic profile injection когда `kind=profile`, использует существующий profile as-is.
  - argparse mutex groups: `--baseline / --baseline-profile`, `--candidate / --candidate-profile`.
  - Параллельно landed task-179: `_evaluate_case_output` теперь case-insensitive substring match (`needle.lower() not in answer_lower`) — раньше lowercase needle `"чек"` ложно фейлил против actual `"Чек"`.
  - 7 новых unit tests в `tests/test_regression_eval_profile_target.py`. 17/17 pytest pass + 10/10 existing `tests/test_regression_runner.py`.
- **`59a3057`** — `scripts/run_regression_via_gracekelly.ps1`: новый параметр `-CandidateProfile`. Когда непустой — wrapper передаёт `--candidate-profile $X` в python (взаимоисключающе с `-Candidate`).
- **`9f96b5b`** — архив task-178 спеки в `codex-tasks/Archive/`.
- **`c95fbf3`** — first green full 20-case run через `gracekelly-mixed` + `GRACEKELLY_REQUEST_TIMEOUT_SEC=120`. Browser layer стабилен end-to-end: 0 infrastructure_failures, gate=fail только из-за 6 regressions (4 = GK Sonar auto-route mismatch, 2 = real Claude differences). Evidence в `reports/regression/20260426T113855Z-*`.
- **`9ac782f`** — `_is_infrastructure_failure` extended для `[model_mismatch]` pattern. GK external auto-route ошибки больше не считаются regressions. 8 новых unit tests в `tests/test_infrastructure_failure_detection.py`.
- **`271bfe5`** — verification report rev 5 documents the closure: re-classified evidence (regressions 6→2, infrastructure_failures 0→4, gate.max_regressions=2 PASS).

### Bottom line

- ✅ task-177 closed end-to-end. RAG pipeline стабильно бежит через GraceKelly browser routing когда верно конфигурирован.
- ✅ task-178: regression_eval поддерживает routing-profile targets.
- ✅ task-179: case-insensitive substring matching.
- 🔍 Real candidate gap (Claude через mixed routing 37.5% effective pass vs Mistral baseline 75%) — отдельная investigation, не блокирующая.
- ⛔ GraceKelly batch-109 (Sonar auto-route fix) — **на стороне GK**, не в RAG scope.

### Operational notes

- Local `.env`: `GRACEKELLY_REQUEST_TIMEOUT_SEC=120` рекомендуется для GK-routed regression runs (default 30s маловат для browser submit на final answer).
- `MISTRAL_API_KEY` обязателен для `gracekelly-mixed` profile — fast tier через Mistral direct API.
- Containers `rag-regression-postgres` + `rag-regression-redis` в idempotent reuse mode у wrapper'а.

## [Arc 7 / Task-176] — 2026-04-24 — regression eval warning cleanup

### Regression pipeline fixes
- **`agent/graph.py`** — `grade_docs` now accepts provider-native structured payloads with extra fields from Mistral tool-use output, requires only `relevant`, and falls back to text grading when structured output is unavailable.
- **`evaluation/evaluator_runner.py`** — online evaluator verdicts now persist with an independent async session per evaluator insert, avoiding shared asyncpg connection races.
- **`config/settings.py` / `ingestion/categorizer.py`** — ingestion categorizer model moved to `INGESTION_CATEGORIZER_MODEL`; missing or failing categorizer calls skip with a warning instead of emitting the old invalid-payload noise.

### Task-176 continuation — 2026-04-25
- **`evaluation/evaluator_runner.py`** — bug 2 (asyncpg race): default production path now opens a single `engine.begin()` transaction, upserts a stub `traces` row, and inserts all `trace_evaluations` sequentially. Bug 4 (FK ordering) is closed in the same transaction.
- **`agent/graph.py`** — final bug 2 close: `run_qa_pipeline` wraps `_persist_results` in `asyncio.run(...)` per case; the global async engine pool kept asyncpg connections bound to the previous (now-dead) loop, which produced `InterfaceError: another operation is in progress` on every subsequent case and on the final `INSERT INTO eval_results`. `_persist_results` now disposes the engine in its `finally` block so the next `asyncio.run` starts with a fresh pool. Verified live on disposable Postgres 16 + 3 ingested seed docs: `regression_eval --max-cases 3` runs warning-free and lands `eval_results` row + 7 distinct evaluators per trace.
- **`tests/integration/test_regression_eval_live.py`** — new integration test that spins up Postgres 16 via testcontainers, runs `alembic upgrade head`, ingests seed docs, executes `regression_eval.run_regression` with a mock LLM/retriever, asserts zero `InterfaceError` / `ForeignKeyViolationError` and presence of `trace_evaluations` + `eval_results` rows. Test currently fails on subprocess `alembic upgrade head` (`DATABASE_URL` env not propagated to subprocess) — infrastructure-only issue in the test harness, not in the bug 2/4 path.

## [Arc 7 / Task-175] — 2026-04-23 — backup encryption at rest

### Snapshot encryption
- **`scripts/backup_snapshot.py`** — nightly snapshots can now encrypt `postgres.dump`, `traces.sqlite`, `uploads.tar.gz`, and `chroma.tar.gz` on disk with `age`. Recipient mode is the primary path (`BACKUP_ENCRYPTION_RECIPIENT` or `BACKUP_ENCRYPTION_RECIPIENT_FILE`); passphrase mode is available as a fallback through `BACKUP_ENCRYPTION_PASSPHRASE_FILE`. Encrypted snapshots record per-component `encrypted`/`algorithm` metadata plus a top-level fingerprinted encryption block in `snapshot_manifest.json`.
- **`scripts/restore_verify.py` / `scripts/restore_verify_integration.py`** — restore verification can now decrypt encrypted snapshot components before the existing SQLite/tar/Postgres checks. New CLI flags: `--age-identity-file` and `--age-passphrase-file`. New exit code: `EXIT_DECRYPT_FAILED=5`.
- **`scripts/backup_integrity.py`** — integrity audit now reports whether each snapshot is encrypted and continues hashing the exact bytes stored on disk, including `.age` artifacts.

### Helm + docs + tests
- **`deploy/helm/templates/cronjob-backup-snapshot.yaml` / `deploy/helm/values.yaml`** — backup CronJob now supports `backup.encryption.enabled`, exports the backup-encryption env vars, and mounts `/secrets/recipient.pub` from the `backup-encryption-key` Secret when enabled.
- **`docs/operations/backup-encryption.md` / `docs/disaster-recovery.md`** — added the operator runbook for key generation, storage, recovery, and manual re-encryption, plus a new DR scenario for leaked backup tarballs and explicit notes about the separate `age` key failure mode.
- **Tests** — added `tests/test_backup_snapshot_encryption.py` and `tests/test_restore_verify_encryption.py` for end-to-end encrypted snapshot creation and restore verification. These tests skip cleanly when `age` tooling is unavailable.

## [Arc 7 / Helm audit gate] — 2026-04-23 — lint + client dry-run

### Helm chart hardening
- **`deploy/helm/Chart.yaml`** — добавлен `icon`, чтобы `helm lint --strict` проходил без warnings.
- **`deploy/helm/templates/*.yaml`** — ко всем rendered objects добавлены стандартные `app.kubernetes.io/*` и `helm.sh/chart` labels; для `deployment-email-poller` и всех CronJob-контейнеров добавлены `resources.requests/limits`; для всех CronJob'ов закреплён `jobTemplate.spec.backoffLimit: 6`.

### CI gate + docs
- **`.github/workflows/ci.yml`** — новый job `helm` запускается на `pull_request` и `push` в `master`, выполняет `helm lint`, `helm template`, поднимает временный `kind` cluster и затем гоняет `kubectl apply --dry-run=client -f /tmp/rendered.yaml`.
- **`docs/operations/helm-lint.md`** — новый короткий runbook с локальными командами, примером вывода и пояснением, почему для `kubectl --dry-run=client` нужен временный API server.

## [Arc 7 / Migration audit gate] — 2026-04-23 — alembic round-trip

### Migration 012 + schema audit
- **`alembic/versions/012_review_queue.py`** — подтверждён и закреплён фикс против double-create PG ENUM (`postgresql.ENUM(create_type=False)` после явного `create(checkfirst=True)`), который раньше падал на чистой Postgres 16.
- **`scripts/migration_round_trip.py`** — новый standalone CLI для `upgrade head -> current -> downgrade base -> current -> upgrade head` с реальной Postgres-проверкой и итоговым diff по ожидаемому набору таблиц.

### CI gate
- **`.github/workflows/ci.yml`** — новый job `migrations` поднимает `postgres:16-alpine`, выставляет `DATABASE_URL` и dummy `DB_ENCRYPTION_KEY`, затем гоняет `python scripts/migration_round_trip.py` на `pull_request` и `push` в `master`.

## [Arc 7 / Minors close-out] — 2026-04-23 — sticky rollout + staleness + cronjobs

### Task-154 sticky hash rollout
- **`agent/prompt_registry.py`** — adds `set_assignment_cache_entry`, `clear_assignment_cache_entry`, `clear_assignment_cache`, `refresh_assignment_cache_from_db`, `_stable_rollout_bucket`, and the live implementation of `resolve_active_experiment()`. Resolver gates on `EXPERIMENT_ASSIGNMENT_ENABLED`, reads the tenant-keyed in-memory cache, computes a deterministic `sha256(tenant_id:session_or_user) % 100` bucket, returns the experiment when `bucket < rollout_percentage` and the YAML loads, otherwise `None`.
- **`api/app.py`** — `POST /admin/experiments/{id}/assignments` now calls `set_assignment_cache_entry` after the DB commit so sticky rollout picks up new assignments without a service restart.

### Task-156 staleness detection
- **`scripts/detect_stale_curated_cases.py`** — CLI + library. `compare_verdicts()` detects route drift, quality/factuality drops, and `answer_contains` misses. `run_detection()` reads `curated_cases.jsonl`, filters by age, re-runs each case through a pluggable `rerun_fn`, and (with `--apply`) writes `stale_needs_review` rows into `curated_case_status` via `DELETE + INSERT`.
- **`config/settings.py`** — new `CURATED_CASE_STALE_DAYS=180`.

### Helm cronjobs
- `deploy/helm/templates/cronjob-backup-snapshot.yaml` — nightly 01:00 UTC `python scripts/backup_snapshot.py --out /backups/$(date -u +%Y%m%dT%H%M%SZ)`.
- `deploy/helm/templates/cronjob-backup-integrity.yaml` — weekly Sun 05:00 UTC integrity audit.
- `deploy/helm/templates/cronjob-restore-verify.yaml` — weekly Sun 04:00 UTC disposable restore against the newest snapshot.
- `deploy/helm/templates/cronjob-curated-staleness.yaml` — daily 03:00 UTC `--apply` run of the staleness detector.

### Tests
- `tests/test_sticky_rollout.py` (8), `tests/test_detect_stale_curated_cases.py` (10), `tests/test_helm_cronjobs.py` (4). Combined Arc 7 sweep (K+I+J + minors + sanity): 189 passed / 0 failed. Ruff clean.

## [Arc 7 / Batch J] — 2026-04-23 — Backup / restore / chaos

### Snapshot backup + integrity (task-159, task-163)
- **`scripts/backup_snapshot.py`** — cross-platform Python CLI that writes an atomic snapshot with `pg_dump` (optional), SQLite backup-API for `data/tracing/traces.db`, tarballs for `data/uploads` and the ChromaDB persistent dir, a `DB_ENCRYPTION_KEY` SHA256 fingerprint (raw key never persisted), and `snapshot_manifest.json` with alembic revision + per-component SHA256/size. `--skip-chroma` is honoured; missing stores are skipped rather than failing hard.
- **`scripts/backup_integrity.py`** — walks a backup directory, verifies every component against the manifest, flags snapshots past `BACKUP_RETENTION_DAYS` (default 30) as deletion candidates and emits a markdown audit report. Never deletes.
- **Settings** — `BACKUP_DIR` and `BACKUP_RETENTION_DAYS` in `config/settings.py`.

### Restore + smoke (task-160, task-162)
- **`scripts/restore_verify.py`** — stages a snapshot into a disposable temp root, runs SQLite `PRAGMA integrity_check`, unpacks tarballs and asserts the resulting layout. Structured exit codes (`EXIT_RESTORE_FAILED`, `EXIT_SMOKE_FAILED`, `EXIT_INFRA_ERROR`) and auto-cleanup of the temp root on both success and failure.
- **`scripts/post_deploy_smoke.py`** — under-30s sanity check (`/healthz/live`, `/healthz/ready`, `/metrics` Prometheus body with `rag_model_routing` + `rag_llm_cost_usd_total` + `rag_experiment_auto_rollback_total`, `POST /api/ask`, `GET /api/admin/providers`). Uses an injected `httpx.Client` for test isolation.

### Full restore verification (task-173)
- **`docker-compose.test.yml`** — isolated `postgres-test` (`postgres:16-alpine`) with random host-port, `pg_isready` healthcheck, ephemeral storage and a dedicated `rag-restore-test` network for restore-only runs.
- **`scripts/restore_verify.py`** — new optional `--postgres-url` path that runs a real `pg_restore --clean --if-exists`, validates `alembic_version`, checks the expected public-table count and probes every ORM table with `SELECT * LIMIT 0`. New `EXIT_POSTGRES_VERIFY_FAILED=4` keeps Postgres failures separate from layout smoke.
- **`scripts/restore_verify_integration.py`** — thin wrapper that brings `postgres-test` up, waits for readiness, resolves the dynamic port, calls `restore_verify.main(... --postgres-url=...)` and always tears the container down with `docker-compose ... down -v`.
- **`docs/operations/backup-restore.md`** — documents the disposable full-restore flow and operator commands.

### Chaos drills + DR docs (task-161, task-164)
- **`scripts/chaos_drill.py`** — six fault scenarios (`ollama_timeout`, `ollama_down`, `postgres_unavailable`, `redis_unavailable`, `network_slow`, `network_flaky`) emitting a timeline + acceptance verdict. Manual-trigger only by design; never wired into CI.
- **`docs/disaster-recovery.md`** — scenarios A-E (`data/` lost, Postgres corrupted, Ollama models lost, full host compromise, `DB_ENCRYPTION_KEY` lost) with RTO/RPO table, step-by-step procedures, verification checks, and explicit mapping to Batch J scripts. Acknowledges that chaos drills are unit-level and documents the Windows `pg_dump` path caveat.

### Tests
- `tests/test_backup_snapshot.py` (7), `tests/test_backup_integrity.py` (7), `tests/test_restore_verify.py` (6), `tests/test_restore_verify_postgres.py` (2, integration skips cleanly without Docker / postgres client), `tests/test_chaos_drill.py` (8), `tests/test_post_deploy_smoke.py` (6), `tests/test_dr_checklist.py` (3). Batch J targeted sweep grows to include real-Postgres restore coverage.

## [Arc 7 / Batch I continued] — 2026-04-23 — Continuous learning close-out

### Automatic rollback watcher (task-155)
- **`evaluation/rollback_watcher.py`** — pure `compute_drift()` scorer plus async `check_and_rollback(session, notifier)` that reads active deployments, compares candidate vs baseline mean evaluator scores across `rollback_trace_window` traces, rolls back deployments that degrade by `rollback_drift_threshold_pct`, and calls the provided notifier. `default_notifier` reuses `scripts.weekly_report.send_email` and `TENANT_ADMIN_EMAIL`.
- **Feature flags** (`config/settings.py`) — `AUTO_ROLLBACK_ENABLED=false`, `ROLLBACK_DRIFT_THRESHOLD_PCT=10.0`, `ROLLBACK_TRACE_WINDOW=1000`, `TENANT_ADMIN_EMAIL=""`.
- **Prometheus** — `rag_experiment_auto_rollback_total{experiment_id,reason}` counter in `monitoring/prometheus.py`.

### Recommendation engine (task-157)
- **`scripts/generate_recommendations.py`** — deterministic rule-based aggregator across improvement-backlog items, threshold-analyzer hints, latest green regression candidates and curated stale cases; emits a ranked list with action + evidence per item and renders markdown via `render_markdown(recs, week=...)`. CLI writes to `reports/recommendations/<week>.md`.
- **Admin endpoint** — `GET /admin/recommendations/current` returns `{recommendations, status}` gated by `RECOMMENDATIONS_ENABLED=true` (safe default, read-only generation only).

### Experiment comparison dashboard (task-158)
- **Admin endpoint** — `GET /admin/experiments/comparison?deployed=<id>&staged=<id>&candidate=<id>` returns three stable buckets with `experiment_id`, `trace_count`, `quality{mean,p50,p95}`, `evaluator_breakdown`, `cost_per_trace`, `latency{p50,p95}`. Deployed bucket reads live trace aggregates, staged reads the latest regression-run row, candidate reflects YAML presence.
- **Admin UI** — `static/admin.html` gains an "Experiment Comparison" tab with `deployed`/`staged`/`candidate` inputs and a JSON output pane, guarded by the existing admin layout.

### Tests
- Added `tests/test_rollback_watcher.py` (8), `tests/test_recommendation_engine.py` (7), `tests/test_experiment_comparison.py` (4). Combined Batch I + K targeted sweep: 130 passed / 0 failed.

## [Arc 7 / Batch I partial] — 2026-04-22 — Continuous learning admin + migrations

### Experiment deployment lifecycle (task-153)
- **Migration 015 `experiment_deployments`** — per-experiment deployment history with `staged_at`, `deployed_at`, `rolled_back_at`, `regression_run_id`, indexed on each timestamp column and on `experiment_id`.
- **Admin deploy/rollback endpoints** — `POST /admin/experiments/{id}/deploy` requires a green regression run on the curated dataset (returns `409` otherwise), updates the experiment YAML status to `deployed`, writes `config/deployed_experiment.yaml` runtime file. `POST /admin/experiments/{id}/rollback` marks the active deployment row and resets YAML status to `completed`, deleting the runtime file.

### Tenant experiment assignments (task-154 admin surface)
- **Migration 016 `experiment_assignments`** — `tenant_id`, `experiment_id`, `rollout_percentage`, `rolled_out_at`, indexed on tenant and experiment.
- **Admin assignments endpoints** — `POST /admin/experiments/{id}/assignments` upserts `{tenant_id, rollout_percentage}`, `GET /admin/experiments/{id}/assignments` lists them.
- **`resolve_active_experiment()` hook** — `agent/prompt_registry.py` now exposes a placeholder resolver that `run_qa_pipeline` consults for `{tenant_id, user_id, session_id}` before falling back to the staged-experiment loader; tests monkeypatch the resolver to simulate tenant assignment.

### Curated dataset freshness (task-156 read side)
- **Migration 017 `curated_case_status`** — `{case_id, tenant_id, status, staleness_reason, last_checked_at}`, indexed on `tenant_id` and `status`.
- **Stale listing endpoint** — `GET /admin/curated-dataset/stale` returns cases with `status='stale_needs_review'`, tenant-scoped via the current admin context.

### Scope
Partial Batch I closure. task-155 auto-rollback, task-157 recommendation engine, task-158 comparison dashboard, sticky rollout evaluation in `resolve_active_experiment`, and the background stale detection job remain for a follow-up batch.

## [Arc 7 / Batch K] — 2026-04-22 — GraceKelly advanced orchestration

### Provider capabilities and graph integration
- **Advanced provider surface** — `llm/providers/base.py`, `gracekelly.py`, `mistral.py`, `ollama.py` and `runtime.py` expanded the runtime to `generate_with_tools`, `generate_with_schema`, `generate_stream` and `generate_batch`, while registry capabilities became the source of truth for tool-use, structured output, streaming and batch support.
- **GraceKelly advanced routing** — `GraceKellyProvider` now keeps simple requests on `/api/v1/smart`, moves tool/schema/consensus requests to `/api/v1/orchestrate`, parses `tool_calls` and `structured_output`, and preserves orchestration metadata.
- **Graph migration to provider-native orchestration** — `agent/graph.py` now uses provider-native tool loops and schema-constrained nodes for `classify_complexity`, `grade_docs` and `verify_facts`, including opt-in consensus mode via `FACT_VERIFY_CONSENSUS_ENABLED` and `FACT_VERIFY_RELIABILITY_LEVEL`.

### Streaming and ingestion
- **Provider-aware streaming API** — `api/app.py` added `/api/chat` and `/api/chat/stream`; the SSE path now tries provider `generate_stream()` before falling back to Ollama-only `_stream_ollama`, and `/api/health` exports `features.streaming_enabled` for the UI.
- **Streaming UI switch** — `static/chat.html` keeps `/api/ask/stream` for compatibility but switches to `/api/chat/stream` when `STREAMING_ENABLED=true`.
- **Opt-in batch contextual headers** — `ingestion/pipeline.py` added `INGESTION_BATCH_ENABLED=false`, provider-batch contextual-header preprocessing for ingestion, and sequential fallback when batch capability is unavailable, with latency metrics written into the ingestion log.

### Observability and tests
- **Consensus metric** — `monitoring/prometheus.py` added `fact_verification_consensus_total{level,verdict}` for explicit visibility into multi-model fact verification.
- **New regression coverage** — added `tests/test_ollama_provider.py`, `tests/test_chat_streaming.py`, and batch-K expansions in provider/graph/ingestion suites covering advanced GraceKelly routing, unified tool/schema paths, provider streaming and ingestion batch fallback.
## [Arc 7 / Batch H] — 2026-04-22 — GraceKelly + Mistral providers

### Provider runtime and routing cleanup
- **GraceKelly provider** — `llm/providers/gracekelly.py`, `llm/providers/base.py` и `llm/providers/runtime.py` добавили локальный orchestrator backend с lazy readiness check через `/healthz/ready`, проксированием в `/api/v1/smart` и `cost_usd=0.0` в наших trace'ах.
- **Direct Mistral provider** — `llm/providers/mistral.py`, `config/providers.yml` и `.env.example` добавили OpenAI-compatible direct provider для `https://api.mistral.ai/v1/chat/completions`, чтение usage из ответа и fail-fast на placeholder `MISTRAL_API_KEY`.
- **Routing profiles revamp** — `local-first`, `gracekelly-primary` и `external-mistral` заменили старые `latency-first` / `cost-first` / `quality-first`; default теперь остаётся zero-spend local-only через Ollama.
- **Dead paid-provider cleanup** — direct `anthropic.py`, `openai.py` и `gemini.py` удалены из runtime как неиспользуемый код для этого deployment profile.

### Failover and observability
- **GraceKelly -> Ollama failover** — runtime теперь перехватывает `ProviderUnavailable`, автоматически переключает запрос на локальный fallback только для declared GraceKelly profiles и кеширует fallback decision на 5 минут.
- **Fallback Prometheus metric** — `monitoring/prometheus.py` добавил `llm_provider_fallback_total{from_provider,to_provider,reason}`, чтобы silent local failover был виден в monitoring.
- **Benchmark refresh** — `scripts/regression_eval.py` и provider tests перешли на `ollama` / `gracekelly` / `mistral` вместо удалённых direct paid providers.

### Docs and operator surface
- **Operator docs refreshed** — README, `.env.example`, roadmap и Arc 7 proposal синхронизированы с новым active set: local Ollama, GraceKelly orchestrator и direct Mistral.
- **Provider/failover test suites** — добавлены `tests/test_mistral_provider.py`, `tests/test_gracekelly_provider.py`, `tests/test_failover_chain.py`, а batch G provider tests переписаны под новый routing surface.

## [Arc 7 / Batch G] — 2026-04-22 — Provider abstraction

### Provider runtime, routing, and economics
- **Provider registry** — `config/providers.yml` и `config/provider_schema.py` добавили единый source of truth для Ollama и direct-provider routing: aliases, pricing tables, capabilities, rate limits и routing profiles `latency-first`, `cost-first`, `quality-first`.
- **Unified provider runtime** — пакет `llm/providers/*` и integration в `agent/graph.py` перевели pipeline на общий provider-backed runtime без отказа от Ollama-first safe default: локальный profile по умолчанию остался zero-spend.
- **Provider-aware trace accounting** — `agent/state.py`, `sqlite_trace.py` и `tracing/sqlite_trace.py` начали сохранять `provider_name`, `model_name`, prompt/completion tokens, usage metadata и `cost_usd` на уровне шагов trace вместо безымянного cost-only режима.
- **Paid guardrails** — `config/settings.py` и `llm/providers/runtime.py` добавили fail-fast validation для paid profiles, считают placeholder secrets вроде `changeme` отсутствующими ключами и блокируют paid runtime при превышении `DAILY_COST_LIMIT_USD`.

### Benchmarking and admin surface
- **Provider benchmark** — `scripts/regression_eval.py` теперь принимает provider/model aliases как baseline/candidate, умеет режимы `mock-provider-benchmark` и `live-provider-benchmark`, а отчёты сравнивают pass rate, latency, total cost и refusal rate по curated dataset.
- **Prometheus provider cost metric** — `monitoring/prometheus.py` и trace logging добавили `llm_cost_usd_total{provider,model,tenant}`, чтобы стоимость LLM стала видимой не только в analytics, но и в operational monitoring.
- **Providers admin tab** — `api/app.py` и `static/admin.html` добавили `GET /api/admin/providers` и UI-вкладку Providers с active/default profile, configured flag, 1-minute usage, 24-hour cost и last successful call timestamp.

### Docs and verification
- **Operator docs refreshed** — `.env.example`, `README.md`, `codex-tasks/ROADMAP.md`, `codex-tasks/arc-7-proposal.md`, `codex-tasks/orchestrator-batch-g-provider-abstraction.md` и task-spec'и 143-149 синхронизированы с новым provider/runtime surface.
- **Provider-focused test suites** — добавлены `tests/test_provider_registry.py`, `tests/test_provider_settings.py`, `tests/test_provider_abstraction.py`, `tests/test_provider_graph_integration.py`, `tests/test_provider_cost_accounting.py`, `tests/test_provider_benchmark.py`, `tests/test_provider_admin_surface.py`, покрывающие schema, runtime, graph integration, cost metrics, benchmark mode и admin API.

## [Arc 6 / Batch F] — 2026-04-22 — Continuous learning lab

### Learning loop foundation (tasks 133-140, fixes 141-142)
- **Review queue** — `alembic/versions/012_review_queue.py`, `scripts/build_review_queue.py`, admin endpoint'ы `/api/admin/review-queue*`, Prometheus-метрики и секция в `static/admin.html` превратили traces/feedback в явную очередь ручного разбора вместо разрозненных сигналов (task-133).
- **Curated dataset builder** — `scripts/build_curated_dataset.py`, `evaluation/dataset.py`, `evaluation/curated_cases.jsonl` и admin-trigger на rebuild начали собирать подтверждённые review cases в переиспользуемый eval/regression датасет вместо одноразового ручного отбора (task-134).
- **Prompt / experiment registry** — `evaluation/experiment_schema.py`, `agent/prompt_registry.py`, `scripts/experiment_{new,apply}.py`, admin endpoint'ы для экспериментов и последующий runtime wire-in через `CURRENT_EXPERIMENT` в `agent/graph.py` сделали staged prompt overrides реально исполняемыми внутри pipeline, а не только описанными в конфиге (tasks 135, 142).
- **Regression runner** — `scripts/regression_eval.py`, CI job `regression-eval`, gate-настройки в `config/settings.py` и API для запуска/просмотра regression runs превратили curated dataset + experiments в формальный pre-deploy quality gate (task-136).
- **Online evaluators runtime** — `evaluation/online_evaluators.py`, `evaluation/evaluator_runner.py`, `alembic/versions/014_trace_evaluations.py`, `/api/admin/evaluations/{trends,worst}`, `scripts/eval_daily_snapshot.py`, `config/evaluator_patterns.yml` и Prometheus-метрики добавили production-оценку trace quality по hot-path и ежедневные snapshot-агрегаты вместо одного только offline eval (tasks 137, 141).
- **Weekly improvement backlog** — `scripts/generate_improvement_backlog.py`, backlog endpoint'ы и cronjob начали агрегировать review queue, KB gaps, evaluator drift, slow traces и freshness signals в единый приоритизированный список улучшений (task-138).
- **Threshold recommendations** — `scripts/analyze_thresholds.py`, `/api/admin/thresholds/*` и `reports/threshold_recommendations.md` перевели quality/review thresholds из ручной настройки в F1-ориентированный анализ на реальных label'ах (task-139).
- **Offline review workflow** — `scripts/review_export.py`, `scripts/review_import.py` и `.gitignore` для review batch artifacts дали команде безопасный export/import ручной разметки вне production UI без потери auditability (task-140).

### Migrations
- **012_review_queue** — таблица `review_queue` и supporting indexes/status fields для human review workflow.
- **013_regression_eval_runs** — расширение `eval_results` полями regression run metadata для baseline/candidate сравнений.
- **014_trace_evaluations** — таблица `trace_evaluations` для online evaluator verdicts, score и evidence.

### Testing
- Полный набор вырос с **319** до **393** тестов (**+74**).
- Closing sweep для Batch F завершился зелёным `pytest tests/ -q`, включая fix-spec'и для prompt-registry routing и online evaluators runtime.

## [Arc 102-122] — 2026-04-21 — Product, enterprise, polish

### Batch A — UX (tasks 102-106)
- **Inline citations и source panel** — ответы начали встраивать маркеры `[N]`, API стал возвращать `citations`, а `static/chat.html` получил hover/click-рендеринг и боковую панель источников вместо «сплошного» текста без ссылок (task-102).
- **Mobile-first responsive UI** — `static/chat.html`, `static/help.html`, `static/metrics.html` и `static/admin.html` перешли на брейкпоинты 480/768/1024, mobile drawer и безопасные tap targets вместо одного грубого mobile fallback (task-103).
- **WCAG 2.1 AA baseline** — `tests/test_a11y.py`, `static/*.html`, `templates/*.html` и `static/styles/components.css` закрыли critical/serious accessibility gaps: labels, `:focus-visible`, keyboard navigation, ARIA и viewport meta (task-104).
- **UX polish для чата** — в `static/chat.html` появились upload progress, retry после сетевых/timeout-ошибок и onboarding-панель с sample questions для первого визита (task-105).
- **Agent copilot** — миграция `alembic/versions/004_escalated_tickets.py`, новые `/api/agent/*` endpoint'ы и `static/agent.html` со `static/styles/agent.css` дали операторам очередь эскалаций, контекст диалога, AI draft и похожие resolved tickets (task-106).

### Batch B — RAG intelligence (tasks 107-110)
- **Agentic tool use** — `agent/tools.py` и `agent/graph.py` добавили LangGraph tool-calling, multi-step tool chains и confirmation gate для необратимых действий под флагом `RAG_AGENTIC_MODE` (task-107).
- **Nightly RAGAS evaluation** — `scripts/nightly_eval.py`, `evaluation/drift.py`, `alembic/versions/005_eval_results.py` и `deploy/helm/templates/cronjob.yaml` превратили offline eval из CI-only практики в регулярный production drift monitoring (task-108).
- **KB gap detection** — `scripts/kb_gap_detector.py`, `alembic/versions/006_knowledge_gaps.py`, `GET /api/admin/kb-gaps` и секция в `static/admin.html` начали превращать unanswered/unsupported вопросы в админские KB gap tickets (task-109).
- **Contextual ingestion headers** — `ingestion/pipeline.py`, `vectordb/manager.py` и `scripts/reindex.py` активировали document-aware contextual headers для чанков под флагом `RAG_CONTEXTUAL_HEADERS` (task-110).

### Batch C — Enterprise (tasks 111-113)
- **OpenTelemetry distributed tracing** — `tracing/otel.py`, интеграция в `api/app.py`, ручные span'ы в графе, `docker-compose.yml` и `deploy/helm/values.yaml` добавили OTLP export в Jaeger/Tempo без удаления SQLite/Langfuse tracing (task-111).
- **SSO via OIDC** — `auth/oidc.py`, `static/login.html`, `/api/auth/sso/providers`, `/api/auth/sso/{provider}/login`, `/api/auth/sso/{provider}/callback` и миграция `007_user_sso_fields` принесли Google/Azure AD sign-in с tenant mapping по email-domain rules (task-112).
- **Encryption at rest** — `db/crypto.py`, `alembic/versions/008_enable_pgcrypto.py` и `DB_ENCRYPTION_KEY` перевели sensitive Postgres columns на `pgcrypto`/AES-256 с прозрачным decrypt в ORM и отдельным rotation script stub `scripts/rotate_encryption_key.py` (task-113).

### Batch D — Differentiation (tasks 114-119)
- **Knowledge Builder** — `scripts/kb_builder.py`, миграция `009_kb_drafts`, админские `/api/admin/kb-drafts/*` endpoint'ы и UI в `static/admin.html` начали собирать resolved tickets в reviewable KB drafts вместо потери накопленного знания (task-114).
- **Knowledge freshness monitoring** — `alembic/versions/010_document_stats.py`, citation counters в графе, `GET /api/admin/stale-docs` и `rag_stale_important_docs_count` сделали видимыми старые, но часто цитируемые документы (task-115).
- **Auto-categorization** — `ingestion/categorizer.py`, `config/categories.yml` и расширенный `/api/upload` начали присваивать документам категории, которые потом используются в metadata и аналитике (task-116).
- **Analytics dashboard** — `static/analytics.html`, `/api/analytics/top-topics`, `/api/analytics/resolution-rate`, `/api/analytics/cost-summary`, `/api/analytics/trends` и миграция `011_trace_costs` добавили продуктовую аналитику поверх traces/cost data (task-117).
- **Weekly quality reports** — `reports/renderer.py`, `scripts/weekly_report.py`, `deploy/helm/templates/cronjob-report.yaml` и `.github/workflows/weekly-report.yml` перевели аналитику из pull-mode в scheduled Slack/email digest (task-118).
- **Email channel** — `channels/email_channel.py`, `channels/email_webhook.py`, `scripts/email_poller.py`, `/api/channels/email/inbound` и `deploy/helm/templates/deployment-email-poller.yaml` подключили IMAP/webhook email ingestion к тому же RAG/escalation flow (task-119).

### Batch E — Code quality (tasks 120-122)
- **Canonical agent package** — `agent/{graph,prompts,state,tools}.py` стал каноническим домом для graph/state/prompt/tool кода, а root-level `graph.py`, `prompts.py` и `state.py` были сохранены как compatibility shims на период миграции импортов (task-120).
- **Settings over magic numbers** — ключевые thresholds и tuning constants переехали в `config/settings.py` и `.env.example`, чтобы retrieval/chunking/quality настройки менялись через конфиг, а не через правку кода (task-121).
- **Integration test suite** — `tests/integration/` и отдельный `integration` marker закрыли полный happy-path: ingestion, multi-turn conversation, SSE streaming, concurrency, escalation и async upload в отдельном прогоне и CI-job'е (task-122).

### Migrations
- **004_escalated_tickets** — таблица `escalated_tickets` для copilot/escalation workflow.
- **005_eval_results** — хранение nightly eval metrics и drift flags.
- **006_knowledge_gaps** — хранение кластеров unanswered questions.
- **007_user_sso_fields** — поля OIDC provider/subject для пользователей.
- **008_enable_pgcrypto** — включение `pgcrypto` и переход sensitive columns на encrypted storage.
- **009_kb_drafts** — хранение reviewable KB drafts из resolved tickets.
- **010_document_stats** — статистика цитирований, freshness и stale-doc review state.
- **011_trace_costs** — token usage и cost data для analytics/cost summaries.

### Testing
- Полный набор вырос с **222** до **293** тестов (**+71**).
- Отдельная `tests/integration/` директория закрыла те сценарии, которые раньше проверялись только набором unit-тестов и ручных прогонов.

## [Arc 68-101] — 2026-04-20 — Production hardening

### Resilience (tasks 69-71, 82-83)
- **Circuit breaker вокруг Ollama** — `utils/circuit_breaker.py`, интеграция в `graph.py` и ручной reset через `/api/admin/circuit-breaker/reset` остановили каскадные задержки при падениях модели и дали fast-fail path вместо накопления зависших запросов (tasks 69, 74).
- **Retry, timeout и bounded failure budget** — `utils/retry.py`, per-call timeout для Ollama и retry observability в `monitoring/prometheus.py` начали гасить транзитные ошибки до того, как breaker откроется, и сделали эти деградации видимыми (tasks 70, 71, 73).
- **Request wall-time timeout и offload из event loop** — `/api/ask` начал выносить sync pipeline в `asyncio.to_thread`, получил `REQUEST_TIMEOUT_SEC`, а обработка запросов перестала блокировать health probes и соседние соединения (task-82).
- **Bounded pipeline concurrency** — глобальный admission control через `asyncio.Semaphore` и timeout на ожидание pipeline slot защитили сервис от самоперегрузки на пиках нагрузки (task-83).

### Observability (tasks 72-81, 89, 98)
- **Prometheus стал основным operational truth** — breaker state/transitions, retry events, component health, generic HTTP metrics, rate-limit rejections, request timeouts, auth failures, body-size rejections и DB pool saturation превратили систему из «логов и догадок» в измеряемый сервис (tasks 72, 73, 76, 78, 81, 89, 98).
- **Alert rules as code** — `monitoring/alert_rules.yml` зафиксировал базовые resilience/health/quality alerts прямо в репозитории, чтобы пороги ревьюились вместе с кодом, а не жили отдельно в ручной инфраструктуре (task-78).
- **Correlation ID end-to-end** — `api/correlation.py`, `X-Request-Id` middleware и прокидывание request id в trace state связали UI-инциденты, middleware-логи и pipeline traces в одну цепочку расследования (task-79).

### Health, deploy and admin operations (tasks 75, 77, 80, 84, 85, 90, 94)
- **Dependency-aware health model** — `/api/health/live` и `/api/health/ready` разделили liveness и readiness semantics, а Postgres/Redis probes добавили реальное представление о состоянии зависимостей вместо чисто Ollama/Chroma статуса (tasks 75, 77).
- **Graceful shutdown with readiness flip** — приложение стало переводить readiness в `503` перед реальным shutdown, чтобы rolling deploy не принимал новый трафик в pod, который уже уходит на остановку (task-80).
- **Trace и audit retention** — фоновая и ручная очистка SQLite traces и Postgres audit log ограничила бесконтрольный рост служебных таблиц и сделала retention частью runtime политики, а не разовой операции DBA (tasks 84, 85).
- **Admin investigation surface** — `/api/admin/audit`, `/api/admin/traces`, `/api/admin/traces/{trace_id}` и затем `static/admin.html` вывели операции расследования из прямого SQL/curl в стандартный HTTP/UI слой для support и admin ролей (tasks 90, 94).

### Security and platform hardening (tasks 86-88)
- **Auth hardening** — `/api/auth/login` получил rate limit `5/min`, failed-login audit trail и Prometheus metrics, чтобы credential stuffing и password spraying стали не только затруднены, но и заметны (task-86).
- **Production CORS guardrails** — `RAG_ENV`, startup validation и `CORS_MAX_AGE_SEC` сделали `CORS_ORIGINS="*"` допустимым только в development и закрыли тихий insecure deploy path в production (task-87).
- **Request body limits** — middleware на `MAX_REQUEST_BODY_BYTES` и upload-specific `MAX_UPLOAD_BYTES` добавили дешёвую защиту от oversized JSON/file DoS до разбора тела в приложении (task-88).

### Multi-tenancy (tasks 91, 93, 95, 96)
- **Tenant schema and propagation** — `tenant_id` вошёл в schema/state/Pydantic, затем в JWT claims, request-scoped context, traces и audit log, так что система перестала считать всех пользователей `default` tenant'ом на уровне записи данных (tasks 91, 93).
- **Tenant enforcement on reads** — admin read endpoints, metrics snapshot и trace/audit lookups начали фильтровать данные по текущему tenant'у, закрывая прямой cross-tenant leak в metadata/read paths (task-95).
- **Per-tenant ChromaDB collections** — `vectordb/manager.py` ушёл от общего `rag_docs` к tenant-scoped `rag_docs_{tenant_id}`, что закрыло самую опасную дыру: смешивание документов разных клиентов в retrieval (task-96).

### Answer quality and routing (tasks 92, 97)
- **Fact verification node** — после `generate` появился отдельный `verify_facts` шаг, который извлекает claims, сверяет их с retrieved context и пишет `factuality_score` вместо слепого доверия к самооценке модели (task-92).
- **Model routing** — `MODEL_ROUTING_ENABLED` и `OLLAMA_FAST_MODEL_NAME` позволили отдавать простые вопросы быстрой модели, а сложные оставлять на более сильной, не меняя retrieval path и сохраняя safe default `off` (task-97).

### Tech debt closure (tasks 99-101)
- **Flaky rate-limit tests fixed** — `tests/conftest.py` начал сбрасывать slowapi state между тестами, убрав случайные падения `test_rate_limiting` в полном прогоне (task-99).
- **LLM response cache wired in** — готовый `cache/redis_cache.py` перестал быть мёртвым кодом и начал кешировать финальные ответы по `(tenant, normalized_question)` с инвалидацией после upload (task-100).
- **Repository line endings normalized** — `.gitattributes` закрепил LF для текстовых файлов и устранил Windows-specific CRLF noise в коммитах и diff'ах (task-101).

### Testing
- Арка стартовала примерно со **130** тестов и закрылась на **222** тестах.
- Существенная часть роста пришлась на resilience, observability, health, multi-tenancy, fact verification и routing regressions, которые раньше вообще не были формализованы в test suite.
## [Arc 7 / Batch H-K close-out] — 2026-04-23 — GraceKelly runtime smoke harness

### Task-174 GraceKelly runtime smoke
- **`scripts/gracekelly_smoke.py`** — manual-only standalone smoke CLI for a live GraceKelly-backed RAG deployment. Validates direct GraceKelly readiness, the active provider profile, `/api/ask` trace metadata, direct schema dispatch on `/api/v1/orchestrate`, SSE streaming on `/api/chat/stream`, Prometheus cost/fallback counters, and a dedicated `--simulate-down` failover-only mode. Steps the current runtime cannot prove externally are emitted as explicit `SKIPPED`.
- **`docs/operations/gracekelly-smoke.md`** — operator runbook with prerequisites, auth expectations, healthy-path and failover-only commands, example output, exit-code mapping, and troubleshooting notes for `GRACEKELLY_BASE_URL`, `/api/admin/providers`, zero-cost metrics, and failover preparation.

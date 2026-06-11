# Аудит RAG_Support_Assistant — 11.06.2026 (Fable)

**Аудитор:** Claude Fable 5
**Дата:** 2026-06-11
**HEAD:** `55f1a42` (master, синхронизирован с origin по AGENT_STATE cont.18; CI зелёный)
**Worktree:** 2 untracked файла чужой параллельной сессии (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`) — не трогал. Плюс этот файл.
**Предыдущие аудиты:** Claude 03.06 (8.8/10, `a73687b`), MiniMax 03.06 (`0e04847`), Codex/Kimi/Opus ранее.

---

## 0. Методология и границы

**Что делалось:** прямое чтение кода — `agent/graph.py` (полностью), `api/app.py` (полностью), `api/routers/conversation.py` (полностью), `vectordb/_base_manager.py` (полностью), `vectordb/manager.py`, `config/settings.py`, `api/routers/upload.py`, `api/routers/analytics.py`, `agent/tools.py`, `cache.py`, `llm/providers/runtime.py` (частично), `tracing/_base_trace.py` (частично), `.github/workflows/ci.yml` (частично) + точечные greps по всему дереву. Сверка с AGENT_STATE.md, BACKLOG.md и двумя последними аудитами.

**Что НЕ делалось:** pytest/mypy/ruff локально не гонялись (правило 1 GiB на этой машине, CI — источник истины; последний прогон зелёный 11/11 на `51628e2`), live LLM не вызывался, ingestion не запускался. Findings ниже — из чтения кода, каждый с `file:line`.

---

## 1. Executive Summary

Проект в отличной форме по меркам своей серии аудитов: retrieval-стек измерен и обоснован данными (R7-judge: recall 0.975, faithfulness 0.864 на D2; циклы E/F закрыты NO-SHIP по данным, а не по ощущениям), 847 тестов зелёные, CI с миграционным аудитом, helm-рендером, hash-locked зависимостями. Findings прошлых аудитов, которые я проверил, закрыты в коде (см. §4).

**Главный сдвиг фокуса:** качество retrieval больше не самое слабое место. Самые серьёзные оставшиеся риски — **операционные**, и почти все вертятся вокруг одного системного решения: ключевое состояние (BM25-индекс, сессии, pending-actions, regression-jobs) живёт в памяти процесса, а sync/async граница пайплайна заклеена мостами (`asyncio.to_thread` + `asyncio.run` + `engine.dispose()` на каждый запрос).

**Топ-3:**
1. **F-2** — hybrid-поиск (BM25 + parent-expansion) молча деградирует до vector-only после рестарта процесса. Весь недавно вымеренный production-стек живёт только в RAM.
2. **F-1** — upload блокирует event loop на полную пере-эмбеддинг-сборку корпуса; стоимость одного аплоада растёт линейно с размером KB (суммарно — квадратично).
3. **F-3** — `/ask/stream` обходит весь Self-RAG-пайплайн и пишет в метрики/трейсы синтетический quality_score.

**Оценка: 8.7/10.** Код зрелый и доказуемо работающий; потолок держат архитектурные долги ниже, а не качество RAG.

---

## 2. Findings

### HIGH

#### F-1. Upload: синхронная пересборка всего векторного стора в event loop + O(N) на каждый файл

`api/routers/upload.py:139` — `_app._rebuild_vector_store_from_docs(docs, tenant_id=tenant)` вызывается **напрямую из async-хендлера** (не через `to_thread`). Внутри (`api/app.py:1139-1189`) — chunking + эмбеддинг всего корпуса BGE-M3. На время пересборки **весь event loop стоит**: все `/ask`, health-probes, readiness — всё.

Усугубляется тем, что:
- `upload.py:109,137` — `loader.load_documents(str(upload_dir))` загружает **всю директорию** заново, а не один новый файл;
- `vectordb/manager.py:163-180` — коллекция тенанта удаляется и строится с нуля (`delete_collection` + `from_documents`).

Итог: стоимость одного аплоада = пере-эмбеддинг всей KB. Celery-путь (`upload.py:116-131`) есть только для `tenant == "default"`; все остальные тенанты всегда идут синхронной веткой.

**Рекомендация:** (а) минимум — обернуть в `asyncio.to_thread`; (б) правильно — инкрементальный ingest: `vector_store.add_documents(новые чанки)` + дельта в `_chunks_cache`, полная пересборка только по явной admin-команде reindex; (в) Celery-путь для всех тенантов.

#### F-2. BM25 и parent-expansion не переживают рестарт процесса — молчаливая деградация retrieval

BM25-индекс строится из `chunks`, которые живут только в `_chunks_cache` (`vectordb/manager.py:24`, заполняется лишь в `build_vector_store`, т.е. при аплоаде). После рестарта:
- `get_retriever(tenant)` (`manager.py:248-251`) получает `chunks=None` из пустого кэша;
- `_base_manager.get_retriever:1193` — `use_bm25 = ... and chunks is not None` → **BM25 выключен**;
- `HybridRetriever.__init__:318-321` — `_chunk_positions` пуст → **parent-expansion фактически мёртв** (lookup соседей не работает);
- остаётся vector + reranker.

Никакого warning'а, никакой метрики — деградацию видно только по качеству ответов. Это значит, что вымеренный production-стек (structural chunking + parent-expansion w=2/3600, FULL 96/100, recall 0.975) **в проде воспроизводится только до первого рестарта** — дальше работает другой, не измеренный стек. A/B-замеры серии D/E/F валидны для конфигурации, которой после restart нет.

**Рекомендация:** при старте/первом обращении к тенанту восстанавливать чанки из персистентного Chroma (`collection.get(include=["documents","metadatas"])` — там всё есть, порядок ингеста можно нести в `chunk_index` метаданных), либо сериализовать chunks на диск рядом с коллекцией. Плюс Prometheus-gauge `retriever_bm25_enabled{tenant}` и warning при сборке HybridRetriever без chunks.

#### F-3. `/ask/stream` обходит Self-RAG целиком и пишет синтетический quality в метрики

`api/routers/conversation.py:520-643`: streaming-путь — это сырой `retriever → build_qa_prompt → стрим токенов`. Ни `grade_docs`, ни `verify_facts`, ни `evaluate`, ни route-логики. Затем:

```python
quality = 70 if len(full_answer.strip()) > 20 or sources else 40   # :642
route = "auto" if quality >= 70 else "human"
```

Любой ответ длиннее 20 символов = quality 70, route auto. Эти значения уходят клиенту и в трейсы. `STREAMING_RAG_PARITY` (полная parity вторым прогоном графа) выключен по умолчанию — осознанно (×2 стоимости), но дефолтное состояние = два класса ответов с несравнимой семантикой quality_score в одних и тех же метриках.

Дополнительно streaming-путь:
- **не подчиняется** `_pipeline_semaphore` (bounded concurrency есть только в `/ask`) и wall-clock `request_timeout_sec`;
- не использует LLM-кэш;
- флаг `settings.streaming_enabled` нигде не enforced — он только отображается в system-info (`api/routers/system.py:166`), эндпоинт работает всегда.

**Рекомендация:** дешёвая parity вместо полной — после стрима прогнать только `evaluate` (+опционально `verify_facts`) над уже полученными docs/answer: один LLM-вызов вместо второго полного прогона. Семафор и таймаут распространить на стрим. Синтетические скоры пометить (см. F-9).

---

### MEDIUM

#### F-4. Граф, провайдеры и YAML-реестр пересоздаются на каждый запрос

`agent/graph.py:1946` — `build_support_graph(...)` (включая `StateGraph(...).compile()`) вызывается внутри `run_qa_pipeline` на **каждый вопрос**. Там же `build_provider_runtime(settings)` (`graph.py:1804`), который без какого-либо кэша парсит `providers.yml` с диска и пересоздаёт провайдеров (`llm/providers/runtime.py:254`, `load_provider_registry` внутри `_instantiate_provider`). Streaming-путь и `_select_agentic_llm` делают это ещё раз.

**Рекомендация:** кэшировать compiled graph + runtime по ключу (profile, experiment_id, перечень experiment-overrides); инвалидация при смене эксперимента. Это самая дешёвая победа по латентности p50.

#### F-5. `asyncio.run()` + `engine.dispose()` на каждый `/ask` (online evaluators)

`agent/graph.py:1995` — `asyncio.run(_persist_results())` внутри sync-пайплайна (который сам крутится в `asyncio.to_thread` из `/ask`), и в `finally` — `await _engine.dispose()` (`:1988`). С `online_evaluators_enabled=true` (default) это означает: **пул asyncpg уничтожается после каждого запроса** — каждый следующий запрос платит за реконнект к Postgres. Комментарии «Bug 2/Bug 4 fix» честно объясняют, что это workaround под event-loop-per-call.

Root cause — сам мост: sync-пайплайн владеет async-персистом. **Рекомендация:** отдавать результаты эвалуаторов в основной loop (`asyncio.run_coroutine_threadsafe` с loop'ом, захваченным до `to_thread`, или очередь + один фоновый consumer). Тогда dispose не нужен вовсе. Туда же — `agent/tools.py:94` (`asyncio.run(_persist_ticket(...))` — тот же паттерн).

#### F-6. Глобальный `_db_retry_after`: один таймаут Postgres → 60 секунд молчаливой потери истории у ВСЕХ сессий

`api/app.py:249-250` + `conversation.py:374-387, 754-767`: при любом исключении персиста сообщений (`timeout=0.5s` — жёсткий) ставится глобальный «не пытаться 60s». Сообщения за это окно **не сохраняются и не доставляются позже** (нет очереди/ретрая), история тенанта в Postgres получает дыры; единственный след — warning в логах. 0.5s на commit под нагрузкой — это не отказ БД, это обычный хвост латентности.

**Рекомендация:** per-операционный retry с буфером недоставленных (in-memory ring + повторная попытка следующим запросом), таймаут 2-3s, Prometheus-counter потерянных сообщений. Глобальный breaker оставить только для подключения, не для отдельных commit'ов.

#### F-7. LLM-кэш не учитывает контекст диалога

`api/app.py:916-919` — ключ кэша = `tenant + sha256(question)`. История сессии в ключ не входит, а в кэш попадают любые `route=auto` ответы (`conversation.py:273-290`), включая ответы на follow-up вопросы, сгенерированные с `chat_history`. Сценарий: пользователь A спрашивает «А сколько это стоит?» в контексте доставки → ответ кэшируется → пользователь B с тем же вопросом в контексте гарантии получает ответ про доставку.

**Рекомендация:** кэшировать только первый ход сессии (пустая история) либо включать в ключ хэш последних N ходов. Сейчас `llm_cache_enabled=false` по умолчанию — риск спящий, но включение флага в проде приведёт к трудноотлаживаемым «не тем» ответам.

#### F-8. Latent NameError в fallback-ветке `/ask/stream`

`conversation.py:779-794`: `except`-ветка обращается к `graph_task` (`:786`) и `ask_args` (`:793`), которые определяются внутри `try` на строках 481-513. Если исключение случится до их присвоения (например, `inspect.signature(session.ask)` на нестандартном объекте сессии, `:480`), fallback упадёт NameError'ом, SSE-поток оборвётся без `result`-события. Узкое окно, но это именно та ветка, которая должна спасать любые ошибки.

**Рекомендация:** инициализировать `graph_task = None`, `ask_args = (question,)` **до** `try`.

#### F-9. Agentic flow: хардкод-эвристики и константные quality_score, загрязняющие метрики

- `graph.py:750-756` — `_build_agentic_search_query`: захардкоженные `"достав"/"москв"` → `"доставка в Москву"`;
- `graph.py:498-502` — `_extract_order_id` = `r"#?(\d{1,10})"`: «статус ошибки 404» → `check_order_status("404")` (маркер `"статус"` в вопросе есть);
- `agent/tools.py:51-62` — `check_order_status` — мок с заказами 42 и 7, отвечающий уверенным текстом про любой заказ («статус 'в обработке'») — для пользователя неотличимо от реальных данных;
- `graph.py:2139, 2186, 2271, 2289, 2337, 2386` — `quality_score` 80/85/90 и `relevance_score` 0.8/0.85/0.9 проставляются **константами** во всех agentic-ветках.

Эти константы попадают в тот же `QUALITY_SCORE` histogram и трейсы, что и честные LLM-оценки (`conversation.py:403`), плюс синтетика из стрима (F-3). Дашборды качества при включённом `agentic_mode`/стриме показывают смесь измеренного и выдуманного.

**Рекомендация:** (а) добавить в state поле `quality_source: "llm" | "heuristic" | "fixed"` и label в метрику — дёшево и сразу честно; (б) keyword-эвристики agentic-фолбэка либо за фичефлаг «demo», либо выпилить (provider tool loop уже есть); (в) мок order-status явно подписывать в ответе.

#### F-10. `evaluate` всегда получает fast-модель — параметр мёртв

`graph.py:1826` — `workflow.add_node("evaluate", make_evaluate_node(llm_fast, llm_fast))`. Фабрика принимает `(llm_fast, llm_strong)` и выбирает по complexity (`:1494`), но strong сюда никогда не передаётся — выбор внутри узла не работает по построению. При этом `suggest_questions` (nice-to-have) получает `llm_strong` (`:1828`). Если экономия на evaluate осознанная — она инвертирована относительно ценности узлов: self-eval определяет route (auto/human/retry), suggested questions — косметика.

**Рекомендация:** либо `make_evaluate_node(llm_fast, llm_strong)` (как явно задумано сигнатурой), либо убрать второй параметр и зафиксировать решение комментарием. `suggest_questions` перевести на fast.

> **Резолюция (2026-06-11):** проводка оказалась НАМЕРЕННОЙ — пин-тест
> `test_build_support_graph_uses_fast_llm_for_evaluate_node` (коммит `7e266af`,
> «Route RAG GraceKelly calls through orchestrate»): strong в gracekelly-primary
> = ~60s browser-orchestrate вызов, self-eval на нём удвоил бы латентность
> complex-запросов. Оставлено `(llm_fast, llm_fast)`, решение задокументировано
> комментарием в `build_support_graph`; `suggest_questions` переведён на fast.

#### F-11. Sync SQLite full-scan в async analytics-эндпоинтах

`api/routers/analytics.py:30,55,81,117` — четыре `async def` эндпоинта зовут `_load_recent_trace_summaries` (`api/app.py:742-877`) **напрямую в event loop**: полный проход `traces` за N дней с `json.loads(state_json)` последнего шага каждого трейса в Python. Открытие дашборда = 4 одинаковых скана подряд. На большой истории (retention 90 дней) это секунды блокировки loop'а на каждый виджет.

**Рекомендация:** минимум — `asyncio.to_thread`; правильно — один эндпоинт-агрегат (или кэш сводки на 30-60s в Redis), категории/cost считать SQL'ем, а не распаковкой JSON в Python.

#### F-12. `verify_facts` проверяет факты по 5×500 символов контекста — лимит не пересмотрен после parent-expansion

`graph.py:1307-1311` — контекст для верификации claims обрезается до первых 500 символов каждого из первых 5 доков. После включения parent-expansion (default ON) чанки достигают 3600 символов — верификация видит ~14% документа. Факт из хвоста расширенного чанка, корректно использованный в ответе, получит «unsupported» → заниженный `factuality_score` → ложные knowledge-gap сигналы (`_is_knowledge_gap`, `:474` — порог factuality < 50).

**Рекомендация:** поднять лимит до согласованного с `parent_expansion_max_chars` (или брать первые N символов суммарного бюджета, а не по-документно 500), и вынести оба числа в settings.

---

### LOW

#### F-13. Settings: смешение import-time defaults и default_factory (известная гоча) + god-object

`config/settings.py:292,300,310,317-321,330-334,542,673-698,711-723` — десятки полей с `os.getenv` на уровне класса (вычисляются при import), вперемешку с `default_factory`-полями. Последствия уже стоили времени (AGENT_STATE cont.15: «`monkeypatch.setenv` бессилен... гасить `monkeypatch.setattr` на singleton'е»). 950 строк, ~120 полей, без валидации диапазонов. **Рекомендация:** механическая унификация всех полей на `default_factory` (поведение для прода не меняется — синглтон создаётся один раз), отдельным PR; в перспективе pydantic-settings с групповыми под-моделями.

#### F-14. Мёртвый код и двойники путей

- Корневой `cache.py` (267 строк, RAGCache) **затенён пакетом `cache/`** и не импортируется нигде в проекте — мёртвый модуль, вводящий в заблуждение (grep подтверждён). Удалить или переместить в archive-legacy.
- `vectordb/_base_manager.py:487-494` — `_project_root()` возвращает `vectordb/`, поэтому `_data_dir()` = `vectordb/data/vectordb`, и `_base_manager._build_chroma` (`:975`) пишет туда с `collection_name="documents"` — путь и имя коллекции расходятся с боевыми (`settings.vectordb_chroma_dir`, `rag_docs_{tenant}` из `manager.py`). Любой прямой вызов `_base_manager.build_vector_store` создаст «невидимый» стор. Переименовать функцию/направить на settings.
- `_base_manager.get_embeddings(model_name)`/`get_reranker(model_name)` (`:166-167, :229-231`) игнорируют аргумент при тёплом кэше — кэш не ключуется по имени модели.

#### F-15. `inspect.signature`-интроспекция в hot path

`conversation.py:80-87, 174-189, 444-451, 480-489`, `api/app.py:996-1000, 1120-1127, 1156-1160` — runtime-проверки сигнатур на каждый запрос ради обратной совместимости старых тестов. Это и стоимость (signature parsing per request), и маскировка реальных контрактов. Сигнатуры давно стабильны — пора зафиксировать их и убрать интроспекцию (вместе с соответствующими monkeypatch-тестами).

#### F-16. Гигиена корня репозитория

В корне: 8 audit-файлов (один без расширения — `audit_codex_27_04_26`), 4 PNG-скриншота (~770KB), `.coverage`, 7 директорий `.pytest-tmp-*`, `AGENT_STATE.md` на 107KB, session-файлы (`next-session-3-subagents.md`, `project-closure-today.md`, `2026-05-02-non-live-backlog.md`, `rec.md`). Рабочему onboarding'у это мешает (Step 0 «прочитай все md в корне» дорожает с каждой сессией). **Рекомендация:** `docs/audits/`, `docs/sessions/`, скриншоты в `docs/img/` или удалить; `.pytest-tmp-*` и `.coverage` — в `.gitignore`/почистить; AGENT_STATE.md — архивировать секции старше N сессий в `docs/sessions/`.

#### F-17. `ask()` возвращает `JSONResponse` при `response_model=AskResponse`

`conversation.py:65,410-417` — возврат готового `JSONResponse` отключает валидацию response_model; поле `cached` (`:411`) вообще не описано в схеме — OpenAPI врёт клиентам. Достаточно добавить `cached: bool = False` в `AskResponse` и возвращать модель.

#### F-18. Online evaluators: жёсткий timeout 1.0s без наблюдаемости

`graph.py:1972-1975` — `asyncio.wait_for(asyncio.to_thread(run_online_evaluators, ...), timeout=1.0)`: на нагруженной машине эвалуаторы будут молча дропаться (warning в лог), доля дропов нигде не считается. Добавить counter `online_evaluators_dropped_total` и вынести timeout в settings.

---

## 3. Сквозная тема: состояние в памяти процесса vs multi-worker

Отдельные findings выше — симптомы одного решения. В памяти процесса живут: `_session_llm_state` + `ConversationSession._history` + `_pending_action` (подтверждение необратимых действий!), `_regression_jobs`, `_chunks_cache`/`_retriever_cache`/`_store_cache`, `_db_retry_after`, circuit breaker. При этом `tracing/_base_trace.py:122-123` явно заявляет поддержку «uvicorn --workers 2», и helm-чарт деплоит это в k8s.

При >1 воркере или >1 реплике: подтверждение `create_ticket` уйдёт не в тот процесс (pending_action отсутствует → пользователю снова «Подтвердите», по кругу); LLM-кэш Redis общий, а сессии — нет; regression-status «queued» навсегда. **Рекомендация:** либо письменно зафиксировать инвариант «строго 1 worker / 1 replica» (в runbook + helm values + assert при старте), либо переносить session-state и pending-actions в Redis/Postgres (модели Message/Session уже есть — не хватает pending_action и серверной правды о history).

## 4. Проверка findings прошлых аудитов (закрыто — подтверждаю по коду)

| Finding | Статус | Доказательство |
|---|---|---|
| F1 (03.06) fire-and-forget `create_task` ×3 | **ЗАКРЫТ** | `utils/background_tasks.spawn_tracked`: `db/audit.py:48`, `admin_experiments.py:269`, `conversation.py:408` |
| F2 (03.06) нет CSP при токене в localStorage | **ЗАКРЫТ** | `api/app.py:1644-1654` — CSP с external-only скриптами |
| H2 (27.04) обещанный handoff без тикета | **ЗАКРЫТ** | `conversation.py:311-331` — EscalatedTicket при ошибке пайплайна |
| R1 RU-reranker | **ЗАКРЫТ** | `settings.py:300` default `bge-reranker-v2-m3`, A/B-доки |
| R7 (HIGH, foundational) RAGAS не измерен | **ЗАКРЫТ** | R7-judge ×N прогонов (AGENT_STATE cont.14-18), D2 recall 0.975/faith 0.864, judge-репорты в `reports/ragas/` |
| Chroma dimension mismatch fail-open | **ЗАКРЫТ** | `api/app.py:1045-1115` fail-closed |
| R5-остаток: BM25 in-memory на retriever | **OPEN, обострён** | теперь это F-2 (рестарт = молчаливая потеря BM25) |
| R6: reranker device | **ЗАКРЫТ** | `_base_manager.py:74-99` `_resolve_device` auto cuda/mps/cpu |

## 5. Приоритизированный план

> Статусы на 2026-06-11 (сессия Fable hardening 2: батч §1-6 верифицирован зелёным
> и закоммичен 7 локальными коммитами `2ee78a8..59df7c9` на `master`, НЕ запушен;
> детальный handoff — `next-session-fable-hardening.md`).

1. **F-2** — восстановление chunks из Chroma при старте + метрика `bm25_enabled`. — **✅ СДЕЛАНО** (`vectordb/manager.py`, тесты `tests/test_chunks_restore.py` 6/6).
2. **F-1** — `to_thread` вокруг rebuild — **✅ СДЕЛАНО** (`api/routers/upload.py`); инкрементальный ingest — отдельный цикл, не начат.
3. **F-9a + F-3** — `quality_source` в state/метриках + дешёвая streaming-parity (evaluate-only, `STREAMING_QUALITY_EVAL`) + семафор/дедлайн стрима — **✅ СДЕЛАНО, верифицировано** (стрим/кэш-suite 49 passed; коммит `f8cc015`).
4. **F-5 + F-6** — мост персистенции: F-6 (таймауты в settings + counter) **✅ сделано**; F-5 — **✅ СДЕЛАНО** (`utils/event_loop.py` подключён: loop регистрируется в `api/app.py` `_lifespan` на старте/сбрасывается в finally; `run_qa_pipeline` шлёт персист online-eval через `run_coroutine_threadsafe` на main loop без `engine.dispose()`, sync-скрипты — legacy `asyncio.run`+dispose; F-18 timeout из `online_evaluators_timeout_sec` + counter `rag_online_evaluators_dropped_total{reason}`; тест threadsafe-пути зелёный; коммит `59df7c9`).
5. **F-4** — кэш compiled graph + provider runtime. — не начат (ловушка `last_response`, см. handoff §4).
6. **F-8, F-10, F-12, F-17** — точечные фиксы. — **✅ ЗАКРЫТЫ** (+ F-7, F-11, F-18-метрика). F-10 разрешён как «намеренно» — см. резолюцию в самом finding'е.
7. **§3** — решение по multi-worker инварианту (документ или Redis-сессии) — до любого масштабирования реплик. — не начат.
8. **F-13, F-14, F-15, F-16** — гигиенический спринт без изменения поведения. — не начат.

---

## 6. Вердикт

**8.7/10.** Сильные стороны: доказательная культура (A/B перед каждым flip дефолта, NO-SHIP по данным), безопасность (fail-fast прод-секретов, CSP, body limits, timing-safe ключи), наблюдаемость (~50 метрик, корреляция request-id, трейсы), дисциплина CI. Что держит потолок: рантайм-архитектура local-PoC-происхождения (state в RAM, sync/async мосты, пересборки на запрос) ещё не догнала зрелость retrieval-слоя и безопасности. Ни один finding не блокирует текущую single-instance эксплуатацию; F-1/F-2/F-3 стоит закрыть до любого разговора о продакшн-нагрузке или нескольких репликах.

# Next Session: Fable hardening — продолжение (план)

## SESSION 5 (2026-06-13) — type-hardening: mypy strict-scope расширен (db/tasks/utils) + governance guard; LOCAL, push GATED ✅

Заход по «доработай проект, решай сам». Бэклог Fable-hardening пуст — взято следующее названное направление (расширение mypy strict-scope). Только типовые правки (поведение не менялось). **НЕ закоммичено, push/commit GATED.**

| Файл | Правка |
|---|---|
| `pyproject.toml` | `[[overrides]]`: `db.models` → `db.*`; новый блок `tasks.*`/`utils.*` (disallow_untyped_defs + disallow_incomplete_defs) |
| `utils/retry.py`, `utils/circuit_breaker.py` | `*args: Any, **kwargs: Any` у proxy-декораторов (`wrapped`, `CircuitBreaker.call`) |
| `db/crypto.py` | `encrypt`/`decrypt`/`EncryptedText.{bind,column}_expression` → `ColumnElement[Any]` (override-совместимо с базовым `TypeDecorator` → `ColumnElement[Any] \| None`) |
| `db/audit.py` | `purge_old_audit`: `getattr(result, "rowcount", 0) or 0` (base `Result` из `execute()` не объявляет `rowcount`; DELETE даёт `CursorResult`) |
| `tasks/ingest_task.py` | `ingest_document(self: Task, …)` + `from celery import Task` |
| `tests/test_precommit_config.py` | guard-тест `test_mypy_strict_scope_is_synced_across_gates` — идентичность strict-путей mypy в ci.yml/local-gate.ps1/autopilot.ps1 + пин модулей |
| `.github/workflows/ci.yml`, `scripts/local-gate.ps1`, `scripts/autopilot.ps1` | strict-команда синхронно: `db/models.py db/engine.py` → `db`, +`tasks utils` |
| `README.md`, `docs/CHANGELOG.md` | `db/` → «mypy --strict clean»; [Type-Hardening] + [Security] CHANGELOG-блоки |
| `requirements.txt`, `requirements.lock`, `requirements-dev.lock` | security-фикс (2-й коммит): `pypdf` 6.10.2→**6.13.2** (CVE-2026-48155/48156, fix 6.12.0) + floor `>=6.12.0`; uv `--upgrade-package pypdf --generate-hashes`, diff только pypdf |

**Верификация:** gated strict-mypy (новый scope) — **Success: no issues found in 30 source files, exit 0**; затронутые модули **66 passed / 3 skipped**; ruff clean; pip-audit на обновлённом lock — «No known vulnerabilities found, 2 ignored»; loader/ingest/governance **30 passed**. Гоча: `| tail` маскирует exit code mypy (первый «exit 0» был ложным) — гонять без `| tail`, читать `Found N errors`/`Success`. Гоча CI: type-правки не трогали security, но push словил свежую diff-независимую `pypdf`-CVE (security+pre-commit job = один pip-audit hook) — чинить bump'ом, не ignore (fix есть).

**Продолжение (по «продолжи», 3-й коммит):** `monitoring.*` (48) + `channels.*` (8) доведены до strict. `_NoopMetric` optional-dependency fallback решён **type-only**: union (`Counter|_NoopMetric` и т.п.) в `TYPE_CHECKING`-блоке на модуль — рантайм нетронут. channels: `payload.decode`→bytes narrow, imap `msg_data[0]`→tuple narrow, telegram `assert _session_class is not None`. pyproject+3 гейта+guard расширены (strict-scope = 11 целей). monitoring Success 2 files, channels Success 4 files. Гоча: mypy `--no-incremental` на channels тянет `agent.graph→langchain` граф, пик ~2.2GB (Windows-порог).

**Остаток (НЕ блокеры):** `customs-clearance-fields` retrieval-MISS (Kaggle, не Windows); дальнейший strict (api/ кроме app, evaluation/, ingestion/, tracing/, vectordb/) — крупный churn.

---

## SESSION 4 (2026-06-12) — F-14-хвост: path-дивергенция закрыта; warm-cache оставлен намеренно ✅

Бэклог Fable-hardening пуст; закрыт остаток F-14 (LOW, «по желанию»).

| Commit | Содержимое |
|---|---|
| `0a38756` | F-14 Issue 2: `_base_manager._project_root()` → корень репо (был папкой пакета). `_data_dir()`/`_build_chroma`/`_build_qdrant` писали «невидимый» стор в `vectordb/data/vectordb/`, отдельный от `settings.vectordb_chroma_dir` (`<root>/data/vectordb/chroma`). Выровнено с `config.settings.PROJECT_ROOT` и `mock_inbox._project_root`; guard-тест `test_data_dir_resolves_under_repo_root_not_package_internal` |

**F-14 Issue 1 (warm-cache `get_embeddings`/`get_reranker` не ключуется по модели) — НЕ менял, осознанно.** Текущее поведение (после первой загрузки `model_name` игнорируется, возвращается единственный закэшированный объект) **закреплено тестами** `test_base_manager.py:87`/`:110` (`get_embeddings("other-model") is embeddings`) и правдоподобно намеренно: модели тяжёлые (BGE-M3 ~2GB), держать две резидентно в памяти нежелательно. Менять test-pinned контракт на LOW/опциональном пункте — scope creep. Рекомендация: трогать только если реально понадобится warm-serving нескольких моделей одновременно (тогда — single-slot+model-name guard, чтобы перезагружать при смене имени без удержания двух моделей; не dict-кэш).

Верификация: `test_base_manager.py` 17 passed; `test_module_layout`/`test_manager_semantic_chunking`/`test_per_tenant_vectorstore` 17 passed; ruff + py_compile clean.

**PUSHED** (по явному «все решения принимаешь ты»): `51628e2..aacaa18`. CI run `27413770413` зелёный полностью. По ходу push CI словил **свежую CVE-2025-3000** (torch 2.11.0, local memory corruption в `torch.jit.script`, fix-версии нет) — pip-audit fail-closed. Добавил документированный `--ignore-vuln CVE-2025-3000` во все 4 точки (`97fdd6e` pre-commit + `aacaa18` ci.yml security-job + `local-gate.ps1` + `autopilot.ps1`); `torch.jit.script` к недоверенному вводу не подключён (только локальный sentence-transformers inference). Снять, когда выйдет upstream-фикс. `test_precommit_config.py` 11 passed, pip-audit hook локально Passed.

### Харденинг к оценке 9.8 (та же сессия, после push)

| Commit | Содержимое |
|---|---|
| `c8d9ea7` | autouse-фикстура `_disable_real_reranker_download` (`tests/conftest.py`): дефолтит reranker OFF на тестах. Виновник был `test_per_tenant_vectorstore::test_two_tenants_get_different_retrievers` (мокал Chroma/embeddings, не reranker → `get_retriever` тянул 2.3GB `bge-reranker-v2-m3` с HF). **Гоча `RAG_RERANKER_MODEL=""` УСТРАНЕНА В КОРНЕ** + де-флак CI HF-429. Полный unit-suite **862 passed / 4 skipped БЕЗ env-workaround** (17:47). |
| `b785a07` | guard-тест `test_pip_audit_ignore_set_is_synced_and_minimal`: запирает pip-audit `--ignore-vuln` ровно на 3 CVE во всех 4 точках (pre-commit/ci.yml/local-gate.ps1/autopilot.ps1). Запрет тихих suppression + защита от рассинхрона (на котором я словила красный CI). Reachability: `torch.jit.script` не используется, Chroma — embedded `PersistentClient`. |

**Гоча cont.14 БОЛЬШЕ НЕ В СИЛЕ:** полный suite гонять без `RAG_RERANKER_MODEL=""` — conftest сам отключает reranker. README:242 (env-таблица дефолта) — это продакшен-config, не тест-workaround, оставлен.

**Остаток:** бэклог Fable-hardening исчерпан, origin синхронизирован, CI зелёный.

---

## SESSION 3 (2026-06-11) — fable_com.md ЗАКРЫТ ПОЛНОСТЬЮ ✅

Гигиен-спринт §5 п.8 + F-4. Бэклог Fable-hardening пуст. 5 локальных коммитов
(push GATED, по явному запросу):

| Commit | Содержимое |
|---|---|
| `ebf50a6` | F-13: все env-поля Settings → `default_factory` + ast-guard + тест setenv-после-импорта |
| `1e0384f` | F-15: `inspect.signature` убран из hot path; контракты зафиксированы; 18 тест-файлов → реальные сигнатуры |
| `6326fdc` | фикс F-3-регрессии: `quality_source="llm"` только при реально распарсенном скоре (фейл был и до F-15) |
| `09a81ce` | F-16: audits → `docs/audits/`, sessions → `docs/sessions/`, AGENT_STATE 1184→659 строк, ссылки/regex/guards обновлены |
| `63a3ee4` | F-4: кэш runtime (profile+mtime) + compiled graph (id+strong refs, LRU 16); все 4 ловушки; `test_provider_runtime_cache.py` 6/6 |

Верификация: settings 79 · docs/autopilot 40 · F-4 acceptance 82 + streaming/integration 25 — все passed; ruff/mypy/py_compile clean. Гочи: `RAG_RERANKER_MODEL=""` для full suite (cont.14); `| tail` маскирует exit code pytest.

**Остаток (НЕ блокеры):** push 21 коммита (GATED); F-14-хвост — `_base_manager._project_root()` пишет «невидимый» стор в `vectordb/data/`, warm-cache `get_embeddings/get_reranker` не ключуется по имени модели (LOW).

---

## SESSION 2 (2026-06-11) — батч §1-6 закоммичен, F-5/F-18 доделаны ✅

Готовый батч верифицирован на этой машине и закоммичен **7 локальными коммитами на `master`** (НЕ запушено — push по явному запросу Юли):

| Commit | Содержимое |
|---|---|
| `2ee78a8` | metrics (bm25_enabled, quality_score_source, message_persist_failures, online_evaluators_dropped) |
| `544c3fc` | F-2 restore BM25 chunks из Chroma при старте + тесты (6/6) |
| `5f9194f` | F-1a/F-11 event-loop unblock (upload/analytics/providers) |
| `defe216` | F-9a/F-12 graph + 6 новых settings |
| `f8cc015` | F-3/F-8/F-7/F-17/F-6 streaming/cache/persist |
| `59df7c9` | **F-5/F-18** мост online-eval на main loop + drop-метрики + тест threadsafe-пути |

Верификация: §2 стрим/кэш-suite **49 passed**, F-2+routing **13 passed**, online-eval **19 passed** (incl. новый threadsafe), graph/routing/conversation **17 passed**, `api.app`/`agent.graph` import OK, ruff clean.

**Состояние дерева сейчас:** чисто, кроме чужих untracked (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`) — НЕ трогать.

### Сделано дополнительно в сессии 2 (после батча):
- **README + `.env.example` + `docs/CHANGELOG.md`** — 6 новых переменных задокументированы (+`STREAMING_QUALITY_EVAL` rollback-нота), [Fable-Hardening] CHANGELOG-блок. Коммит `1ed8efc`.
- **Гигиена #11 ЗАКРЫТА:** `.gitignore` уже содержал temp/coverage-паттерны; мёртвый корневой `cache.py` (затенён пакетом `cache/`) + тест → `archive-legacy/` (коммит `84de8e2`, тест 7/7 при прямом запуске); 76× `tests/pytest-cache-files-*` + 7× `.pytest-tmp-*` удалены (untracked).
- **Multi-worker инвариант ЗАКРЫТ** (`d805292`): выбрана опция 1 аудита — выровнял дефолты на 1 worker / 1 replica (`Dockerfile --workers 1`; helm `replicaCount: 1` + `autoscaling.enabled: false`), починил вводящий в заблуждение claim в `tracing/_base_trace.py`, добавил best-effort startup-warning на `WEB_CONCURRENCY>1` (срабатывает, старт не ломается) и секцию README «Deployment topology». Прошлый дефолт реально гонял 2 worker × 2–8 replica → ломал confirm-actions/сессии.

### Осталось — F-4 (де-скоуплено, спека для Codex написана):
- **F-4** (кэш runtime + compiled graph) → **`codex-tasks/task-F4-cache-runtime-graph.md`**. При разборе кода найдена **4-я ловушка, которой не было в исходном handoff**: `build_provider_runtime` гоняет `_enforce_daily_cost_limit` (per-request SQLite-проверка `DAILY_COST_LIMIT_USD`) — наивный кэш всего runtime молча отключит spend-cap (money-safety). Полный список ловушек (last_response / daily-cost / id()-ключ+GC / thread-safety), порядок шагов и тесты — в спеке. Это оптимизация (текущее поведение корректно), concurrency+money-sensitive → не шипить вслепую; гнать через Codex или отдельный аккуратный заход с concurrency- и cost-limit-тестами.

---

## (Историческая часть — план сессии 1, исполнен)

**Контекст:** сессия 2026-06-11. Аудит `fable_com.md` (18 findings) → пошла реализация плана §5.
**Состояние дерева: DIRTY НАМЕРЕННО, ничего не закоммичено.** 11 modified + 3 наших новых файла
(`fable_com.md`, `tests/test_chunks_restore.py`, `utils/event_loop.py`).
Чужие untracked из параллельной сессии — НЕ трогать: `docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`.

---

## 1. Что сделано (код готов)

| Finding | Файлы | Статус верификации |
|---|---|---|
| **F-2** restore chunks после рестарта: `chunk_index`-штамп при build, `_restore_chunks_from_store` (сорт. по chunk_index; legacy — stable sort по source), `_report_bm25_state` + gauge + warning | `vectordb/manager.py`, `tests/test_chunks_restore.py` | ✅ 6/6 passed |
| **F-1a** upload без блокировки event loop (`write_bytes`, `load_documents`, categorizer, rebuild → `asyncio.to_thread`) | `api/routers/upload.py` | ✅ в прогоне 38/39 (упавший 1 — контрактный, починен, см. F-17) |
| **F-10** РАЗРЕШЁН КАК «НАМЕРЕННО»: evaluate-на-fast — осознанный trade-off (strong в gracekelly-primary = ~60s orchestrate-вызов; коммит `7e266af`, пин-тест `test_build_support_graph_uses_fast_llm_for_evaluate_node`). Проводка `(llm_fast, llm_fast)` ОСТАВЛЕНА + задокументирована комментарием; suggest_questions → `llm_fast` (удешевление, ничем не пинится) | `agent/graph.py` (~:1833) | ✅ 47/48 первого прогона; пин-тест перегнан после отката (см. §2) |
| **F-12** verify_facts evidence-окно → settings (`fact_verify_context_max_docs`=5, `fact_verify_context_chars_per_doc`=3600) | `agent/graph.py`, `config/settings.py` | ⚠ таргетный тест не гонялся |
| **F-8** `graph_task`/`ask_args` инициализируются ДО `try` в `ask_stream` | `api/routers/conversation.py` | ✅ syntax, тесты стрима см. §2 |
| **F-7** LLM-кэш (чтение+запись) только при пустой истории сессии | `api/routers/conversation.py` | ⚠ см. §2 |
| **F-17** `AskResponse.cached: bool = False`; тест-ассерт обновлён (`get("cached") is False`) | `conversation.py`, `tests/test_llm_response_cache.py` | ⚠ см. §2 |
| **F-6** db persist timeout 0.5s → `db_persist_timeout_sec` (2.0) во всех 4 местах + counter `rag_message_persist_failures_total{operation}` | `conversation.py`, `api/app.py` | ⚠ см. §2 |
| **F-9a** `GraphState.quality_source` ("llm"/"fixed"/"heuristic"); evaluate→llm, 8 agentic-констант→fixed (патч проверен ast+grep); counter `rag_quality_score_source_total{source}` в /ask и стриме | `agent/state.py`, `agent/graph.py`, `conversation.py` | ✅ syntax; e2e см. §2 |
| **F-3** стрим: pipeline semaphore (+busy SSE event, finally release — disconnect-safe), дедлайн `streaming_timeout_sec` (120s) в обоих токен-циклах, **дешёвая parity** — один self-eval вызов (`streaming_quality_eval` default TRUE, откат env=false), route по `quality_threshold` при llm-оценке, `quality_source` в SSE result | `conversation.py`, `config/settings.py` | ⚠ см. §2 |
| **F-11** analytics ×4 + `/admin/providers` → `asyncio.to_thread` | `api/routers/analytics.py`, `api/routers/misc.py` | ⚠ test_analytics_dashboard в §2 |
| Метрики ×4: `RETRIEVER_BM25_ENABLED`, `QUALITY_SCORE_SOURCE_TOTAL`, `MESSAGE_PERSIST_FAILURES`, `ONLINE_EVALUATORS_DROPPED` (+helpers, noop, `__all__`) | `monitoring/prometheus.py` | ✅ импортится; `ONLINE_EVALUATORS_DROPPED` ещё НЕ подключён (ждёт F-5) |

Новые settings (все default_factory): `fact_verify_context_max_docs`, `fact_verify_context_chars_per_doc`, `online_evaluators_timeout_sec` (1.0), `db_persist_timeout_sec` (2.0), `streaming_quality_eval` (true), `streaming_timeout_sec` (120).

## 2. Верификация стрим/кэш-правок — СДЕЛАНА в конце сессии 1

Итог прогона (исправленная команда ниже): **47 passed / 1 failed** за 130s.
Единственное падение — `test_build_support_graph_uses_fast_llm_for_evaluate_node`,
вскрывшее, что старая проводка evaluate была намеренной (см. F-10 в §1) → моя
правка откатана, после отката перегнаны `test_magic_numbers_settings.py` +
`test_model_routing.py` (результат см. в конце файла / AGENT_STATE).
Тесты стрима/кэша/analytics прошли БЕЗ правок — контракт `quality_source`/`cached`
обратно совместим с существующими ассертами.

⚠ Гоча: файла `tests/test_analytics_dashboard.py` НЕ существует (правильное имя —
`tests/test_analytics.py`); из-за этой опечатки первый «прогон» сессии вообще
не запускался (pytest: «no tests ran» — exit code пайпа с `tail` маскирует это).
Рабочая команда:

```bash
RAG_RERANKER_MODEL="" python -m pytest tests/test_chat_streaming.py tests/test_streaming_rag_parity.py \
  tests/test_llm_response_cache.py tests/test_analytics.py tests/test_conversation_router.py \
  tests/test_citations.py tests/test_magic_numbers_settings.py tests/test_online_evaluators.py \
  -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-fable
```
Вероятные точки падения: тесты стрима, ассертящие `quality_score == 70` (теперь self-eval может вернуть другое — если фейковый LLM в тесте отвечает числом) и отсутствие `quality_source` в ожидаемом payload. Чинить тесты под новый контракт, НЕ откатывая parity (это суть F-3); при необходимости в конкретном тесте — `settings_factory(streaming_quality_eval=False)`.

Затем `ruff check agent api config monitoring vectordb utils tests/test_chunks_restore.py`.

## 3. In flight: F-5 + F-18 (Task #7) — НЕ ДОДЕЛАНО

`utils/event_loop.py` создан (set/get_main_loop), **нигде не подключён** (безопасно). Осталось:

1. `api/app.py` `_lifespan`: на старте `set_main_loop(asyncio.get_running_loop())`, в `finally` — `set_main_loop(None)`.
2. `agent/graph.py` `run_qa_pipeline`, блок online evaluators (`asyncio.run(_persist_results())` + `engine.dispose()`):
   - `_persist_results(dispose_engine: bool)`; таймаут из `settings.online_evaluators_timeout_sec`;
   - на `asyncio.TimeoutError` → `record_online_evaluators_dropped("timeout")`, на прочее → `("error")` (метрика уже есть);
   - `main_loop = get_main_loop()`; если есть, жив и НЕ текущий running loop → `fut = asyncio.run_coroutine_threadsafe(_persist_results(False), main_loop)`; `fut.result(timeout=timeout_sec + 10)` (семантика «персист до ответа» сохраняется, dispose НЕ нужен — пул живёт в main loop);
   - иначе (sync-скрипты) — старый путь `asyncio.run(_persist_results(True))` с dispose; **сохранить комментарии Bug 2/Bug 4**.
3. Тесты: `tests/test_online_evaluators.py` должен остаться зелёным (sync-путь); добавить тест threadsafe-пути (поднять loop в фоновом потоке, set_main_loop, позвать run_qa_pipeline из главного, проверить отсутствие dispose — например, monkeypatch на engine.dispose со счётчиком).

## 4. Не начато

- **F-4** кэш provider runtime + compiled graph. **ЛОВУШКА:** `ProviderBackedLLM.last_response` — мутируемое per-instance состояние; при глобальном кэше runtime конкурирующие запросы перепутают usage. Сначала `threading.local` для `last_response` в `llm/providers/base.py`, потом кэш по (resolved profile, mtime providers.yml), потом кэш compiled graph по `(id(retriever), id(llm_fast), id(llm_strong), min_quality)`.
- **Гигиена** (#11): `.gitignore` += `.pytest-tmp-*/`, `tests/pytest-cache-files-*/`, `.coverage`; корневой `cache.py` (мёртвый, затенён пакетом `cache/`) → `archive-legacy/` вместе с `tests/test_rag_cache.py`; 76 каталогов `tests/pytest-cache-files-*` удалить.
- README: env-таблица для 6 новых переменных + `STREAMING_QUALITY_EVAL` rollback; `docs/CHANGELOG.md`.
- fable_com.md §5 пп. 7-8 (multi-worker инвариант, F-13/F-15) — отдельные циклы.

## 5. Коммиты (после зелёной верификации §2; push — только по явному запросу Юли)

Нарезка: (1) metrics; (2) F-2 retrieval restore + тесты; (3) F-1a/F-11 event loop unblock; (4) graph F-10/F-12/F-9a; (5) streaming F-3/F-8; (6) cache/persist F-7/F-17/F-6; (7) F-5 после доделки. `fable_com.md` + handoff-доки — отдельным docs-коммитом.

## 6. Гочи сессии

- `manager.get_retriever(embeddings=None)` в тестах тянет **реальный BGE-M3** → всегда стабовать `manager.get_embeddings` (fixture-образец в `tests/test_chunks_restore.py`). Зависший python: `taskkill //F //FI "IMAGENAME eq python.exe"`.
- Контракт изменён: `/api/ask` всегда отдаёт `cached: bool`; SSE result несёт `quality_source`.
- Поведение: evaluate на complex → strong-модель (дороже/медленнее при профиле с разными моделями); suggest_questions → fast (дешевле); стрим +1 LLM-вызов (откл. `STREAMING_QUALITY_EVAL=false`).
- Полный suite на этой машине — только с `RAG_RERANKER_MODEL=""` (гоча cont.14).

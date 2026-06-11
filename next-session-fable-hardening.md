# Next Session: Fable hardening — продолжение (план)

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

### Осталось (отдельные циклы — требуют осторожности/решения, НЕ начато):
- **F-4** — кэш compiled graph + provider runtime. **Ловушка** `ProviderBackedLLM.last_response` (читается в `agent/graph.py:557` `_capture_llm_usage` сразу после invoke): сегодня гонки нет (свой llm-инстанс на запрос), но глобальный кэш runtime/graph → шаринг инстанса между потоками (`run_qa_pipeline` в `asyncio.to_thread`) → перепутанный usage. Нужно: `threading.local` для `last_response` в `llm/providers/base.py` (6 set-мест + read в graph + тесты `test_provider_abstraction`), затем кэш runtime по (resolved profile, mtime `providers.yml`), затем кэш compiled graph по `(id(retriever), id(llm_fast), id(llm_strong), min_quality)` — внутри `build_support_graph`. Concurrency-sensitive → кандидат на второе мнение Codex (§7) + concurrency-тест.
- **Multi-worker инвариант** (§3 аудита) — РЕШЕНИЕ: задокументировать «1 worker / 1 replica» (runbook + helm values + честная правка claim в `tracing/_base_trace.py` про «workers 2») ИЛИ перенести session-state/pending-actions в Redis/Postgres. Осторожно: жёсткий startup-assert на >1 worker сломает helm, который сейчас деплоит с воркерами — безопаснее warning + выравнивание манифестов.

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

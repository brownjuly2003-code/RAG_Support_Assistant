# Доработки по FLANT_DOGFOOD_FINDINGS (2026-06-18)

## Goal
Закрыть 5 практических шероховатостей дожфуда (внешний домен Deckhouse/werf): тихая
деградация online-evaluators, видимость прогресса/конкуренция при contextual-ingest,
опц. wall-budget на прямой `ask`, remote-embedding backend, headless-safe reload.

## Контекст / поправка к находке #1
Реальный путь дожфуда (`D:/Flant_new/data/rag_runner.py`) идёт через
`manager.build_vector_store` с `llm=None` → contextual-headers строятся из metadata
(БЕЗ сети). LLM-путь живёт только в `IngestPipeline` за `ingestion_batch_enabled=false`
и работает **по документу, не по чанку**. 20-мин «вис» на 2000 чанков — это CPU-эмбеддинг
(≈1.3 c/чанк), а не LLM. → НЕ меняем дефолт `contextual_headers`; чиним видимость
прогресса (реальный дефицит — «не отличить медленно от завис») + конкуренцию LLM-fallback.

## Tasks
- [ ] #5 `main.py`: reload через `UVICORN_RELOAD` (default false, headless-safe) → Verify: `python -c "import main"` + unit на env-парс.
- [ ] #2 `agent/graph.py`: online-evaluators деградируют тихо — connection-ошибки (no Postgres) логируются WARN один раз/процесс, дальше debug; счётчик prometheus сохраняем → Verify: новый unit `test_online_evaluators_quiet` (2 запроса → 1 warning).
- [ ] #1a `ingestion/pipeline.py`: sequential-fallback contextual headers → bounded-concurrency (`INGESTION_CONTEXTUAL_CONCURRENCY`, default 4) + прогресс-лог `[contextual_headers] i/N` → Verify: unit с fake-llm считает вызовы/лог.
- [ ] #1b `vectordb/manager.py` `build_vector_store`: info-лог до/после тяжёлого embed (N чанков, device, elapsed) → Verify: unit ловит лог-строку.
- [ ] #3 `agent/graph.py` `ConversationSession.ask`: опц. wall-budget `RAG_ASK_BUDGET_SEC` (default 0=off) — мирроринг API (`asyncio.wait_for(to_thread)` → здесь thread+`future.result(timeout)`), на таймаут — graceful degraded GraphState → Verify: unit с медленным fake-pipeline.
- [ ] #4 `vectordb/_base_manager.py`: `_RemoteEmbeddings` (httpx, OpenAI/Mistral `/v1/embeddings`, L2-norm, батч) под `RAG_EMBEDDING_BACKEND=remote`; ключ из env по имени (как MistralProvider) → Verify: unit с fake-httpx (без сети) — батчинг/норма/контракт.
- [ ] settings.py: новые поля (`ask_budget_sec`, `embedding_backend`+remote-*) с env-алиасами.
- [ ] Доки: `docs/CONFIGURATION.md` + README — стоимость contextual-ingest, remote-embedding, новые флаги; `docs/CHANGELOG.md`.

## Done When
- [ ] ruff clean; целевые unit-тесты зелёные на Windows; mypy на изменённых лёгких модулях чист (graph/vectordb — через CI/Linux, как принято).
- [ ] Поведение по умолчанию НЕ меняется (все новые рычаги opt-in/без сети по дефолту).

## Notes
- Mac-only/тяжёлое (реальный remote-embed прогон с ключом, полнокорпусный ingest) — НЕ блокер; код+unit на Windows, реальная верификация по запросу.
- Ключи НЕ хардкодить/не печатать; remote-embed читает имя env-переменной из конфига.

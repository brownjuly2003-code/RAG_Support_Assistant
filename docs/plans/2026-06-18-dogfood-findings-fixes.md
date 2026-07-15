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
- [x] #5 `main.py`: reload через `UVICORN_RELOAD` (default false, headless-safe) → shipped `1343323`.
- [x] #2 `agent/graph.py`: online-evaluators деградируют тихо → shipped `1343323` + unit quiet dedup.
- [x] #1a `ingestion/pipeline.py`: bounded concurrency + progress log → shipped `1343323`.
- [x] #1b `vectordb/manager.py` embed progress log → shipped `1343323`.
- [x] #3 wall-budget `RAG_ASK_BUDGET_SEC` → shipped `1343323` + `tests/test_ask_wall_budget.py`.
- [x] #4 remote embeddings `RAG_EMBEDDING_BACKEND=remote` → shipped `1343323` + `tests/test_remote_embeddings.py`.
- [x] settings.py fields + CONFIGURATION / CHANGELOG.

## Done When
- [x] ruff clean; целевые unit-тесты зелёные; defaults unchanged (opt-in levers only).

## Notes
- Mac-only/тяжёлое (реальный remote-embed прогон с ключом, полнокорпусный ingest) — НЕ блокер; код+unit на Windows, реальная верификация по запросу.
- Ключи НЕ хардкодить/не печатать; remote-embed читает имя env-переменной из конфига.

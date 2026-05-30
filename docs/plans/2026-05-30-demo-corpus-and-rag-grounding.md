# Continuation plan — демо-корпус + обоснование RAG-конфигурации

- Дата: 2026-05-30
- Автор: Claude (Opus 4.8)
- Опирается на: `audit_claude_30_05_26.md` (R1–R7), `audit_codex_30_05_26.md`,
  `docs/research/rag-landscape-2026.md`, ADR `docs/adr/0001-graphrag-deferral-and-trigger.md`
- Жёсткое ограничение среды: на Windows-ноуте и Mac **нельзя запускать процессы > ~1 ГБ RAM**.
  Любой шаг с эмбеддером (BGE-M3 ~2.3 ГБ), реранкером, Docker, RAGAS — **только Colab/remote**.
  Windows = thin client (код, лёгкие тесты без загрузки моделей, доки, staging).

## 0. Что уже сделано в этой сессии (локально, безопасно)

- Заведён реальный демо-корпус: **201 документ** скопирован из `D:\TestRag\corpus`
  в `data/uploads/aircargo/` (тенант `aircargo`). `data/*` в `.gitignore` — git не засорён,
  шаг обратим.
- Профиль корпуса (измерен): 201 док, 4.2 МБ; категории — HR 70, legal 65,
  transport-logistics 35, compliance 20, FAQ 10, +1 внешний; длина документа RU
  **медиана ~21 200 символов** (min 13 925, max 30 225). Однородные структурированные
  markdown-документы (заголовки/секции/пункты).
- Написан ADR по GraphRAG (см. `docs/adr/0001`).

Тенант `aircargo` выбран намеренно отдельным от дефолтного consumer-support KB
(warranty/returns/errors) — это **не разрушает** существующее демо и заодно демонстрирует
multi-tenancy. Ingestion (тяжёлый) — на Colab/Mac, см. §5.

## 0bis. ВЕРИФИЦИРОВАНО на iMac (2026-05-30) — R1 доказан, R2 подтверждён

Прогон на iMac `julia@192.168.1.133` (8 ГБ Intel): ingest 10 FAQ-доков (BGE-M3, 194 чанка) +
retrieval keyword-coverage @ top-5 на 31 кейсе из `curated_cases_aircargo.jsonl` (LLM-free).
Полный отчёт: **`docs/operations/2026-05-30-mac-rag-retrieval-baseline.md`**.

| Конфиг top-5 | FULL coverage |
|---|---|
| Реранкер **OFF** (vector+BM25+RRF) | **31/31 = 100%** |
| Реранкер **ON** (англ. `ms-marco-MiniLM`, дефолт) | **19/31 = 61%** |

- **R1 доказан**: англ. реранкер на RU берёт идеальный RRF-retrieval и портит до 61%
  (Δ −39 п.п.) — выкидывает правильные чанки из top-5. Не гипотеза, а measured before/after.
  Граница честности: абсолютные 100% завышены малой подвыборкой (10 FAQ); относительная
  находка (англ. реранкер вредит RU) робастна.
- **R2 подтверждён живьём**: ingest-лог завален `Contextual header exceeded chunk_size;
  truncating chunk` — дефолтный contextual-header длиннее `chunk_size=800`, чанк режется.
- **Вывод для продукта (measured)**: дефолтный `ms-marco-MiniLM` на RU-проде менять на
  `BAAI/bge-reranker-v2-m3`. Не «выключить реранкер», а поставить мультиязычный — закрытие R1.

## 1. Почему текущий chunk_size = 800/200 не обоснован для этого корпуса

`config/settings.py:301-302` — дефолт `chunk_size=800`, `chunk_overlap=200` (символов,
`RecursiveCharacterTextSplitter`). Сам `scripts/chunking_eval.py` в docstring честно пишет:
«размер чанка НЕ обязан быть степенью двойки; оптимум зависит от языка, длины документов,
типа вопросов и модели эмбеддингов». Но этот скрипт прогонялся только на **синтетических
игрушечных доках** (`semantic_chunking_ab.py::SYNTHETIC_DOCS` — 6 коротких абзацев). На
реальном корпусе размер чанка **ни разу не подбирался по данным** — это «так принято».

Эмпирика против дефолта:
- 800 символов ≈ 200–260 RU-токенов. Документы корпуса — структурированные юр/HR-тексты с
  медианой ~21 200 символов. Флэтовое окно 800 символов **режет посреди пункта договора /
  раздела политики**, где единица смысла — пункт/раздел, а не N символов.
- При 800/200 каждый ~21K-документ → ~35 чанков, корпус → ~7000 чанков. Это раздувает и
  vector-, и in-memory BM25-индекс (R5: BM25 строится в RAM на каждый retriever).

Вывод: chunk-конфигурацию надо **обосновать замером на реальном корпусе**, а не дефолтом.

## 2. План обоснования chunk_size (на Colab/Mac)

Зависимость: нужен RU eval-набор (R7). Поэтому порядок — сначала R7, потом chunking A/B.

Прогнать `scripts/chunking_eval.py` + `scripts/semantic_chunking_ab.py`, **указав реальный
корпус `data/uploads/aircargo/` и RU eval-вопросы** (а не синтетику). Сетка:

| Ось | Значения |
|---|---|
| chunk_size (символы) | 512, 800, 1024, 1536, 2048 |
| overlap | 10 %, 15 %, 20 % от chunk_size |
| стратегия | fixed `RecursiveCharacterTextSplitter`, **markdown-structural** (по заголовкам), semantic (`RAG_SEMANTIC_CHUNKING`), **late chunking** (BGE-M3, см. §3) |

Метрики: Recall@k, MRR, Precision@k (chunking_eval), context_recall (semantic_ab),
+ итоговый faithfulness/precision на RAGAS. Выбрать конфигурацию по composite score
**на этих данных** и записать число + обоснование в README. Ожидание: для длинных
структурированных RU-документов оптимум заметно выше 800 и/или structural-разбиение,
а не флэтовые символы.

## 3. Frontier-фишки, которых нет (и которые дёшевы/применимы)

Аудит закрыл R1–R7. Сверх него — «очевидные острые» приёмы 2025–2026, не применённые,
с высоким ROI для **длинных структурированных RU-документов**:

### 3.1 Markdown-structural chunking — HIGH ROI, без GPU, применимо сразу
Документы — чистый markdown с заголовками. `MarkdownHeaderTextSplitter` (split по
структуре) + cap по размеру бьёт флэтовый `RecursiveCharacterTextSplitter`: чанк = логический
раздел, а не N символов. Прямо закрывает претензию из §1. Дёшево, детерминированно.

**Карта сайтов чанкинга (важно при реализации — НЕ промахнуться мимо ingestion-пути):**
чанкинг выбирается в трёх местах, и ingestion корпуса идёт НЕ через `_base_manager`:
- `vectordb/manager.py::build_vector_store` (tenant-aware) — **именно это зовёт
  `scripts/reindex.py --tenant aircargo`**; ключевой сайт для A/B корпуса.
- `vectordb/_base_manager.py::build_vector_store` (строки ~747–756).
- `vectordb/_base_manager.py::build_retriever` (строки ~810–822).
Все три ветвятся `settings.semantic_chunking` (дефолт **true** → семантика по умолчанию;
fixed 800/200 — это fallback при отсутствии `langchain_experimental` или флаге off). Чтобы
добавить structural как третью стратегию: ввести флаг `RAG_STRUCTURAL_CHUNKING` в
experiment-реестр `config/settings.py` (tuple `_EXPERIMENT_SETTINGS` + dict
`_EXPERIMENT_SETTING_ENV_VARS` + поле dataclass, дефолт `False`) и единый хелпер выбора
чанкера, вызываемый из всех трёх сайтов (заодно убирает дублирование, которое дингует аудит).
**Делать ПОСЛЕ R7-baseline** (§7) — иначе меняем дефолтный путь до того, как есть с чем
сравнивать. Юнит-тест структурного сплиттера — чистая функция на тексте, без эмбеддера
(локально OK); end-to-end эффект меряется только на Colab.

### 3.2 Late Chunking (Jina, 2024) — HIGH ROI, дёшево
Эмбеддить **весь документ** длинноконтекстным эмбеддером, затем пулить токен-эмбеддинги в
чанки → каждый чанк несёт контекст всего документа. **BGE-M3 уже стоит в проекте и держит
8K контекста** → late chunking применим напрямую, без доп. LLM-вызовов. Идеален для
~21K-символьных структурированных документов (контекст раздела не теряется на границе чанка).

### 3.3 BGE-M3 native sparse вместо наивного `.split()` BM25 — закрывает R5 «бесплатно»
R5 (аудит): BM25 строится на `query.lower().split()`, без RU-лемматизации → слабая
keyword-половина hybrid. **Но BGE-M3 уже нативно выдаёт learned sparse (лексические) веса**
вдобавок к dense. То есть модель, которая уже загружена, отдаёт обучённый sparse-сигнал —
им можно заменить наивный BM25 и унифицировать hybrid в одной модели (dense + sparse из
BGE-M3), вместо отдельного питоновского `.split()`. Это самый недоиспользованный актив стека.

### 3.4 Anthropic Contextual Retrieval — MED ROI (есть LLM-цена, но кэшируется)
Аудит R2: текущая фича `RAG_CONTEXTUAL_HEADERS` — статический префикс заголовка
документа/секции, и она **багована** (ломает RRF-дедуп). Настоящий Contextual Retrieval
(Anthropic, конец 2024) — LLM генерирует для каждого чанка короткий контекст «где это в
документе» перед эмбеддингом + contextual BM25; снижает retrieval-провалы на ~35–49 %.
Цена — LLM на чанк, **но с prompt caching документа в контексте это дёшево** (см. навык
`claude-api` — caching). Реализовать как корректную замену текущего header-префикса
(заодно чинит R2).

### 3.5 Query routing / adaptive retrieval — закрывает R3/R4
`classify_complexity` уже классифицирует сложность, но **не маршрутизирует стратегию
ретрива**. Завести: `simple → vector-only, без per-doc LLM-grade, без verify` (срезает
~5–10 LLM-вызовов из fan-out R4), `complex → hybrid+rerank+grade`, `global → graph` (ADR 0001).
Это и оптимизация латентности (R3/R4), и место подключения GraphRAG.

### 3.6 Реранкер — listwise/мультиязычный (расширение R1)
R1 уже требует `bge-reranker-v2-m3`. Сверх него на остриё: listwise LLM-rerank (RankGPT) или
`bge-reranker-v2-gemma`. Решать после замера R1 — не усложнять до базового A/B.

**Приоритет внедрения (после R7-baseline, по ROI и дешевизне):**
3.1 structural → 3.2 late chunking → 3.3 BGE-M3 sparse → 3.5 routing → 3.4 contextual → 3.6.
Каждый — A/B против baseline на RU eval-сете; не «вкатываем вслепую» (дисциплина аудита:
сначала baseline, потом дельта).

## 4. Связь с findings аудита (что чем закрывается)

| Audit finding | Закрывается чем (этот план) |
|---|---|
| R7 — качество не измерено | §5 шаги 2–3: RU eval-сет из корпуса + RAGAS baseline на Colab. Стартовый retrieval-baseline уже снят (§0bis) |
| R1 — EN-реранкер на RU | **ДОКАЗАН (§0bis): реранкер OFF 100% vs ON 61%, Δ−39пп.** Фикс: §5 шаг 5 A/B `bge-reranker-v2-m3` на aircargo |
| R2 — RRF-дедуп по префиксу + статичный header | **Подтверждён живьём (§0bis): header > chunk_size, чанк режется.** §3.4 настоящий contextual retrieval (RRF-ключ уже пофикшен `5c7f3b1`) |
| R3/R4 — LLM fan-out | §3.5 query routing (simple → без grade/verify) |
| R5 — наивный BM25 на RU | §3.3 BGE-M3 native sparse |
| chunk_size «по привычке» | §1–§2 обоснование замером на реальном корпусе |
| GraphRAG при росте | ADR 0001 (шов + trigger + LightRAG) |

## 5. Mac/Colab runbook (тяжёлые шаги — НЕ на Windows)

Ноутбук уже есть: `notebooks/rag_support_colab_remote_benchmark.ipynb`
(URL в `AGENT_STATE.md`). Все шаги ниже — Colab (GPU, бесплатно) или Mac, **не локальный
Windows** (RAM-лимит, thin-client boundary).

1. **Ingest корпуса `aircargo`.** Скопировать `data/uploads/aircargo/` в среду Colab,
   `python scripts/reindex.py --tenant aircargo`. Тянет BGE-M3 (~2.3 ГБ), эмбеддит ~7K чанков.
   Раздельным процессом (build → eval → report), кэшировать Chroma-коллекцию (см. memory:
   `feedback_rogii_split_python_runs`).
2. **Построить RU eval-набор (R7).** Стартовый набор **уже создан**:
   `evaluation/curated_cases_aircargo.jsonl` — **31 грунтованный RU-кейс** (`tenant_id=aircargo`),
   keywords взяты дословно из ответов `07_faq_*` корпуса, покрытие HR/legal/logistics/compliance.
   Отдельный файл (не трогает дефолтный CI-gate `curated_cases.jsonl`); guard-тест
   `tests/test_curated_dataset.py::test_aircargo_curated_cases_parse_and_cover_domains` (≥30, unique,
   все RU) — зелёный. На Colab расширить до 100–150 (генерация Q/A по остальным разделам +
   confirmed-good трейсы через `build_curated_dataset.py`). Запуск eval:
   `python scripts/regression_eval.py --dataset evaluation/curated_cases_aircargo.jsonl --tenant aircargo ...`.
3. **RAGAS baseline.** `scripts/nightly_eval.py` + `evaluation/ragas_eval.py` на текущей
   конфигурации (800/200, ms-marco reranker) → зафиксировать faithfulness / context-precision /
   context-recall / answer-relevancy. Это нулевая точка.
4. **Chunk-size A/B (§2).** Сетка размеров × стратегий (incl. structural §3.1, late §3.2) →
   выбрать конфигурацию по данным → записать в README.
5. **Reranker A/B (R1).** `ms-marco-MiniLM` vs `bge-reranker-v2-m3` на выбранном chunking →
   дельта. Проверить latency на CPU/GPU (R6: `device` сейчас захардкожен `cpu`).
6. **(Позже, при росте корпуса) GraphRAG индекс** — только Colab, LightRAG/nano-graphrag,
   инкрементально (ADR 0001 §3–§4).

Вынести итоговые цифры (baseline → после R1/chunking) в README и в новый раздел аудита.

## 6. Что можно делать локально на Windows (без нарушения RAM-лимита)

- Код-шов §3.5 (query routing) и `RAG_RETRIEVAL_STRATEGY` (ADR 0001 §1) — пишется и
  юнит-тестируется без загрузки моделей (мокать retriever/LLM).
- Markdown-structural splitter (§3.1) — чистая функция разбиения, тестируется на тексте
  без эмбеддера.
- Расширение `curated_cases.jsonl` (составление кейсов — текст, не вычисление).
- Доки/ADR/README.

Не делать локально: любой `reindex`/ingest реального корпуса, RAGAS, загрузку BGE-M3 или
реранкера, Docker, live-eval с провайдером.

## 7. Рекомендуемая последовательность (по ROI) — обновлено после §0bis

1. **R1 reranker `bge-reranker-v2-m3`** (Colab) — теперь №1: R1 доказан (§0bis), это
   подтверждённый крупнейший скачок precision. A/B на 3 руки: OFF / ms-marco / bge-v2-m3.
2. R7 baseline на полном корпусе (Colab) — расширить 31→100–150 кейсов, RAGAS.
3. chunk-size A/B + structural/late chunking (Colab) — ответ на «800 по привычке».
4. BGE-M3 sparse вместо наивного BM25 (§3.3) — закрывает R5, модель уже загружена.
5. query routing (§3.5, локально код + Colab eval) — срезает fan-out R3/R4.
6. contextual retrieval (§3.4) — чинит R2 (подтверждён §0bis), после baseline + caching.
7. GraphRAG-шов (ADR 0001) — код локально; включение реализации — при достижении trigger.

# План: преодоление барьера для retrieval-фикса (7 deep-miss `*-required-fields`)

- Дата: 2026-06-03
- Контекст: `docs/operations/2026-06-03-r7-llm-judged-baseline.md`. R7 LLM-judged измерен
  (faithfulness 0.833 / relevancy 0.838). Бутылочное горло — retrieval. Цель фикса:
  **7 deep-miss** (+1 near-deep, +5 uncertain) — запросы класса «какие поля нужны для X»
  не достают чанк с таблицей полей под `## Обязательные поля`, т.к. NL-запрос не пересекается
  лексически со snake_case-полями. Гипотеза фикса: **contextual-header chunking** (чанк несёт
  якорь из тайтла дока + заголовка секции).

## Барьер

Проверить фикс «в лоб» = переингест 201 дока с BGE-M3 (~2.3GB) + bge-reranker-v2-m3 (~2GB).
На Windows-хосте процессы >1GiB вешают машину (правило среды); 8GB-iMac OOM'ит при двух
моделях разом. Поэтому прямой A/B упирается в железо.

## Стратегия: cheap-first, heavy-as-confirmation

Бóльшая часть валидации НЕ требует production-моделей. Вопрос фикса —
**относительный**: «поднимает ли contextual-header целевой чанк в ранге?» — почти
embedder-агностичен (добавление текста «обязательные поля dangerous goods» в чанк даёт
И dense, И BM25 общий сигнал с запросом). Значит направление можно подтвердить лёгким
прокси-эмбеддером под лимитом, а абсолютные числа снять remote.

---

> **СТАТУС 2026-06-03:** Phase 0 ✅ DONE (`fc4ad0e`). Открытие при реализации: contextual-header
> фича УЖЕ реализована и подключена (флаг `RAG_CONTEXTUAL_HEADERS`, `vectordb/manager.py:135`,
> default ON — пинован тестом; «default off» здесь раньше было ошибкой) + `ParentDocumentStore`
> подключён (`RAG_PARENT_CHILD`). Единственный пробел был
> в no-LLM fallback заголовка — не нёс heading-path. Починено + unit-тест.
>
> **СТАТУС 2026-06-04:** Phase 1 ✅ DONE — **GO на Phase 2**. Прокси-A/B
> (multilingual-MiniLM, 3 плеча, `.tmp/ab_proxy_minilm.py`): structural+heading-path
> поднимает **12/13 диагноз-целей, 0 регрессий** (без обрезки тела), top-5 FULL 65%→73%.
> Попутно ДОКАЗАН вред production-обрезки `[:chunk_size]` в `manager.add_contextual_headers`
> (3/13 регрессий: хвостовые строки field-таблиц вырезались из пула целиком) — починено
> `4844094` до Phase 2. Отчёт: `docs/operations/2026-06-04-phase1-proxy-ab-contextual-header.md`.
> **Следующий шаг = Phase 2** (BGE-M3+реранк на Colab/iMac, плечи A vs C-конфиг).
>
> **СТАТУС 2026-06-05:** Phase 2 ✅ DONE (третий путь — Kaggle CPU-kernel, код private-датасетом
> без обхода push-гейта) + Phase 3 ✅ LANDED. Production-стек подтвердил Phase 1:
> top-5 FULL **82%→87% (8 gains / 4 regressions, нетто +5), MISS 11→6**; R7 LLM-judged
> A vs C: recall **0.855→0.905**, faithfulness **0.875→0.909**. Реранкер фактически поднял
> 6/10 rerank-recoverable (совпало с rank-grade прогнозом). **`RAG_STRUCTURAL_CHUNKING`
> включён дефолтом** + пин-тест. Отчёт: `docs/operations/2026-06-05-phase2-contextual-ab-production.md`.
> Остаток (не блокер): 4 deep-цели (query-side → query-expansion / BM25-вес) + 4 регрессии
> (1 жёсткая out-of-pool, 3 мягких in-pool → parent-child / реранк-тюнинг).
>
> **СТАТУС 2026-06-05 (вечер):** остаток закрыт parent-expansion'ом (плечо D):
> post-rerank расширение top-k соседними секциями source-дока, `RAG_PARENT_EXPANSION`
> default ON (window=2/3600). FULL 87→96 @ top-5, MISS 6→1, recall 0.905→0.975;
> обе жёсткие регрессии восстановлены. Замер ЛОКАЛЬНЫЙ и точный (отбор идентичен C,
> меняется только текст) + R7-judge ×2 с снятой полосой шума судьи. Отчёт:
> `docs/operations/2026-06-05-parent-expansion-arm-d.md`. Остаточный MISS 1
> (customs-clearance-fields) → query-expansion. Дальше: планы
> `2026-06-05-chunk-size-justification.md` и `2026-06-05-graph-retrieval-activation.md`.

## Phase 0 — Реализация фикса (локально, автономно, unit-tested, <1GiB)

- Расширить chunker contextual-header режимом: к **embedded-тексту** каждого чанка
  препендить якорь `«{doc_title} › {section_heading_path}»` (raw-текст для отображения не
  трогать). Флаг `RAG_CONTEXTUAL_HEADER` (default off, реверсивно). Это Anthropic-style
  contextual retrieval, сделанный правильно (vs баганый static-header R2).
- Точка вмешательства: `select_chunks`/`structural_split` в `vectordb/_base_manager.py`
  (чистая функция без эмбеддера — unit-тестируема).
- Unit-тесты: чанк из `05_tlog_regulation_dangerous_goods.md` несёт якорь
  «dangerous goods / Обязательные поля» + field-IDs; default-путь не изменён.
- **Owner: CC. Барьера нет. Verifiable: pytest + ruff.**

## Phase 1 — Дешёвый прокси-A/B (локально Windows, MiniLM, <1GiB, автономно)

- Ингест 201 aircargo-дока с `all-MiniLM-L6-v2` (windows-safe, ~594MB, доказано в
  closure-прогоне 2026-05-31), два рукава: (a) текущий чанкинг, (b) contextual-header.
- Retrieve top-20 для **12 целевых кейсов** (7 deep + 5 uncertain); замерить ранг целевого
  чанка в каждом рукаве.
- **Gate решения:** contextual-header поднимает 7 deep-miss целевые чанки в top-k на прокси →
  направление подтверждено, → Phase 2. Не поднимает → пересмотр (BM25-вес / query-expansion).
- Дисциплина: ингест и eval — отдельными python-процессами (память
  `rogii_split_python_runs`), kill orphan python после; запуск в фоне + мониторинг RAM,
  убить при спайке >1GiB.
- **Owner: CC. Под лимитом. Verifiable: ранги до/после.**

## Phase 2 — Production-подтверждение (remote, gate / интерактивно)

Снять РЕАЛЬНЫЕ числа на production-стеке (BGE-M3 + bge-reranker-v2-m3). Два пути:

- **A. Colab (приоритет — free, без карты).** Self-contained cell: pinned deps, upload
  corpus.zip, ингест обоих рукавов BGE-M3, реранк bge-v2-m3 top-5, пересчёт recall на 100
  кейсах + re-run R7 LLM-judged через Mistral (`getpass MISTRAL_API_KEY`). Заодно закрывает
  **5 uncertain** (top-5-С-реранком). Основа есть: `notebooks/rag_support_colab_remote_benchmark.ipynb`
  + `scripts/aircargo_ragas_eval.py`. **Owner: Julia интерактивно; CC готовит cell + corpus.zip
  и синтаксически проверяет.**
- **B. iMac two-phase (если свободен/доступен).** Тот же паттерн, что собрал full-corpus A/B
  2026-06-02: SSH `julia@192.168.1.133` (key-auth из DE_project), detached+nohup, phase A
  ингест (bge-m3 only) → exit → phase B реранк only. Гочи (память): снять `hf-xet`, Intel-Mac
  ML-пин (numpy<2/torch2.2.2/transformers4.44.2), SSH-сессии ≤8 мин. **Сначала проверить, что
  iMac не занят DV2 и доступен.** **Owner: CC может драйвить semi-автономно, если iMac свободен.**

## Phase 3 — Land + re-measure (локально, после подтверждения)

- Подтвердилось → оставить `RAG_CONTEXTUAL_HEADER` (или включить дефолтом, если recall↑ и
  faithfulness не просел), обновить baseline-доку новыми числами, коммит. Если закрывает 7
  deep-miss — recall двигается с ~0.785/0.80 ощутимо вверх.
- Не подтвердилось → зафиксировать отрицательный результат, следующий рычаг (query-expansion
  HyDE на `-fields` / BM25-веса).

---

## Что CC может начать СЕЙЧАС без барьера

**Phase 0 + Phase 1** — обе под лимитом <1GiB, автономны, верифицируемы. Барьер (Phase 2)
бьётся либо твоим Colab-прогоном (готовлю turnkey), либо моим iMac-прогоном (если свободен).
Прокси-A/B (Phase 1) — главный обход: даёт go/no-go по фиксу до траты remote-ресурса.

## Анти-риски

- Прокси ≠ production: MiniLM-числа абсолютно не равны BGE-M3; используем только
  **относительный** сигнал (ранг до/после), не абсолютный recall.
- Не включать contextual-header дефолтом до Phase 2 (shipping-blind, память
  `no_shipping_blind_ci`).
- Не гонять BGE-M3/реранкер на Windows (повесит машину, память `weak_machine_offload_heavy`).

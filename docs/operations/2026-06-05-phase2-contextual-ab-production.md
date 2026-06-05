# Phase 2 A/B (production stack) — structural chunking ПОДТВЕРЖДЁН, дефолт включён

- Дата: 2026-06-05
- План: `docs/plans/2026-06-03-overcome-retrieval-barrier.md` (Phase 2 — подтверждение
  Phase-1-направления на production-стеке BGE-M3 + reranker; Phase 3 — лендинг дефолта).
- Вопрос: переносится ли прокси-результат Phase 1 (MiniLM, reranker OFF) на production-стек,
  и не роняет ли фикс faithfulness при LLM-judged генерации.
- Где считалось: Kaggle kernel `liovinajo/rag-phase2-contextual-ab` v5 (private, **CPU**
  4 vCPU — GPU-квота выдала P100/sm_60, у которого в torch-образе Kaggle нет кернелей;
  см. гочи в `AGENT_STATE.md` cont.12), wall-clock 6.4 h. Код уехал private-датасетом
  `liovinajo/rag-phase2-ab-bundle` v3 (git archive HEAD c локальными коммитами
  `4844094`/`c4ffd50`/`09195c1`) — push-гейт не обходился через GitHub.
- Драйвер: `scripts/ab_remote_contextual.py` — 3 стадии (`pools` → `rerank` → `report`),
  каждая отдельным процессом; обвязка `run_phase2.py` в `.tmp/kaggle_phase2/kernel/`
  (gitignored, layout-agnostic к смене Kaggle-маунта `/kaggle/input/datasets/<owner>/<slug>/`).

## Setup

- Корпус: `data/uploads/aircargo/` — 201 RU-док (zip в датасете, Kaggle развернул).
- Кейсы: `evaluation/curated_cases_aircargo.jsonl` — 100; метрики те же, что в Phase 1:
  keyword-coverage @ post-rerank top-5 (FULL/PART/MISS) + co-occur rank по pre-rerank пулу.
- Ретривал: production-стек — BGE-M3 dense + BM25 → RRF (top-40 pool) → reranker
  `bge-reranker-v2-m3` → top-5. В отличие от Phase 1 прокси здесь оба недостающих звена:
  production-эмбеддер и реранкер.
- Генерация/судья: `scripts/aircargo_ragas_free.py --provider mistral` (`mistral-small-latest`,
  300 LLM-вызовов на плечо, локально с Windows-хоста; кандидаты — с Kaggle).

## Плечи

| Плечо | Чанкинг | Header | Чанков |
|---|---|---|---|
| **A** (production-зеркало) | fixed 800/200 | contextual ON (production default) | 5077 |
| **C** (фикс) | `RAG_STRUCTURAL_CHUNKING=true` | contextual ON | 5589 |

Обрезка тела чанка в обоих плечах отсутствует — production-путь после `4844094` ≡ плечо C
Phase 1; отдельное плечо B больше не нужно.

## Результат 1 — retrieval (post-rerank top-5 coverage)

| Плечо | FULL | PART | MISS |
|---|---|---|---|
| A | 82/100 | 7 | 11 |
| **C** | **87/100** | 7 | **6** |

- Полная матрица переходов по 100 кейсам (пересчитана по сырым candidates той же
  `_kw_status`-логикой): **8 gains / 4 regressions, нетто +5 FULL**.
  - Gains: 7×MISS→FULL (dangerous-goods-fields, driver-hours, warehouse-3pl, gps-monitoring,
    weight-control, cross-border-pdn-required-fields, sick-leave-required-fields)
    + 1×PART→FULL (cargo-loss-required-fields).
  - **Regressions (вне 13 диагноз-целей, в summary-таблице kernel'а их не видно):**
    customs-broker-escalation FULL→MISS, dangerous-goods-clearance PART→MISS,
    breach-notification-participants FULL→PART, perishable-special-cargo-evidence FULL→PART.
- 13 диагноз-целей (`*-required-fields` класс): **5 спасено MISS→FULL**
  (dangerous-goods, driver-hours, warehouse-3pl, gps-monitoring, weight-control;
  fuel-supply остаётся FULL c pool-rank 14→2), 3 остаются FULL, 4 остаются MISS
  в обоих плечах (deep): customs-clearance, waybill-first-mile, perishable-temperature,
  cross-border-required-fields. Внутри диагноз-списка регрессий нет.
- Верификация «10 rerank-recoverable» из rank-grade диагноза (cont.9): в плече A реранкер
  фактически поднял **6/10** в top-5 — совпало с прогнозом «4 лёгких + часть uncertain»
  и с A/B-оценкой 2026-06-02 (~6 of 26).

## Результат 2 — R7 LLM-judged (Mistral, 100 кейсов на плечо)

| Метрика | Старый baseline¹ | A (production) | **C (фикс)** | Δ C−A |
|---|---|---|---|---|
| context_recall | 0.785 | 0.855 | **0.905** | **+0.050** |
| faithfulness | 0.833 | 0.875 | **0.909** | **+0.034** |
| context_precision | 0.488 | 0.499 | 0.507 | +0.008 |
| answer_relevancy | 0.838 | 0.888 | 0.864 | −0.024² |

¹ `20260603T031646Z-e437ad07` — кэш Mac-прогона БЕЗ реранкера, fixed chunking; колонка
показывает, что один только реранкер двигает recall 0.785→0.855, а фикс добавляет ещё +0.050.
² В пределах шума LLM-судьи (та же генерация на тех же вопросах; не связано с retrieval —
recall/precision у C выше).

Run-id: A = `20260605T054729Z-de03550d`, C = `20260605T052606Z-85b99bdf`
(`reports/ragas/` gitignored, агрегаты продублированы здесь).
Эксплуатационная заметка: первый прогон судьи плеча A умер на 16/100 без traceback
(transient kill процесса на Windows-хосте), re-run прошёл 100/100 без ошибок.

## Решение (Phase 3 плана)

Критерий «recall↑ И faithfulness не просел» выполнен с запасом → **`RAG_STRUCTURAL_CHUNKING`
включён дефолтом** (`config/settings.py`), пин-тест `test_structural_chunking_enabled_by_default`
(`tests/test_ingestion_contextual.py`). Откат: `RAG_STRUCTURAL_CHUNKING=false` в env.

Существующие индексы фикс не мигрирует — новый чанкинг применяется при следующем ингесте
(re-ingest корпуса — штатная операция `IngestPipeline`).

## Остаток (не блокеры, кандидаты на следующий рычаг)

- 6 MISS @ top-5 в плече C: 4 deep diagnosis-цели (выше) + customs-broker-escalation
  (регрессия) + dangerous-goods-clearance (регрессия).
- 4 регрессии по характеру: **1 жёсткая** — customs-broker-escalation: kws выпали из всего
  top-40 пула C (в A co-occur rank 9) — structural-нарезка разнесла связку по разным чанкам;
  **3 мягких** — kws в пуле C есть (dangerous-goods-clearance rank 26,
  breach-notification-participants rank 16, perishable-special-cargo-evidence union-FULL),
  но реранкер не собрал их в top-5. Кандидаты на parent-child / реранк-тюнинг.
- customs-clearance-fields: правильный док в пуле (rank 27), но нужной секцией не попадает —
  кандидат на parent-child retrieval (`RAG_PARENT_CHILD` уже wired) или query-expansion.
- waybill-first-mile / perishable-temperature / cross-border: целевой чанк вне top-40 пула
  в обоих плечах — это query-side проблема (NL RU ↔ snake_case field-IDs), рычаг —
  query-expansion / BM25-вес, как и записано в плане.

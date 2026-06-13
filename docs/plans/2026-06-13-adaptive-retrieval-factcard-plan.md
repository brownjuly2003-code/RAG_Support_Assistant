# Adaptive Retrieval Router + Fact-Card (SFR) — план

> Статус: **PLANNED, не начато.** Отдельный workstream, не связан с mypy-strict-hardening.
> Research-обоснование: `research_adaptive.md` (Adaptive RAG / CRAG / RAGRouter-Bench, 2024–06.2026).
> Принцип: **eval-gated** — ничего тяжёлого не строим, пока данные не докажут выгоду (дисциплина arms E/F: NO-SHIP по данным).

---

## Как начать новую сессию (READ FIRST)

1. **Запуск:** свежая сессия → `/auto` с задачей вида
   `RAG_Support_Assistant — adaptive-retrieval: Phase 0 из docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md`.
   (Голое `/auto … продолжи` подхватит mypy-strict-линию, а не этот план — указывай план явно.)
2. **Step-0 онбординг как обычно:** `Glob *.md` по корню + прочитать `AGENT_STATE.md`, `next-session-fable-hardening.md`, этот файл. Текущее состояние кода: origin/master = `2c01c5a`, дерево чисто (кроме 2 чужих untracked — не трогать).
3. **Первый и единственный безопасный автономный шаг — Phase 0** (разметка + baseline + train-набор роутера). Нового индекса не создаёт, обратимо, только чтение eval-данных. Можно делать на Windows (офлайн, без тяжёлых процессов).
4. **ГЕЙТ после Phase 0:** дальше (Phase 1+/2+) идём ТОЛЬКО если данные прошли пороги (см. ниже). Если нет — STOP, фиксируем NO-SHIP, остаёмся на D2. Не изобретать обходы.
5. **Гочи, которые НЕ ломать (из mypy-сессий и проб E/F):**
   - Тяжёлые процессы (Docker, полный re-embed, ragas на корпусе) — **только на Mac, не на Windows** (машина виснет).
   - Любой strict-модуль с top-level `import yaml`/known-stub либой → сразу `# type: ignore[import-untyped]` (локальный mypy не ловит, CI падает).
   - Полный suite — без `RAG_RERANKER_MODEL=""` (conftest сам глушит reranker).
   - В `/auto` push свой при зелёном+CI-safe; гейт только для deploy/наружу.

---

## Goal

Per-query выбор лучшего ретривера (router-first multi-lane), доказанный данными, без регрессий качества/latency от мисроутинга. Опционально — новый lane Fact-Card (SFR) под класс «перечень полей/документов/условий».

## Текущий шов (что УЖЕ есть — переиспользуем, не пишем заново)

| Компонент | Где | Что делает |
|---|---|---|
| LLM query-классификатор | `agent/graph.py:make_classify_complexity_node`, `build_classify_complexity_prompt` | `state["complexity"]` = simple/global/… |
| Выбор стратегии | `agent/graph.py:_select_retrieval_strategy` (+`_normalize_retrieval_strategy`, `_RETRIEVAL_STRATEGIES`) | `Literal["vector","hybrid","graph"]` из settings + complexity |
| Диспетчер ретрива | `agent/graph.py:make_retrieve_node` | `get_vector_documents`/`get_graph_documents`/`get_relevant_documents`, fallback graph→hybrid |
| Ретривер | `vectordb/manager.py`, `vectordb/_base_manager.py` | методы `get_*_documents` |
| Конфиг | `config/settings.py:retrieval_strategy` | дефолт стратегии |
| Состояние | `agent/state.py:GraphState` | `complexity`, `retrieval_strategy` |
| Эвал | `evaluation/curated_cases*.jsonl`, `scripts/regression_eval.py` | офлайн-гейт |
| Стек по умолчанию | D2: structural chunking + parent-expansion (w=2/3600) + reranker | production baseline |

Вывод: «несколько вариантов + выбор» — это **уже каркас**. Новый вариант = +значение `Literal` + метод ретривера + ветка в `_select_retrieval_strategy`.

## Новый вариант: Fact-Card Retrieval (SFR) — «n-арность облегчённая»

На индексации LLM достаёт плоские **fact-cards**:
```json
{"topic":"customs_clearance","fields":["..."],"required_docs":["..."],
 "conditions":["..."],"source":"customs.md#sec3"}
```
Хранятся отдельной маленькой Chroma-коллекцией (`<prefix>_factcards`, карта эмбеддится по каноничному тексту + богатые metadata). На запросах «какие поля/документы/условия нужны для X» отдаём **целую карту** → LLM получает полный перечень (бьёт в остаточный MISS `customs-clearance-fields`; механизм потери полей при реранке завалил arms E/F). Дешевле hypergraph на порядок: нет графа/обхода гиперрёбер, только структурные записи + metadata-фильтр + векторный матч.

## Research-уточнения (из `research_adaptive.md`)

- **Router-first hybrid = best practice 2026** → наша архитектура уже такая, не догоняем.
- **Ни одна парадигма не доминирует** (RAGRouter-Bench): главный гейн — в качестве роутинга, не в экзотическом ретривере → Fact-Card строго за гейтом.
- **Lightweight-классификатор (TF-IDF+SVM/MiniLM) бьёт LLM-роутер по цене** (≈0.93 F1, ~28% экономии токенов по доку) → заменить дорогой per-query LLM-вызов.
- **Multi-lane (cheap/standard/heavy)** — формализовать поверх существующего шва.
- **Метрики router-слоя**: cost-aware (токены/latency saving при ≥ том же качестве) + **AUROC калибровки confidence** (триггер эскалации).
- ⚠ Часть бенчмарков в доке датированы после моего cutoff — конкретные числа проверять по первоисточникам, если идут в обоснование.

---

## План (eval-gated)

### Phase 0 — Измерение + train-набор роутера (ГЕЙТ; безопасно, без нового индекса)
> **DONE 2026-06-13.** Отчёт: `docs/operations/2026-06-13-adaptive-retrieval-phase0.md`.
> Артефакты: `evaluation/adaptive_retrieval/build_phase0_labels.py` (разметка) +
> `evaluation/adaptive_retrieval/phase0_labels.jsonl` (135 кейсов / train-набор).
- [x] T0.1: Разметить `evaluation/curated_cases_aircargo.jsonl` (+`curated_cases.jsonl`): метка `query_class` (simple/factual/enumeration/multi-condition) и флаг `needs_factcard` → **Verify:** доли посчитаны. **РЕЗ:** 135 кейсов размечены. aircargo: needs_factcard **44%** (enum 44 / multi-cond 41 / factual 9 / simple 6). curated: needs_factcard 6% (в осн. simple/factual). ALL: needs_factcard 34%.
- [x] T0.2: Baseline D2 на размеченном срезе через `scripts/regression_eval.py` (mock-runtime, без paid-API) → **Verify:** известно сколько `needs_factcard`-кейсов сейчас FULL/PART/MISS. **РЕЗ:** mock-harness валиден (135/135 кейсов, офлайн), но mock строит ответ из `answer_contains` → pass-rate ≠ retrieval. Реальный D2 (Kaggle, задокументирован): **FULL 96 / PART 3 / MISS 1**. Среди needs_factcard: **1 MISS** = `customs-clearance-fields` (enumeration), ≤3 PART (D2-PART id'ы локально не восстановимы), ≥40 FULL.
- [x] **ГЕЙТ → PASS обоими треками (eligible).** Fact-Card: needs_factcard 44% ≫ 10% И есть MISS (`customs-clearance-fields`) на needs_factcard-кейсе. Router: выраженный mixed-complexity (44/41/9/6). **Дисциплина:** headroom мал (D2 уже FULL 96/100) — любая постройка обязана пройти Phase-5 NO-SHIP; router-трек = про cost, не recall. Исполнение Track R (R1, можно Windows) / Track F (F1, только Mac) — отдельной сессией по явному запросу, НЕ в scope Phase 0.

### Track R (router cost) — Lightweight-классификатор [если есть mixed-complexity]
- [ ] R1: Обучить TF-IDF+SVM (или MiniLM) на Phase-0-разметке; сравнить с LLM `classify_complexity` по macro-F1 **и** по токенам/latency → **Verify:** F1 не хуже + экономия per-query вызова.
- [ ] R2: Врезать классификатор перед `_select_retrieval_strategy` (LLM-классификатор → fallback на низкой confidence) → **Verify:** `tests/test_model_routing.py` + новый тест зелёные; токен-метрика на запрос упала.

### Track F (Fact-Card lane) — [если Phase 0 ГЕЙТ пройден]
- [ ] F1: LLM-экстрактор fact-cards в `ingestion/`, schema через pydantic (образец — `evaluation/experiment_schema.py`) → **Verify:** на 3 customs-доках валидные карты, поля не теряются. (Тяжёлый ingest — на Mac.)
- [ ] F2: Коллекция `<prefix>_factcards` + запись карт при ingest → **Verify:** карты ищутся векторно.
- [ ] F3: `get_factcard_documents(query)` на ретривере (`vectordb/manager.py`/`_base_manager.py`) → **Verify:** возвращает карту как Document.
- [ ] F4: Расширить `_RETRIEVAL_STRATEGIES`+`Literal`+`config/settings.py` на `"factcard"`, ветка в `make_retrieve_node` (fallback→hybrid) → **Verify:** mypy strict-scope зелёный (+ `# type: ignore[import-untyped]` если новый yaml-импорт), retrieve диспетчеризует.

### Phase 3 — Lanes + per-query маршрутизация
- [ ] T3.1: Формализовать lanes поверх шва: `cheap` (cache/simple→vector) · `standard` (D2 hybrid, default) · `heavy` (factcard/graph по сигналу) в `_select_retrieval_strategy` → **Verify:** роутер шлёт `needs_factcard`-класс в factcard, остальное — как было.

### Phase 4 — Эскалация (cascade) + калибровка confidence
- [ ] T4.1: После `grade_docs`/quality-оценки — при low confidence на field-вопросе перезапрос через factcard (использовать существующий Self-RAG-сигнал) → **Verify:** на baseline-MISS-кейсе эскалация поднимает recall.
- [ ] T4.2: Посчитать **AUROC** confidence-сигнала vs фактическое качество на eval → **Verify:** сигнал калиброван (иначе каскад мисроутит — чинить порог).

### Phase 5 — Верификация (LAST)
- [ ] T5.1: Офлайн-дельта D2 vs D2+router(+factcard) на полном `curated_cases` → **Verify:** recall на `needs_factcard` ↑, на остальных НЕ упал (нет мисроутинг-регрессий), p95 latency в норме, токены/запрос ≤ baseline → иначе **NO-SHIP**.

## Done When
- [ ] Роутер выбирает спец-lane только на нужном классе; `customs-clearance-fields` закрыт **или** явно зафиксирован как незакрываемый;
- [ ] router/factcard, доказанно полезные (recall↑ без регрессий, cost не вырос), влиты; либо обоснованный NO-SHIP по данным.

## Out of scope / опционально
- **Hypergraph RAG** — только если Phase 0 покажет МНОГО истинно multi-hop n-арных запросов (в support-домене не жду). SFR покрывает ~80% выгоды за ~20% стоимости.
- **C-RAG (Contrastive-RAG)** — альтернатива для heavy-lane про устойчивость к noisy-context; ортогонально, не на твою enumeration-дыру.
- **RAISE/AutoRAG offline-HPO** — overkill для текущего масштаба.

## Риски
- Двойная индексация (vector+factcard): ingest-cost + рассинхрон при обновлении KB → оправдано только при доказанной доле кейсов.
- Мисроутинг = тихая деградация → калибровка confidence + офлайн-дельта обязательны.
- NO-SHIP — нормальный исход (как arms E/F); не «дожимать» вопреки данным.

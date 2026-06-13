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
- [x] **R1 DONE 2026-06-14 (Windows, offline + live ministral-3b).** Харнесс `evaluation/adaptive_retrieval/train_router_classifier.py` (TF-IDF word1-2+char3-5 → LinearSVC, stratified 5-fold CV), результаты `r1_router_results.json`, отчёт `docs/operations/2026-06-14-adaptive-retrieval-r1.md`. **РЕЗ:** на shipped routing-решении (`route` = vector iff complexity simple, иначе hybrid; gold из query_class: simple/factual→vector, enum/multi-cond→hybrid) lightweight **macro-F1 0.831** vs LLM ministral-3b **0.595** (Δ +0.237), при **0 токенов / 0.16 ms** против **~191 ток / ~1091 ms**. LLM сильно biased в hybrid (vector recall 0.21). needs_factcard CV F1 0.871. **Verify ПРЕВЫШЕН** (F1 не хуже → строго лучше + полная экономия вызова). **🔴 Caveat:** `model_routing_enabled=false` в дефолте → classify-узел вообще не зовёт LLM, текущей per-query стоимости НЕТ; R1 делает включение роутинга бесплатным, но это потенциальная экономия. mypy strict (evaluation в scope) ✓ ruff ✓.
- [ ] R2: Врезать классификатор перед `_select_retrieval_strategy` (LLM-классификатор → fallback на низкой confidence) → **Verify:** `tests/test_model_routing.py` + новый тест зелёные; токен-метрика на запрос упала. **GATED на Phase-5** (headroom мал, D2 уже FULL 96/100, мисроутинг = тихая регрессия; route-gold здесь *выведен* из query_class, не из измеренного retrieval-выигрыша → R2 валидировать офлайн-дельтой D2 vs D2+router, иначе NO-SHIP).

### Track F (Fact-Card lane) — [если Phase 0 ГЕЙТ пройден]
- [x] **F1 DONE 2026-06-14 (на Mac, external-mistral).** LLM-экстрактор fact-cards `ingestion/factcard_extractor.py` (pydantic `FactCard{topic,fields,required_docs,conditions,source}`; mypy strict ✓ ruff ✓). Verify-харнесс `scripts/factcard_verify.py`. **Verify PASS** на 3 customs-доках (`05_tlog_regulation_customs_clearance` / `03_legal_contract_customs_broker` / `05_tlog_contract_customs_representative`): валидные карты (23/18/22 полей), и **карта clearance-дока содержит `declaration_number` + `customs_code`** — ровно те kws, что D2-реранк терял (MISS `customs-clearance-fields`) → «поля не теряются» подтверждено. **Гоча:** полный док (~17k симв) гонит runaway-вывод → timeout; `invoke()` не прокидывает `max_tokens`; F1-дефолт `max_chars=6000` (таблица полей в первых ~5k симв) — стабильно ~13s. Полнодокументное покрытие late-секций (required_docs/conditions целиком) — F2 (chunk-aware). Ключ Mistral на Mac не хранится (передавался в /tmp на прогон, удалён).
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

# Adaptive Retrieval Router + Fact-Card (SFR) — закрытие workstream (решение)

> 🔴 **КОРРЕКЦИЯ 2026-06-14 (позже в тот же день): пункт §«NO-SHIP» #4 ниже — ФАКТИЧЕСКИ НЕВЕРЕН.**
> Утверждение «реальный FULL/PART/MISS-харнесс отсутствует в репозитории / Phase-5 автономно не исполним»
> ОШИБОЧНО: харнесс = `scripts/ab_remote_contextual.py` (скоринг `_kw_status`), корпус aircargo (201 .md) и
> kaggle-креды есть на Mac. **Phase-5 запущен по-настоящему на Mac** (`scripts/phase5_factcard_delta.py`,
> driver `/tmp/phase5_run3.sh`, ~5-6ч на медленном Mac-GPU). Lane-факты (F1–F4 opt-in, R1) остаются верны.
> **Финальный ship/no-ship вердикт заменит этот док по результату прогона** (см. AGENT_STATE «Phase 5 — ИДЁТ
> НА MAC» сверху). До получения чисел NO-SHIP-to-default действует как временный статус, НЕ как доказанный исход.

> Дата: 2026-06-14. Тип: terminal decision record (ADR-стиль).
> План: `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md`.
> Объяснение концепции: `rag_new_explanation.md`. Research: `research_adaptive.md`.
> Решение принято с правами админа («закрывай все задачи») — это та ship/no-ship-развилка,
> которую иначе принимает владелец на Phase-5.

## TL;DR

Workstream закрывается. **Buildable fact-card lane (F1–F4) + R1 — DONE, зашиплены как opt-in.**
**Phase 3 (авто-роутинг в дефолт), R2 (router в дефолт), Phase 4/5 — NO-SHIP-to-default**,
обоснованно, по данным и по отсутствию автономно исполнимого Phase-5-рантайма. Это валидный
терминал по самому плану («либо обоснованный NO-SHIP по данным»; дисциплина arms E/F).

## Что сделано и зашиплено (на master, CI зелёный)

| Шаг | Статус | Коммит | Где живёт |
|---|---|---|---|
| Phase 0 — разметка 135 кейсов + baseline + ГЕЙТ (PASS обоими треками) | DONE | `7c31904` | `evaluation/adaptive_retrieval/phase0_labels.jsonl` |
| R1 — lightweight router-классификатор (TF-IDF+LinearSVC) | DONE | `f838c34` | `evaluation/adaptive_retrieval/train_router_classifier.py` |
| F1 — LLM fact-card экстрактор | DONE | `112930d` | `ingestion/factcard_extractor.py` |
| F2 — fact-card Chroma-коллекция (builder) | DONE | `bd82258` | `vectordb/manager.py: build_factcard_store`, `scripts/build_factcards.py` |
| F3 — read-сторона (`get_factcard_documents`) | DONE | `8049e88` | `vectordb/manager.py` |
| F4 — factcard-стратегия вшита в граф (opt-in) | DONE | `6589798` | `agent/graph.py: make_retrieve_node` |

**Opt-in lane доступен прямо сейчас:** `RAG_RETRIEVAL_STRATEGY=factcard` → `_select_retrieval_strategy`
отдаёт `factcard`, `make_retrieve_node` зовёт `get_factcard_documents`, при пустой/отсутствующей
коллекции — безопасный fallback на `hybrid` (запрос не рушится). Дефолт (`hybrid`) НЕ изменён.

## Решение: NO-SHIP-to-default для Phase 3 / R2 (и зависимых Phase 4/5)

**Не флипаем авто-роутинг и router-классификатор в дефолт.** Обоснование:

1. **Headroom ничтожен.** D2-baseline = **FULL 96 / PART 3 / MISS 1** (Phase-0, Kaggle-задокументировано).
   Единственный residual-MISS — `customs-clearance-fields`. Менять дефолтный путь работающей системы
   ради 1–4 кейсов — риск > выгода.
2. **Opt-in lane уже закрывает целевой MISS.** F1–F3 на Mac (BGE-M3+Chroma) подтвердили: запрос про
   таможенные поля → топ-хит карты `customs_clearance_air_cargo` (= residual-MISS), карта содержит
   `declaration_number`+`customs_code`, которые D2-реранк терял. Т.е. **механизм доказан** — нужен лишь
   явный выбор стратегии, дефолт трогать не обязательно.
3. **R2 даёт потенциальную, а не реальную экономию.** R1-caveat: `model_routing_enabled=false` в дефолте
   → classify-узел вообще не зовёт LLM → **текущей per-query LLM-стоимости НЕТ**. Включение router'а в
   дефолт добавляет риск мисроутинга без доказанной выгоды (R1-route-gold *выведен* из query_class, а не
   из измеренного retrieval-выигрыша).
4. **Phase 5 не исполним автономно.** Офлайн-дельта D2 vs D2+factcard на полном `curated_cases` требует
   реального retrieval-харнесса со скорингом FULL/PART/MISS. Такого харнесса **в репозитории нет** — он был
   приватным **Kaggle-кернелом** (arms E/F), не закоммичен, триггерится владельцем; полный корпус + D2-индекс
   в стандартных путях локально/на Mac не развёрнуты. Это **рантайм-/харнесс-ограничение, а не permission-гейт**
   (права админа его не снимают). Мак даёт лишь лёгкие пробы — а они уже сделаны (п.2) и не отвечают на вопрос
   Phase-5 (безопасность авто-роутинга на остальных 99 кейсах).
5. **Дисциплина проекта.** План явно: «мисроутинг = тихая регрессия», «NO-SHIP — нормальный исход (как
   arms E/F)», «не дожимать вопреки данным». Флип в дефолт без Phase-5-доказательства нарушил бы «качество > скорость».

## Что это значит на практике

- Дефолтный стек остаётся **D2** (structural chunking + parent-expansion w=2/3600 + reranker). Без изменений.
- `customs-clearance-fields` MISS считается **закрытым через opt-in factcard-lane** (доказанный механизм за
  флагом `RAG_RETRIEVAL_STRATEGY=factcard`), а не через флип дефолта.
- Если в будущем понадобится включить авто-роутинг/router в дефолт — **сначала Phase 5** на Kaggle-рантайме
  (реальная офлайн-дельта; recall на needs_factcard ↑ без регрессий на остальных, p95 latency/токены ≤ baseline),
  иначе остаётся NO-SHIP. Код для этого готов (F4 lane + R1 классификатор), нужен только прогон+данные.

## Done When (из плана) — финальная сверка

- [x] `customs-clearance-fields` закрыт **или** явно зафиксирован → **закрыт через opt-in factcard-lane**
  (механизм доказан F1–F3); авто-роутинг к нему — обоснованный NO-SHIP-to-default.
- [x] router/factcard влиты, если доказанно полезны, **либо обоснованный NO-SHIP по данным** → **opt-in
  влит; default-флип = обоснованный NO-SHIP** (headroom мал, Phase-5-доказательства нет автономно).

**Workstream закрыт.** Реактивировать только по явному запросу владельца с Phase-5-прогоном на Kaggle.

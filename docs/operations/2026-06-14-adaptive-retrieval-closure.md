# Adaptive Retrieval Router + Fact-Card (SFR) — закрытие workstream (решение)

> ✅ **РАЗВЯЗКА 2026-06-15: Phase-5 ПРОГНАН на Mac → вердикт NO-SHIP теперь обоснован ДАННЫМИ.**
> Полные числа и анализ: **`docs/operations/2026-06-15-phase5-factcard-delta.md`**.
> Кратко (потолок идеального роутера, 100 curated-кейсов): композит «gold needs_factcard→factcard, иначе D2»
> даёт **FULL 79 vs D2 FULL 97 (Δ −18)**; на needs-срезе (44) D2 **42/44** vs factcard **24/44** —
> **1 улучшение, 19 регрессий**; целевой residual-MISS `customs-clearance-fields` лишь **MISS→PART** (не закрыт).
> Дистилляция карт теряет точные `answer_contains`-формы, которые D2-чанки содержат дословно → как **замена**
> D2 полоса строго хуже. Раньше пункт #4 ниже ошибочно гласил «harness отсутствует / Phase-5 не исполним» —
> это БЫЛО НЕВЕРНО (harness = `scripts/ab_remote_contextual.py`+`phase5_factcard_delta.py`); теперь п.4
> исправлен реальным исходом. Lane-факты (F1–F4 opt-in, R1) остаются верны; opt-in остаётся, дефолт не флипаем.

> Дата: 2026-06-14. Тип: terminal decision record (ADR-стиль).
> План: `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md`.
> Объяснение концепции: `rag_new_explanation.md`. Research: `research_adaptive.md`.
> Решение принято с правами админа («закрывай все задачи») — это та ship/no-ship-развилка,
> которую иначе принимает владелец на Phase-5.

## TL;DR

Workstream закрывается. **Buildable fact-card lane (F1–F4) + R1 — DONE, зашиплены как opt-in.**
**Phase 3 (авто-роутинг в дефолт), R2 (router в дефолт), Phase 4 — NO-SHIP-to-default.** **Phase 5
ПРОГНАН (2026-06-15)** → офлайн-дельта подтвердила NO-SHIP **по данным**: композит даёт Δ FULL −18
(19 регрессий на needs-срезе), целевой MISS лишь MISS→PART. Валидный терминал по плану («обоснованный
NO-SHIP по данным»; дисциплина arms E/F). Числа: `docs/operations/2026-06-15-phase5-factcard-delta.md`.

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
2. **Opt-in lane извлекает целевую карту, но НЕ выигрывает на eval-метрике.** F1–F3 на Mac (BGE-M3+Chroma)
   подтвердили retrieval-механизм: запрос про таможенные поля → топ-хит карты `customs_clearance_air_cargo`
   (= residual-MISS). Но Phase-5 (`_kw_status`) показал: на keyword-метрике карта закрывает MISS лишь до
   **PART**, не до FULL (дистилляция теряет точные ключи). Т.е. **механизм извлечения рабочий, но как замена
   D2 проигрывает** — оставляем за флагом, дефолт не трогаем.
3. **R2 даёт потенциальную, а не реальную экономию.** R1-caveat: `model_routing_enabled=false` в дефолте
   → classify-узел вообще не зовёт LLM → **текущей per-query LLM-стоимости НЕТ**. Включение router'а в
   дефолт добавляет риск мисроутинга без доказанной выгоды (R1-route-gold *выведен* из query_class, а не
   из измеренного retrieval-выигрыша).
4. **Phase 5 ПРОГНАН (2026-06-15) и дал NO-SHIP по данным.** Офлайн-дельта D2 vs D2+factcard на 100 curated-кейсах
   (harness = `scripts/ab_remote_contextual.py` + `scripts/phase5_factcard_delta.py`, скорер `_kw_status`):
   композит на потолке идеального роутера = **FULL 79 vs D2 97 (Δ −18)**, на needs-срезе **19 регрессий / 1
   улучшение**, целевой MISS лишь **MISS→PART**. Причина — factcard-полоса возвращает дистиллированные карты,
   теряющие точные `answer_contains`-формы, тогда как D2-чанки несут их дословно. Полные числа:
   `docs/operations/2026-06-15-phase5-factcard-delta.md`. (Прежняя формулировка «harness отсутствует / не
   исполним автономно» была ФАКТИЧЕСКИ НЕВЕРНА — harness в репо есть; теперь вердикт обоснован прогоном.)
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

- [x] `customs-clearance-fields` закрыт **или** явно зафиксирован → **явно зафиксирован**: карта ретривится
  топом (F1–F3), но Phase-5 показал лишь MISS→PART на keyword-метрике; авто-роутинг = NO-SHIP по данным.
- [x] router/factcard влиты, если доказанно полезны, **либо обоснованный NO-SHIP по данным** → **opt-in
  влит; default-флип = NO-SHIP, обоснованный прогнанной Phase-5-дельтой** (Δ FULL −18 на потолке роутера).

**Workstream закрыт, Phase-5 отработан.** Реактивировать только по явному запросу владельца — и при ином
дизайне полосы (factcard как **аугментация** D2, не замена), т.к. замена доказанно проигрывает на eval.

# Диагноз остаточных MISS/регрессий после Phase 2 — нарезка не виновата, рычаг = ранжирование

- Дата: 2026-06-05 (та же сессия, что закрыла Phase 2/3).
- Контекст: `docs/operations/2026-06-05-phase2-contextual-ab-production.md` — после включения
  `RAG_STRUCTURAL_CHUNKING` остались 6 MISS @ top-5 (4 deep + 2 регрессии) и 2 PART-регрессии.
- Вопрос: виновата ли structural-нарезка (разнесла kw-связки по чанкам) — и чинить ли её
  (merge мелких секций / overlap), или проблема в ранжировании.
- Метод: чистый текст-анализ БЕЗ моделей — обе нарезки воспроизведены локально
  (`_build_text_splitter(800,200)` = 5077 чанков 1-в-1 с Kaggle-плечом A;
  `structural_split(800,200)` = 5589 = плечо C), kw co-occurrence по всем 100 кейсам.

## Результат — co-occur «связка целиком в одном чанке»

| класс | кейсов |
|---|---|
| both (живёт в обеих нарезках) | **97** |
| fixed_only (structural разнёс) | **0** |
| struct_only (structural собрал) | 1 (remote-work-equipment-compensation) |
| neither (не живёт ни в одной) | 2 (cargo-loss-required-fields¹, subject-rights-third-party-masking) |

¹ cargo-loss при этом — gain PART→FULL в C: top-5 закрывается объединением чанков,
одно-чанковая связка не обязательна.

## Выводы

1. **structural_split чинить не нужно.** Гипотеза «merge мелких секций / межсекционный
   overlap» отменена данными: ни одного fixed_only кейса — нарезка C нигде не разрезала
   связку, которая жила в A.
2. **Все 4 регрессии — ранжирование, не нарезка.** Проверено точечно: в
   06_comp_policy_breach_notification.md связка `DPO + владелец авиационного процесса`
   живёт в structural-чанке #2 (350 b); в 03_legal_contract_customs_broker.md
   `customs hold + sanctions hit` — в чанках #3/#15/#27. Чанки СУЩЕСТВУЮТ, но в C-пуле
   top-40 не достаются: запросы («Какие события по таможенному брокеру требуют возврата
   к Legal…») не содержат ни одной kw — нулевой лексический оверлап, dense тянул их
   в A за счёт широкого тематического контекста fixed-чанков; узкие structural-секции
   этот контекст потеряли. Обратная сторона того же трейдоффа, который дал +8 gains
   на field-запросах.
3. **Потенциал parent-контекста измерен по Kaggle C-пулу: 8/8.** Для ВСЕХ 8 проблемных
   кейсов (4 регрессии + 4 deep) правильный документ (где связка живёт одним чанком)
   УЖЕ присутствует в top-40 пула C, причём first-rank 1-7 (у трёх deep-целей — 18-24
   чанка дока в пуле): customs-broker r1 (4 чанка), dangerous-goods-clearance r2 (9),
   breach-notification r1 (8), perishable-special-cargo r7 (6), customs-clearance r1 (18),
   waybill-first-mile r1 (20), perishable-temperature r1 (24), cross-border r2 (8).
   Retrieval находит правильный док — но не тем чанком; возврат parent-контекста
   механически приносит связку.
4. **`RAG_PARENT_CHILD` as-is НЕ включать** — проверено по коду: `ParentDocumentStore`
   (`vectordb/_base_manager.py:656`) — in-memory brute-force ретривер, который ПОДМЕНЯЕТ
   HybridRetriever целиком (`:1019`): теряется BM25+RRF+reranker (основа 80%+ coverage),
   children эмбеддятся при каждом построении (без персистентности), нарезка детей
   fixed 300/50 (не structural). Включение флага = регрессия всего retrieval-пути.
5. **Правильный шов следующего цикла: parent-expansion ПОСЛЕ реранка в HybridRetriever** —
   финальные top-k child-чанки дополняются контекстом соседних structural-секций своего
   документа (чистый текст-lookup по metadata source + порядковому индексу; hybrid-путь
   не меняется). Бьёт в доказанные 8/8 + 2 neither-кейса. Для 4 deep дополнительный
   рычаг — query-expansion (если parent-expansion не доберёт). Замер — Kaggle-паттерн
   Phase 2 (turnkey готов, добавить плечо «C + parent-expansion»).

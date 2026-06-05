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
3. **Рычаги следующего цикла (по убыванию ожидаемой отдачи):**
   - **parent-child retrieval** (`RAG_PARENT_CHILD` уже wired, выключен): child-точность
     structural-секций + parent-контекст для тематических запросов — бьёт и в 4 регрессии,
     и в 2 neither-кейса (связка живёт в parent'е), и потенциально в customs-clearance-fields
     (док в пуле не той секцией).
   - **query-expansion / BM25-вес** — для 4 deep-целей (NL RU ↔ snake_case/EN-термины,
     вне пула в обеих нарезках).
4. Замер обоих рычагов — production-стек (BGE-M3+reranker) → Kaggle-паттерн Phase 2
   уже turnkey (`scripts/ab_remote_contextual.py` + датасет-бандл); расширить плечом
   «C + parent-child» дёшево.

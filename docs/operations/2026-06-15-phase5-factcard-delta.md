# Phase 5 — offline delta D2 vs D2+factcard (executed, NO-SHIP)

> Дата прогона: 2026-06-15 (Mac `deproject-mac`, CPU embed). Тип: ship-gate evidence.
> Скрипт: `scripts/phase5_factcard_delta.py` (вердикт-логика) на артефактах
> `scripts/ab_remote_contextual.py` (pools→rerank→expand D2) + коллекция
> `rag_docs_aircargo_factcards` (`scripts/build_factcards.py --docs-dir data/uploads/aircargo`).
> Скорер — `_kw_status` (тот же, что меряет D2-baseline): покрытие `answer_contains`-ключей в top-k.

## Вердикт: **NO-SHIP** (даже на потолке идеального роутера)

Composite-рука маршрутизирует кейс в factcard-полосу **тогда и только тогда**, когда его
**gold** `needs_factcard`=true (иначе остаётся на D2). Это ПОТОЛОК авто-роутинга (идеальный
классификатор). Реальный R1-классификатор (needs_factcard CV F1 ≈ 0.871) — дополнительный
дисконт сверху, измерять его смысла нет: потолок уже отрицательный.

## Числа (100 curated-кейсов aircargo, 44 gold-needs_factcard, factcard top-k=3)

| Срез | D2 | D2+factcard (gold routing) |
|---|---|---|
| Все 100 | FULL **97** / PART 2 / MISS 1 | FULL **79** / PART 9 / MISS 12 |
| Δ FULL (all) | — | **−18** |
| needs_factcard (44) | FULL **42/44 (95%)** / PART 1 / MISS 1 | FULL **24/44 (55%)** / PART 8 / MISS 12 |
| Δ FULL (needs) | — | **−18** |
| improved / regressed (needs) | — | **1 / 19** |
| all-factcard (без роутера) | — | FULL **41** (Δ −56) |

- **Residual MISS `customs-clearance-fields`:** D2=MISS → factcard=**PART** (НЕ закрыт до FULL —
  карта релевантна и поднимается топом, но её дистиллированное содержимое не покрывает все
  ожидаемые `answer_contains`-ключи на keyword-метрике).
- D2-baseline воспроизведён этим прогоном (FULL 97/PART 2/MISS 1) — sanity к документированному
  Phase-0 FULL 96/PART 3/MISS 1 (расхождение ±1 — локальная PART-чистка id'ов, не регрессия).

## Почему factcard-полоса проигрывает D2 на этой метрике

Factcard-полоса возвращает **дистиллированные LLM-карты** (`topic` + `fields` + `required_docs`
+ `conditions`), а не исходный текст чанков. `_kw_status` проверяет наличие точных
`answer_contains`-форм в retrieved-контексте. Дистилляция перефразирует/сворачивает enumeration →
**теряет точные поверхностные формы ключей**, которые D2-чанки содержат дословно. Итог: на 19 из 44
needs-кейсов, которые D2 брал FULL, карта даёт PART/MISS; на целевом enumeration-MISS карта помогает
лишь до PART. Как **замена** D2 на needs-классе полоса строго хуже.

## Следствие для решения

- **NO-SHIP-to-default подтверждён ДАННЫМИ** (не «harness отсутствует» — та формулировка была неверна).
  Авто-роутинг needs_factcard→factcard как замена D2 = крупная регрессия (−18 FULL на потолке).
- Opt-in lane (`RAG_RETRIEVAL_STRATEGY=factcard`) остаётся как был: механизм извлечения карт рабочий
  (карта ретривится топом), но НЕ выигрывает на keyword-метрике → в дефолт не идёт.
- Возможное будущее (НЕ автономно, требует владельца + Kaggle/Mac): factcard как **аугментация**
  (D2 ∪ карта в одном контексте), а не замена — тогда регрессия по конструкции невозможна, но это
  иной дизайн полосы (F4 шипнул замену) и отдельный Phase-5-прогон. Headroom — 1 кейс (PART→?FULL),
  выгода под вопросом.

## Провенанс прогона

- Стадии 1–3 (pools C → rerank C → expand D2): MPS, ~3.3ч, артефакты `.tmp/ab_candidates_phase2_D2.json`.
- Стадия 4 (build_factcards, full corpus, paid Mistral extraction + **CPU** embed): 747 карт из 201 док,
  коллекция `rag_docs_aircargo_factcards`, verification PASS. CPU вместо MPS — обход MPS-OOM (6.8 ГБ cap;
  batch 32→8 оба падали; CPU = system RAM, та же скорость).
- Стадия 5 (delta): CPU query-embed, 100 кейсов.
- Mistral-ключ передавался через `/tmp/mk.env` и удалён после прогона.

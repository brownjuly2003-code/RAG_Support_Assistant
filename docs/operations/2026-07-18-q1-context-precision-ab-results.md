# Q1 — context_precision A/B: результаты прогона (NO-SHIP)

- Дата прогона: 2026-07-18, Mac `deproject-mac` (mps, batch 8), run
  `20260718T173221Z-8c2fd13e`, mode `live`, 100 кейсов aircargo.
- План и рецепт: `2026-07-18-q1-context-precision-ab-plan.md`. Прогон — полная
  one-command форма (`--build-pool --with-grade --with-judge`,
  профиль external-mistral).
- Сырые артефакты (untracked по конвенции `reports/ragas/*` в .gitignore):
  `reports/ragas/20260718T173221Z-8c2fd13e-q1-context-precision-ab.{md,json}` —
  локально на Windows и на Mac; rerank-пул `.tmp/ab_candidates_phase2_C.json`
  (7.7 MB) сохранён на Mac — детерминированную сетку можно пересчитать из него
  за минуты без моделей.

## Вердикт: NO-SHIP по всем 7 плечам — прод-дефолты остаются

SHIP-критерии (вшиты в скрипт): Δ context_precision ≥ +0.05 vs prod;
context_recall ≥ 0.90; keyword FULL ≥ 96; MISS ≤ 1. `ship_candidates = []`.

| arm | rerank_k | window/chars | grade | ctx_prec | Δ | recall | FULL/PART/MISS | итог |
|---|---:|---|:---:|---:|---:|---:|---|---|
| prod | 5 | 2/3600 | — | 0.5768 | — | 0.980 | 97/2/1 | baseline |
| k3-grade | 3 | 2/3600 | on | 0.6478 | +0.071 | 0.945 | 92/5/3 | FULL −5, MISS +2 |
| k3 | 3 | 2/3600 | — | 0.6179 | +0.041 | 0.960 | 94/4/2 | Δ<0.05, FULL −3 |
| grade | 5 | 2/3600 | on | 0.6101 | +0.033 | 0.965 | 95/3/2 | Δ<0.05, FULL −2 |
| k3-light-expand | 3 | 1/2400 | — | 0.5881 | +0.011 | 0.940 | 92/4/4 | Δ<0.05, FULL −5 |
| k8 | 8 | 2/3600 | — | 0.5460 | −0.031 | 0.985 | 98/1/1 | precision вниз |
| light-expand | 5 | 1/2400 | — | 0.5504 | −0.026 | 0.950 | 93/4/3 | оба вниз |
| no-expand | 5 | off | — | 0.5067 | −0.070 | 0.905 | 87/7/6 | оба вниз |

Judge (external-mistral, только baseline — победителя нет): prod
faithfulness 0.8406 / answer_relevancy 0.8900.

## Интерпретация

1. **Каждый выигрыш precision оплачен регрессией FULL/MISS.** Единственное
   плечо, пробившее порог Δ ≥ +0.05 (k3-grade, +0.071), роняет FULL 97→92 и
   MISS 1→3 — ровно тот trade-off, от которого страхуют вшитые критерии.
   Урезание top-k и/или CRAG-фильтр убирают не только шум, но и документы,
   которые несут `answer_contains`-ключи.
2. **Parent-window expansion помогает precision, а не вредит** (контр-интуитивно
   для «меньше текста → выше precision»): no-expand теряет −0.070 precision И
   роняет FULL до 87. Экспансия добавляет текст, содержащий искомые ключи —
   выключать её нельзя ни по одной оси.
3. **k8 — единственное плечо с ростом keyword-покрытия** (FULL 98/1/1 vs
   97/2/1) ценой −0.031 precision. Это не цель Q1 (precision), но если
   когда-либо понадобится дожать последний MISS — это задокументированный рычаг
   с известной ценой.
4. Baseline prod по script-метрике 0.5768 согласуется с официальным RAGAS
   baseline ≈0.51 (2026-06-05; другая реализация метрики) — «слабое звено
   precision» подтверждено, но доступные ручки (k, window, grade) его не чинят
   без потери recall/FULL.

## Каверза прогона: transport-ошибки Mistral в grade-плечах

25 из ~200 batch-вызовов grade_docs (≈12%) упали с
`transport error: read timed out / server disconnected / DNS`. По коду узла
(`agent/graph.py`, `make_grade_docs_node`) batch-фейл откатывается на per-doc
grading, и только фейл per-doc-вызова оставляет документ без фильтра
(`is_relevant = True`). Проверено по логу прогона: строк
`[grade_docs] LLM error` (per-doc фейл) — **0**, т.е. на всех 25 кейсах
fallback отработал и grade РЕАЛЬНО применён; деградации к «оставить всё» не
было ни на одном кейсе. Transport-ошибки стоили только времени (таймауты по
120 с), не качества данных — регрессии FULL/MISS grade-плеч получены на
полноценно отработавшем фильтре. Embed-стадия также шла ~2.2 ч вместо
«3–6 мин» из плана: корпус aircargo = 5589 чанков, а не «сотни» (оценка в
плане была занижена; сам прогон от этого только дольше, не хуже).

## Решение

- Прод-дефолты (`RAG_RERANK_TOP_K=5`, parent-window 2/3600, grade off) **не
  меняются** — Q1a закрыт обоснованным NO-SHIP (дисциплина «evidence culture»,
  как Phase-5 fact-card).
- Q1b (nightly RAGAS drift + CI quality floor) остаётся гейтованным: аудит
  привязывал его к «после того как precision осмысленно сдвинулся» — этого не
  произошло.
- Дальнейший рост precision требует других механизмов (не k/window/grade) —
  отдельное решение владельца, не этот scope.

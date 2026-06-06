# Плечо F (split-query): результаты — NO-SHIP, цикл query-expansion закрыт

- Дата: 2026-06-06. Продолжение `2026-06-06-arm-e-field-hyde-results.md`
  (раздел «Будущий рычаг»).
- Плечо F = **split-query**: пулы (dense+BM25) строятся по field-aware
  расширенному запросу (те же пулы, что E, из датасета v7), реранк —
  cross-encoder по ОРИГИНАЛЬНОМУ запросу (как в C/D2), затем parent-expansion
  w=2/3600 локально (`--stage expand --label F`) = полный стек.
- Kernel v7 (CPU, 6h05m чисто): rerank F → pools C (регенерация: D2-база была
  вычищена в cont.17, Kaggle CLI versioned output не отдаёт) → rerank C.
- Контракт judge сохранён: `query` = оригинал, `expanded_query` отдельным полем.

## Результаты

### Воспроизводимость baseline

Регенерированный D2 (pools C v7 → rerank → expand) = **FULL 96 / PART 3 /
MISS 1**, остаточный MISS тот же (`customs-clearance-fields`) — совпадает с
cont.15 1-в-1. Baseline валиден, kernel-путь детерминирован.

### kw-coverage @ top-5 (100 кейсов)

| плечо | FULL | PART | MISS |
|---|---|---|---|
| F-pre (без экспансии) | 92 | 5 | 3 |
| **F (полный стек)** | **95** | 3 | 2 |
| D2-pre | 87 | 7 | 6 |
| D2 (baseline) | **96** | 3 | 1 |

Матрица переходов D2 → F (все 100 кейсов): **1 gain / 2 регрессии, нетто −1 FULL**.

- Gain: `customs-special-cargo-manual-check` PART→FULL.
- Регрессии: `customs-broker-escalation` FULL→MISS,
  `waybill-escalation-events` FULL→PART.
- `customs-clearance-fields` (последний MISS D2): **MISS и в F** — gain плеча E
  НЕ сохранился. В E его закрывал именно expanded-реранк (пулы у E и F
  одинаковые), а реранк по оригиналу не поднимает kw-чанк из глубины пула —
  тот же фейл-механизм, что в D2 (cont.13: rank 27, реранкер не поднимает).

### Диагноз регрессий (по пулам v7)

| кейс | характер | детали |
|---|---|---|
| customs-broker-escalation | rerank-anchor shift | co-occur чанк В F-пуле (rank 20), но original-реранк выбирает другие top-5 якоря, чьи соседи (parent-expansion) kws не несут; в D2 якорь rank 2 тянет оба kw через соседние секции |
| waybill-escalation-events | pool-выпадение | co-occur чанка НЕТ в F-пуле вовсе (expanded query сместил состав) — детерминированное наследство пулов E; предсказано в E-отчёте («1/8 — pool») |

### Split-query до экспансии — реально лучше

F-pre 92 vs D2-pre 87 (+5 нетто): гипотеза E-отчёта подтвердилась — original-
реранк поднимает kw-чанки, которые expanded-реранк демотировал, и пулы от
расширения выигрывают. Но **parent-expansion поглощает этот выигрыш**: D2
добирает +9 FULL экспансией, F — только +3 (механизмы восстановления
перекрываются: оба добирают соседний контекст одного и того же source).

### R7-judge: НЕ гонялся (обоснованный skip)

Ship-критерий cont.18 конъюнктивный: FULL ≥ 96 **и** judge не хуже D2.
Первая нога упала (95 < 96) — решение определено без судьи. Дельта 3 кейса
лежит внутри полосы шума судьи (re-judge C: 0.9092/0.9132, zeros 6/5 при
неизменных данных — гоча cont.15), т.е. 300 free-tier вызовов различающего
сигнала не дали бы.

## Решение

**NO-SHIP: split-query параметр retriever'а НЕ внедряем.** Выигрыш
существует только в конфигурации без parent-expansion, а она default ON
production (cont.15). В полном стеке F = 95 < D2 = 96 при 2 регрессиях
(одна — жёсткая FULL→MISS). **Цикл query-expansion (probe → E → F) закрыт:
D2-стек (structural chunking + parent-expansion w=2/3600, оба default ON)
остаётся production.** Остаточный MISS один — `customs-clearance-fields`;
известный рычаг (expanded-реранк из E) приносит −7 FULL коллатерали и
отвергнут.

## Артефакты

- `.tmp/kaggle_phase2/out_F/ab_candidates_phase2_F.json` (kernel v7, pre-expansion)
- `.tmp/kaggle_phase2/out_F/ab_candidates_phase2_F_expanded.json` (полный стек)
- `.tmp/kaggle_phase2/out_F/ab_candidates_phase2_C.json` → `ab_candidates_phase2_D2.json` (регенерированный baseline)
- `.tmp/kaggle_phase2/out_F/ab_phase2_{F,D2}_summary.md`, `ab_phase2_{F,C}_pool.json`
- Гоча Kaggle (повторно подтверждена): датасет заливать `--dir-mode zip` и
  читать ВЕСЬ вывод аплоада («Skipping folder» = corpus не уехал, v5/v6 битые).

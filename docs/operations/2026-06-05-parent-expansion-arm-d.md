# Parent-expansion (плечо D): coverage 87% → 93/96%, MISS 6 → 3/1 — локальный замер без моделей

- Дата: 2026-06-05.
- Контекст: после Phase 2 (`docs/operations/2026-06-05-phase2-contextual-ab-production.md`)
  остались 6 MISS @ top-5 + 2 PART-регрессии; диагноз
  (`docs/operations/2026-06-05-residual-miss-diagnosis.md`) показал потенциал
  parent-контекста 8/8 и зафиксировал шов: расширение ПОСЛЕ реранка, hybrid-путь
  не трогается.
- Реализация: `HybridRetriever._expand_parents` (`vectordb/_base_manager.py`),
  флаг `RAG_PARENT_EXPANSION` (default OFF), параметры
  `RAG_PARENT_EXPANSION_WINDOW` / `RAG_PARENT_EXPANSION_MAX_CHARS`.
  Финальные top-k чанки дополняются соседними structural-секциями своего
  source-документа (текст-lookup по порядку ингеста); соседи, уже выбранные в
  top-k или добавленные другим чанком, не дублируются; контекстный заголовок
  соседа срезается (якорь уже есть у ядра).

## Метод замера — почему он точный и локальный

Экспансия выполняется после реранка ⇒ **отбор плеча D идентичен плечу C**,
меняется только текст кандидатов. Поэтому kw-coverage пересчитывается по уже
скачанным Kaggle-кандидатам C чистым текст-анализом: нарезка C воспроизводится
локально 1-в-1 (5589 чанков, как в диагнозе), экспансию делает боевой
`_expand_parents`, не реимплементация. Kaggle/Colab/iMac не нужны.
Стадия: `scripts/ab_remote_contextual.py --stage expand [--window N --max-chars M]`.

По построению регрессии невозможны: текст top-5 только растёт, kw-статус
монотонно не убывает. Риск смещён в judge-метрики (precision/faithfulness
при разбавлении контекста) — поэтому R7-judge обязателен (ниже).

## Coverage @ top-5 (100 кейсов)

| плечо | FULL | PART | MISS |
|---|---|---|---|
| C (structural, prod default) | 87 | 7 | 6 |
| D1 = C + expansion (window=1, max=2400) | **93** | 4 | 3 |
| D2 = C + expansion (window=2, max=3600) | **96** | 3 | **1** |

Переходы C→D2: 5 MISS→FULL (dangerous-goods-clearance, waybill-first-mile,
perishable-temperature, customs-broker-escalation, cross-border-required-fields)
+ 4 PART→FULL (waybill-escalation-events, employment-contract-essential-terms,
perishable-special-cargo-evidence, breach-notification-participants).

### 8 проблемных кейсов диагноза (4 регрессии Phase 2 + 4 deep)

| кейс | C | D1 | D2 |
|---|---|---|---|
| customs-broker-escalation | MISS | MISS | **FULL** |
| dangerous-goods-clearance | MISS | **FULL** | **FULL** |
| breach-notification-participants | PART | **FULL** | **FULL** |
| perishable-special-cargo-evidence | PART | **FULL** | **FULL** |
| customs-clearance-fields | MISS | MISS | MISS |
| waybill-first-mile-fields | MISS | **FULL** | **FULL** |
| perishable-temperature-controls | MISS | MISS | **FULL** |
| cross-border-required-fields | MISS | **FULL** | **FULL** |

D2 закрывает 7/8; обе регрессии Phase 2 типа FULL→MISS/PART→MISS восстановлены.
Остаточный MISS — customs-clearance-fields (kw-связка в чанке r27 пула, до
top-5 не доехала; sections added 4/5 — один кандидат не нашёлся в локальной
нарезке либо у границы дока). Кандидат на query-expansion, как и было
запланировано в диагнозе.

## R7 LLM-judged (mistral-small, 100 кейсов, post-rerank top-5 c экспансией)

Базы сравнения: A faith 0.8747 / recall 0.855; C faith 0.9092 / rel 0.864 /
prec 0.5073 / recall 0.905 (`reports/ragas/20260605T*`).

| плечо | faithfulness | relevancy | precision | recall | run_id |
|---|---|---|---|---|---|
| C | 0.9092 | 0.864 | 0.5073 | 0.905 | 20260605T052606Z |
| D1 (w=1/2400) | 0.8528¹ | 0.861 | 0.55 | **0.95** | 20260605T101506Z |
| D2 (w=2/3600) | 0.864¹ | **0.8945** | **0.5759** | **0.975** | 20260605T103014Z |

¹ **Aggregate-просадка faithfulness — артефакт судьи, не свойство плеча.**
Доказательства:
- Per-case медианная дельта = **0.000** в обоих сравнениях (C↔D1 и C↔D2);
  mean (−0.056/−0.045) целиком набран единичными флипами 1.0→0.0
  (6 кейсов в D1, 3 в D2).
- Флипнувшие кейсы D1 и D2 **не пересекаются** — контент-проблема дала бы
  одни и те же кейсы в обоих окнах.
- `sick-leave-required-fields`: **байт-в-байт идентичный ответ** в C и D1,
  судья дал 1.0 vs 0.0; `templates-insufficient` — отличие в одно слово.
Паттерн: mistral-small-judge флапает (вероятно, фейл извлечения statements на
коротких ответах/длинных промптах → 0). Полоса шума снята повторным judge C
на тех же контекстах (ниже).

## Полоса шума судьи (re-judge C на тех же контекстах)

| прогон | aggregate faith | zeros | mean без нулей |
|---|---|---|---|
| C run1 (052606Z) | 0.9092 | 6 | 0.9672 |
| C run2 (104909Z) | 0.9132 | 5 | 0.9613 |
| D1 (101506Z) | 0.8528 | 10 | 0.9475 |
| D2 (103014Z) | 0.8640 | 7 | 0.9291 |

- C повторяем: агрегат ±0.004, **5 из 5-6 zero-кейсов общие** (стабильные).
- Zero-кейсы D1∩D2 = 2 — добавочные нули случайны, их частота растёт с длиной
  контекста (флип-артефакт).
- Без нулей остаточная разница D2−C ≈ −0.03 (paired both-nonzero: mean −0.0365,
  **медиана 0.000**) — реальная, но малая и сконцентрированная в меньшинстве
  кейсов цена разбавления.

## Решение — `RAG_PARENT_EXPANSION` default ON, window=2 / max_chars=3600

За: FULL 87→96 @ top-5, recall 0.905→0.975, precision 0.507→0.576 (вырос,
не упал), relevancy 0.864→0.895, обе жёсткие регрессии Phase 2 восстановлены,
7/8 проблемных кейсов закрыты. Против: остаточная цена faithfulness
−0.02..−0.04 (медиана per-case 0.000) + контекст до 5×3600 символов
(+латентность/токены генерации).

Итоговый стек vs production-baseline A (до Phase 2): recall 0.855→0.975,
faithfulness 0.875→0.864 (в пределах артефакта судьи), FULL 82→96.

- Откат: `RAG_PARENT_EXPANSION=false`.
- Консервативный конфиг (меньше цена faithfulness, mean без нулей 0.9475):
  `RAG_PARENT_EXPANSION_WINDOW=1`, `RAG_PARENT_EXPANSION_MAX_CHARS=2400` →
  FULL 93, recall 0.95.
- Остаточный MISS: customs-clearance-fields → рычаг query-expansion
  (следующий цикл, см. диагноз).
- Судья: mistral-small флипает 1.0→0.0 чаще на длинных контекстах — при
  будущих сравнениях плеч с разной длиной контекста смотреть медиану и
  mean-без-нулей, не только агрегат.

## Стоимость трейдоффа

Контекст для LLM растёт: C ≈ 5×~800 символов, D1 ≤ 5×2400, D2 ≤ 5×3600.
Это +латентность/токены на генерацию — при включении дефолтом зафиксировать
в README/конфиге.

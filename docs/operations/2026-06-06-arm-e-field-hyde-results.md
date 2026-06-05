# Плечо E (field-aware HyDE): результаты — NO-SHIP, диагноз rerank-демоции записан

- Дата: 2026-06-06. Продолжение `2026-06-05-query-expansion-probe.md` (шаги 3-4 цикла).
- Плечо E = C-конфиг чанкинга + field-aware HyDE расширенные запросы для
  dense+BM25+rerank (kernel v6, CPU, 5.7h) + parent-expansion w=2/3600 локально
  (`--stage expand --label E`) = полный стек, сравнимый с D2 1-в-1.
- Контракт judge соблюдён: `query` = оригинальный вопрос (генерация),
  `expanded_query` — только retrieval/rerank.

## Результаты

### kw-coverage @ top-5 (100 кейсов)

| плечо | FULL | PART | MISS |
|---|---|---|---|
| E-pre (без экспансии) | 79 | 12 | 9 |
| **E (полный стек)** | **89** | 6 | 5 |
| D2 (baseline) | **96** | 3 | 1 |

Матрица переходов D2 → E: **1 gain / 8 регрессий, нетто −7 FULL**.

- Gain: `customs-clearance-fields` MISS→FULL — ровно целевой кейс пробы
  (последний MISS D2). Query-side гэп NL RU ↔ snake_case реально мостится.
- Регрессии: 5 FULL→MISS (`access-control-review`,
  `cross-border-pdn-required-fields`, `data-retention-required-fields`,
  `internal-transfer-consent`, `perishable-temperature-controls`)
  + 3 FULL→PART (`breach-notification-participants`, `leave-compensation`,
  `waybill-escalation-events`).

### R7-judge (mistral-small, 300 вызовов, run `20260605T214926Z-e728353a`)

С поправкой на гочу судьи (медиана / mean-без-нулей, cont.15):

| метрика | E agg | E mean>0 (zeros) | D2 agg | D2 mean>0 (zeros) |
|---|---|---|---|---|
| context_recall | 0.920 | 0.9684 (5) | **0.975** | **0.9848** (1) |
| context_precision | 0.509 | — (0) | **0.576** | — (0) |
| answer_relevancy | 0.833 | 0.8862 (6) | **0.895** | 0.9035 (1) |
| faithfulness | 0.766 | 0.9455 (19) | 0.864 | 0.9291 (7) |

E проигрывает D2 по всем метрикам и в aggregate, и в mean-без-нулей
(faithfulness mean>0 у E чуть выше, но zeros 19 vs 7 — полоса шума длинных
контекстов плюс честная цена регрессий; медианы всюду равны).

**Перекрёстная валидация: judge recall-zeros E = ровно те же 5 кейсов
FULL→MISS из kw-матрицы, 1-в-1.** Два независимых замера (kw-substring и
LLM-judge) сошлись — регрессии реальны, не шум.

## Диагноз регрессий: реранкер с длинным расширенным запросом

По прерank-пулам E (top-40, RRF-порядок) для 8 регрессий:

| кейс | kw-ранги в пуле E | характер |
|---|---|---|
| access-control-review | 1, 1 | rerank |
| cross-border-pdn-required-fields | 1, 2 | rerank |
| data-retention-required-fields | 1, 1 | rerank |
| internal-transfer-consent | 9, 9 | rerank |
| perishable-temperature-controls | 8, 8 | rerank |
| breach-notification-participants | 1, 35 | rerank |
| leave-compensation | 1, 1 | rerank |
| waybill-escalation-events | 5, — | pool (kw выпал из top-40) |

**7/8 — rerank-фейлы: kw-чанки СТОЯТ в пуле (часто RRF rank 1), но
cross-encoder, скорящий против расширенного запроса (медиана 574 символа:
гипотетический ответ + список полей), демотирует их из top-5.** Пулы от
расширения выигрывают (kw-чанки высоко), реранк — проигрывает: длинный
HyDE-текст размывает релевантность узких kw-секций.

## Решение

**NO-SHIP: field-aware промпт в `_build_hyde_prompt` НЕ внедряем** (ни флагом,
ни заменой при `RAG_HYDE`). Цена (−7 FULL kw, recall 0.975→0.920,
precision 0.576→0.509) многократно выше выигрыша (1 целевой кейс).
D2-конфигурация (structural chunking + parent-expansion w=2/3600) остаётся
production-стеком; единственный остаточный MISS — `customs-clearance-fields`.

## Будущий рычаг (кандидат, НЕ задача)

Split-query (арм F): **expanded query только для пулов (BM25+dense), оригинал —
для реранкера.** Обоснование из данных этого плеча: в пулах E kw-чанки
регрессий стоят на rank 1-9 — реранк по оригинальному запросу (как в C/D2,
где эти кейсы FULL) с большой вероятностью их поднимет, сохранив gain
целевого кейса (его kw-чанк в пуле E тоже есть). Текущий production-путь
(`hyde_query → get_relevant_documents`) такого split не поддерживает —
потребуется отдельный параметр retriever'а. Делать только по явному запросу.

## Артефакты

- `.tmp/kaggle_phase2/out_E/ab_candidates_phase2_E.json` (kernel v6, pre-expansion)
- `.tmp/kaggle_phase2/out_E/ab_candidates_phase2_E_expanded.json` (полный стек, вход judge)
- `.tmp/kaggle_phase2/out_E/ab_phase2_E_summary.md` (E-pre → E матрица)
- `reports/ragas/20260605T214926Z-e728353a-aircargo-ragas.{json,md}`
- Гоча Kaggle: первый `kernels output` оборвался `IncompleteRead` на 2.5MB/8MB —
  retry прошёл; пустой `out_E/*.json` после обрыва удалить перед повтором.

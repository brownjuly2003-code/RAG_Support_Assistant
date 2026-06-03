# R7 LLM-judged baseline — генерация измерена (faithfulness 0.833 / relevancy 0.838)

- Дата: 2026-06-03
- Цель: снять потолок «недоказанного качества» (оба аудита оценивали proven-quality
  6.5/10, т.к. faithfulness / answer_relevancy **никогда не измерялись** — free LLM-API
  гео-блокированы с RU IP). Дополняет `2026-06-03-free-r7-retrieval-baseline.md`,
  который закрыл только retrieval-сторону.
- Разблокировка: добавлен провайдер `mistral` в `scripts/aircargo_ragas_free.py`
  (OpenAI-совместимый endpoint Mistral **доступен с RU IP без VPN**, через проектный
  `MISTRAL_API_KEY`). Это единственный путь к LLM-судье без карты/VPN.
- Судья + генератор: `mistral-small-latest` (один LLM на обе роли, как во free-скрипте).
- Корпус: aircargo, 100 RU curated-кейсов; контексты — те же закэшированные RRF top-k
  (`.tmp/ab_candidates.json`, БЕЗ production-реранка bge-reranker-v2-m3). Переингест не нужен.
- Прогон: 100/100 кейсов, **300 LLM-вызовов** (generate + faithfulness-judge +
  relevancy-judge на кейс), 0 generate-ошибок, 0 пустых ответов. Стоимость sub-dollar.
- Run id: `20260603T031646Z-e437ad07`
  (`reports/ragas/20260603T031646Z-e437ad07-aircargo-ragas.{md,json}`).

## Результат — впервые измеренная генерация

| Метрика | mean | примечание |
|---|---|---|
| **faithfulness** (LLM-judged) | **0.833** | 🆕 ответ опирается только на контекст |
| **answer_relevancy** (LLM-judged) | **0.838** | 🆕 ответ отвечает на вопрос |
| context_precision (keyword) | 0.488 | подтверждает retrieval-baseline |
| context_recall (keyword) | 0.785 | подтверждает retrieval-baseline |

`context_precision`/`recall` совпали с прошлым прогоном до тысячных → сигнал устойчив,
не артефакт одного запуска.

## Главный вывод: бутылочное горло — retrieval, не генерация

Корреляция faithfulness с recall (LLM-judge на 91 кейсе с явным recall):

| Группа кейсов | faithfulness | n |
|---|---|---|
| zero-recall (нужный фрагмент не найден) | **0.624** | 17 |
| full-recall (всё найдено) | **0.893** | 74 |

Когда retrieval попадает, генерация надёжна (0.893). Просадка faithfulness идёт ровно
там, где ретривер мажет. **Качество ответов упирается в retrieval-recall/precision, а
не в LLM.** Дальнейший тюнинг промптов/моделей генерации даст мало — работать надо над
retrieval.

## Actionable: класс запросов `*-required-fields` систематически промахивается

Все 17 zero-recall кейсов концентрированы на запросах «какие поля/реквизиты обязательны»
и escalation-сценариях:

```
dangerous-goods-fields · customs-clearance-fields · waybill-first-mile-fields
waybill-escalation-events · incident-response-required-fields · access-control-review
driver-hours-required-fields · warehouse-3pl-required-fields · perishable-temperature-controls
oversized-permit-route · subject-rights-required-fields · conflict-interest-sanctions
fuel-supply-evidence · gps-monitoring-required-fields · weight-control-required-fields
cross-border-required-fields · breach-notification-required-fields
```

Нужный фрагмент (как правило — список конкретных полей в таблице/структурной секции) не
доходит до RRF top-k. Это recall ретривера: structural-chunking A/B его НЕ закрыл
(recall-neutral 73% vs 74%). Кандидаты на следующий шаг (measure→fix→re-measure):

1. **BGE-M3 native sparse** (R5-продолжение) — lexical-составляющая для точечных
   «обязательные поля X» запросов, где dense-эмбеддинг размывает специфику.
2. **Query-expansion / HyDE** на `*-required-fields`-классе.
3. **Parent-child / section-aware chunking** — чтобы список полей не дробился на чанки,
   теряющие заголовок-якорь.
4. Проверить полноту корпуса по этим темам (нет фрагмента → recall недостижим в принципе).

## Воспроизведение

```
set -a; . ./.env; set +a        # подгружает MISTRAL_API_KEY, не печатает
python scripts/aircargo_ragas_free.py --provider mistral --min-interval 1.2
```

Heavy-ингест BGE-M3 / production-реранк — по-прежнему только Colab/iMac (на Windows-хосте
запрещён >1 GiB). LLM-judging же — чистые API-вызовы на закэшированных контекстах, локально OK.

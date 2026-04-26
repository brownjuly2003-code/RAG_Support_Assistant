# Regression Eval — ministral-3b-latest vs gracekelly-mixed

- Run ID: `20260426T113855Z-1f7a6479`
- Created at: `2026-04-26T11:38:55.577956+00:00`
- Dataset: `D:\RAG_Support_Assistant\evaluation\curated_cases.jsonl`
- Tenant: `all`
- Mode: `live-provider-benchmark`

## Summary

| Metric | Value |
| --- | --- |
| Baseline | `ministral-3b-latest` |
| Candidate | `gracekelly-mixed` |
| Baseline pass rate | 60.00% |
| Candidate pass rate | 30.00% |
| Regressions | 6 |
| New passes | 0 |
| Neutral | 14 |
| Baseline avg latency | 0.0 ms |
| Candidate avg latency | 0.0 ms |
| Baseline total cost | $0.000297 |
| Candidate total cost | $0.000000 |
| Baseline refusal rate | 35.00% |
| Candidate refusal rate | 25.00% |
| Gate | fail |

## Gate Reasons

- max regressions exceeded: 6 > 2
- candidate pass rate 30.00% below minimum 85.00%
- candidate pass rate 30.00% below baseline 60.00%

## Regressions

### warranty-no-receipt-where
- Query: Чек утерян. Куда можно обратиться по гарантии?
- Baseline answer: По гарантии при утере чека можно обратиться в **сервисный центр** или **службу поддержки** (см. [2]).

Возврат товара надлежащего качества без чека не предусмотрен [1].
- Candidate answer: В предоставленном документе указано, что для обращения по гарантии необходимо подготовить чек. Информации о том, как действовать в случае его утери, в данных правилах нет.
pravoved
+1
По имеющимся данным ответить на ваш вопрос невозможно. Пожалуйста, обратитесь в службу поддержки для получения дальнейших инструкций.
- Detail: answer missing 'сервис'

### returns-window
- Query: В течение скольких дней можно вернуть товар надлежащего качества?
- Baseline answer: В течение **14 дней** с момента покупки можно вернуть товар надлежащего качества [1].
- Candidate answer: По предоставленному контексту информация о сроках возврата товара надлежащего качества не указана. Ответить нельзя на основании данных документов.
Пожалуйста, обратитесь к специалисту службы поддержки или к условиям продажи/оферте вашего магазина, где указаны сроки возврата товара надлежащего качества.
- Detail: answer missing '14'; answer missing 'дн'

### error-e25
- Query: На дисплее появилась ошибка E25. Что сначала попробовать клиенту?
- Baseline answer: Сначала **перезагрузите устройство** [Документ 1, E25].
Если ошибка не исчезнет, выполните **сброс к заводским настройкам** [Документ 1, E25].
- Candidate answer: [model_mismatch] Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'.
- Detail: answer missing 'E25'; answer missing 'перезагруз'

### error-e30
- Query: При ошибке E30 можно продолжать пользоваться устройством или нужно отключить его от сети?
- Baseline answer: По имеющимся данным из предоставленного контекста ответить нельзя.

В документе **errors_e10_e30.md** нет информации о том, как поступать при ошибке **E30** — можно ли продолжать использовать устройство или отключать его от сети. Для уточнения рекомендую обратиться к специалисту поддержки.
- Candidate answer: [model_mismatch] Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'.
- Detail: answer missing 'E30'; answer missing 'отключ'

### error-e20-clog-vs-pump
- Query: По ошибке E20 как отличить засор фильтра от неисправности насоса?
- Baseline answer: По ошибке **E20** в контексте невозможно точно определить, засорён ли фильтр или неисправен насос, так как в документах не приведены конкретные признаки или тесты для диагностики [1, 2, 3, 4].

Для уточнения причины рекомендуется обратиться в сервисный центр или специалиста поддержки.
- Candidate answer: [model_mismatch] Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'.
- Detail: answer missing 'E20'; answer missing 'засор'; answer missing 'насос'

### off-topic-price
- Query: Сколько стоит этот товар?
- Baseline answer: По имеющимся данным ответить нельзя.

В предоставленном контексте нет информации о стоимости товара. Для получения точных данных рекомендую обратиться к специалисту поддержки или на сайт производителя.
- Candidate answer: [model_mismatch] Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'.
- Detail: answer missing 'ответить нельзя'; answer missing 'обрат'


## New Passes

None.

## Aggregate Metrics

- Total cases: 20
- Baseline pass rate: 60.00%
- Candidate pass rate: 30.00%
- Baseline avg latency: 0.0 ms
- Candidate avg latency: 0.0 ms
- Baseline total cost: $0.000297
- Candidate total cost: $0.000000
- Baseline refusal rate: 35.00%
- Candidate refusal rate: 25.00%

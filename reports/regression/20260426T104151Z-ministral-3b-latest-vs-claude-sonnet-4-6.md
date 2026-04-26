# Regression Eval — ministral-3b-latest vs claude-sonnet-4-6

- Run ID: `20260426T104151Z-9b06b8d9`
- Created at: `2026-04-26T10:41:51.135857+00:00`
- Dataset: `D:\RAG_Support_Assistant\evaluation\curated_cases.jsonl`
- Tenant: `all`
- Mode: `live-provider-benchmark`

## Summary

| Metric | Value |
| --- | --- |
| Baseline | `ministral-3b-latest` |
| Candidate | `claude-sonnet-4-6` |
| Baseline pass rate | 100.00% |
| Candidate pass rate | 0.00% |
| Regressions | 2 |
| New passes | 0 |
| Neutral | 0 |
| Baseline avg latency | 0.0 ms |
| Candidate avg latency | 0.0 ms |
| Baseline total cost | $0.000025 |
| Candidate total cost | $0.000000 |
| Baseline refusal rate | 0.00% |
| Candidate refusal rate | 0.00% |
| Gate | fail |

## Gate Reasons

- candidate pass rate 0.00% below minimum 85.00%
- candidate pass rate 0.00% below baseline 100.00%

## Regressions

### warranty-period
- Query: Какой срок гарантии на продукцию?
- Baseline answer: Срок гарантии на продукцию составляет **12 месяцев с момента покупки** [1].
- Candidate answer: Не удалось обработать запрос автоматически. Ваш вопрос передан оператору — мы ответим в ближайшее время.
- Detail: quality 0 below minimum 0.5; answer missing '12'; answer missing 'месяц'

### warranty-receipt-storage
- Query: На какой срок нужно сохранять чек для гарантии?
- Baseline answer: Согласно гарантийным условиям, сохранять кассовый или товарный чек необходимо **в течение 12 месяцев с момента покупки** для подтверждения права на гарантию [1].
- Candidate answer: Не удалось обработать запрос автоматически. Ваш вопрос передан оператору — мы ответим в ближайшее время.
- Detail: quality 0 below minimum 0.5; answer missing 'чек'; answer missing '12'


## New Passes

None.

## Aggregate Metrics

- Total cases: 2
- Baseline pass rate: 100.00%
- Candidate pass rate: 0.00%
- Baseline avg latency: 0.0 ms
- Candidate avg latency: 0.0 ms
- Baseline total cost: $0.000025
- Candidate total cost: $0.000000
- Baseline refusal rate: 0.00%
- Candidate refusal rate: 0.00%

# Regression Eval — ministral-3b-latest vs mistral-small-latest

- Run ID: `20260424T071115Z-885a2766`
- Created at: `2026-04-24T07:11:15.042043+00:00`
- Dataset: `D:\RAG_Support_Assistant\evaluation\curated_cases.jsonl`
- Tenant: `all`
- Mode: `live-provider-benchmark`

## Summary

| Metric | Value |
| --- | --- |
| Baseline | `ministral-3b-latest` |
| Candidate | `mistral-small-latest` |
| Baseline pass rate | 100.00% |
| Candidate pass rate | 80.00% |
| Regressions | 1 |
| New passes | 0 |
| Neutral | 4 |
| Baseline avg latency | 0.0 ms |
| Candidate avg latency | 0.0 ms |
| Baseline total cost | $0.000068 |
| Candidate total cost | $0.000389 |
| Baseline refusal rate | 40.00% |
| Candidate refusal rate | 0.00% |
| Gate | fail |

## Gate Reasons

- candidate pass rate 80.00% below minimum 85.00%
- candidate pass rate 80.00% below baseline 100.00%

## Regressions

### returns-refund-timeline
- Query: How long does the refund take after a return is accepted?
- Baseline answer: Согласно **Документа 3** [N=3], срок возврата денежных средств после принятия товара составляет **до 10 рабочих дней**.
- Candidate answer: The refund is processed within 10 business days after the item is accepted for return [2].
- Detail: answer missing 'дн'


## New Passes

None.

## Aggregate Metrics

- Total cases: 5
- Baseline pass rate: 100.00%
- Candidate pass rate: 80.00%
- Baseline avg latency: 0.0 ms
- Candidate avg latency: 0.0 ms
- Baseline total cost: $0.000068
- Candidate total cost: $0.000389
- Baseline refusal rate: 40.00%
- Candidate refusal rate: 0.00%

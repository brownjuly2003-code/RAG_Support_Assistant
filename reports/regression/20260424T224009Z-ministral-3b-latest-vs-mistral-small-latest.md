# Regression Eval — ministral-3b-latest vs mistral-small-latest

- Run ID: `20260424T224009Z-0da9edc1`
- Created at: `2026-04-24T22:40:09.567195+00:00`
- Dataset: `D:\RAG_Support_Assistant\evaluation\curated_cases.jsonl`
- Tenant: `all`
- Mode: `live-provider-benchmark`

## Summary

| Metric | Value |
| --- | --- |
| Baseline | `ministral-3b-latest` |
| Candidate | `mistral-small-latest` |
| Baseline pass rate | 100.00% |
| Candidate pass rate | 66.67% |
| Regressions | 1 |
| New passes | 0 |
| Neutral | 2 |
| Baseline avg latency | 0.0 ms |
| Candidate avg latency | 0.0 ms |
| Baseline total cost | $0.000034 |
| Candidate total cost | $0.000212 |
| Baseline refusal rate | 0.00% |
| Candidate refusal rate | 0.00% |
| Gate | fail |

## Gate Reasons

- candidate pass rate 66.67% below minimum 85.00%
- candidate pass rate 66.67% below baseline 100.00%

## Regressions

### returns-refund-timeline
- Query: How long does the refund take after a return is accepted?
- Baseline answer: Согласно **Документа 3 [N=3]**, срок возврата денежных средств после принятия возврата составляет **до 10 рабочих дней**.
- Candidate answer: Refunds are processed within 10 business days after the return is accepted. [1, 2]
- Detail: answer missing 'дн'


## New Passes

None.

## Aggregate Metrics

- Total cases: 3
- Baseline pass rate: 100.00%
- Candidate pass rate: 66.67%
- Baseline avg latency: 0.0 ms
- Candidate avg latency: 0.0 ms
- Baseline total cost: $0.000034
- Candidate total cost: $0.000212
- Baseline refusal rate: 0.00%
- Candidate refusal rate: 0.00%

# Regression Eval — ministral-3b-latest vs claude-sonnet-4-6-api

- Run ID: `20260425T040428Z-99b49efd`
- Created at: `2026-04-25T04:04:28.662809+00:00`
- Dataset: `D:\RAG_Support_Assistant\evaluation\curated_cases.jsonl`
- Tenant: `all`
- Mode: `live-provider-benchmark`

## Summary

| Metric | Value |
| --- | --- |
| Baseline | `ministral-3b-latest` |
| Candidate | `claude-sonnet-4-6-api` |
| Baseline pass rate | 100.00% |
| Candidate pass rate | 0.00% |
| Regressions | 1 |
| New passes | 0 |
| Neutral | 0 |
| Baseline avg latency | 0.0 ms |
| Candidate avg latency | 0.0 ms |
| Baseline total cost | $0.000014 |
| Candidate total cost | $0.000000 |
| Baseline refusal rate | 0.00% |
| Candidate refusal rate | 0.00% |
| Gate | fail |

## Gate Reasons

- candidate pass rate 0.00% below minimum 85.00%
- candidate pass rate 0.00% below baseline 100.00%

## Regressions

### warranty-receipt-storage
- Query: На какой срок нужно сохранять чек для гарантии?
- Baseline answer: Согласно **гарантийным условиям** (Документ 1), чек нужно сохранять **в течение всего срока гарантии (12 месяцев)**.

[1]
- Candidate answer: [provider_unavailable] Anthropic API key is not configured.
- Detail: answer missing 'чек'; answer missing '12'


## New Passes

None.

## Aggregate Metrics

- Total cases: 1
- Baseline pass rate: 100.00%
- Candidate pass rate: 0.00%
- Baseline avg latency: 0.0 ms
- Candidate avg latency: 0.0 ms
- Baseline total cost: $0.000014
- Candidate total cost: $0.000000
- Baseline refusal rate: 0.00%
- Candidate refusal rate: 0.00%

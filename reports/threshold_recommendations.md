# Threshold recommendations - 2026-04-21

Based on 3 traces (last 30 days), 3 proxy-labeled.

## quality_threshold
- Current: 80
- Suggested: insufficient data
- Detail: insufficient labeled traces (1 < 20)
- Distribution chart:
```text
50 | #################### (1)
```

## fact_verification_min_score
- Current: 70
- Suggested: insufficient data
- Detail: insufficient labeled traces (0 < 20)
- Distribution chart:
```text
no data
```

## escalation_threshold
- Current: 0.7
- Suggested: insufficient data
- Detail: insufficient labeled traces (1 < 20)
- Distribution chart:
```text
0.5 | #################### (1)
```

## slow_trace_threshold_ms
- Current: 10000
- Suggested: insufficient data
- Detail: insufficient labeled traces (0 < 20)
- Distribution chart:
```text
no data
```

## YAML patch
```yaml
# copy to .env if accepting recommendation:
```

## Caveats
- Human review_queue verdicts were unavailable; recommendations use proxy labels from traces with final_route == 'human'.
- escalated_tickets could not be joined back to trace_id in the current schema, so proxy labels rely on trace routing only.
- No duration_ms values were found in trace snapshots for the selected window.
- No fact_score values were found in trace snapshots for the selected window.

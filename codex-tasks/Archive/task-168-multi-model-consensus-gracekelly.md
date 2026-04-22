# Task 168 — Multi-model consensus through GraceKelly

## Closed
- Added `FACT_VERIFY_CONSENSUS_ENABLED` and `FACT_VERIFY_RELIABILITY_LEVEL`.
- `verify_facts` can use schema-constrained consensus responses instead of plain-text verdict parsing.
- Added Prometheus counter `fact_verification_consensus_total{level,verdict}`.

## Caveat
- `standard` and `high` reliability levels are slower because they imply multiple model calls.

## Verified by
- `tests/test_provider_graph_integration.py`


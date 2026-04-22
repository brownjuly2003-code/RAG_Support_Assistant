# Task 161 — Chaos drills

## Closed
- `scripts/chaos_drill.py` — manual-trigger CLI for six faults:
  `ollama_timeout`, `ollama_down`, `postgres_unavailable`,
  `redis_unavailable`, `network_slow`, `network_flaky`.
- Deterministic acceptance rules per fault; flaky drill uses a seeded
  RNG; markdown report with timeline + metrics.
- Not wired into CI by design.

## Verified by
- `tests/test_chaos_drill.py`

# Task 145 - Provider cost accounting and observability

## Goal
Сделать provider-aware cost attribution полноценной частью traces и
Prometheus-метрик.

## Context
- В проекте уже был `cost_usd`, но не было provider registry как основного
  pricing source.
- Batch G требует cost breakdown по provider/model/tenant и видимость в admin
  observability surface.

## Deliverables
1. `sqlite_trace.py` и `tracing/sqlite_trace.py`
   - сохраняют `provider_name`, `model_name`, prompt/completion tokens,
     `cost_usd`.
   - pricing берётся из `config/providers.yml`, legacy prices остаются fallback.
   - stale usage из чужих graph nodes не должна ломать cost attribution.
2. `monitoring/prometheus.py`
   - metric `llm_cost_usd_total{provider,model,tenant}`
   - helper `record_llm_cost(...)`
3. `agent/graph.py` / `agent/state.py`
   - usage metadata собирается из provider-backed responses и мержится в state.
4. `llm/providers/runtime.py`
   - daily paid cost guardrail по `DAILY_COST_LIMIT_USD`.
5. Tests
   - `tests/test_provider_cost_accounting.py`
   - доп. проверки в `tests/test_provider_abstraction.py`

## Acceptance
- `pytest tests/test_provider_cost_accounting.py tests/test_provider_abstraction.py -q`
  зелёный.
- `trace_steps` содержит `provider_name` и корректный `cost_usd`.
- `/metrics` содержит `llm_cost_usd_total{provider,model,tenant}` после trace
  logging.
- Paid profile отклоняется, если уже достигнут `DAILY_COST_LIMIT_USD`.

## Notes
- Для текущего batch G отдельная Alembic migration не обязательна: достаточно
  ленивого SQLite schema upgrade, если он прозрачен и покрыт тестами.
- Cost attribution должен быть безопасным даже при старых traces и неполных
  usage payloads.

# Task 146 - Provider benchmark (mock-by-default)

## Goal
Расширить regression runner до provider/model benchmark режима без случайных
paid API вызовов в тестах и CI.

## Context
- Arc 6 уже добавил curated dataset и regression runner.
- Batch G должен использовать эту базу для provider comparisons, а не строить
  новый benchmark tool с нуля.
- Критический safeguard: benchmark по умолчанию работает через mocks.

## Deliverables
1. `scripts/regression_eval.py`
   - baseline/candidate могут быть experiment ids или provider aliases.
   - provider aliases резолвятся из `config/providers.yml`.
   - default mode: `mock-provider-benchmark`.
   - live mode доступен только через `--allow-paid-apis` или env flag.
   - report включает quality, latency, cost и refusal rate.
2. Mock benchmarking logic
   - seeded/mock answer path без реальных paid provider requests.
3. Guardrails
   - CI-safe default
   - integration with `LLM_BENCHMARK_ALLOW_PAID_APIS`
4. Tests
   - `tests/test_provider_benchmark.py`

## Acceptance
- `pytest tests/test_provider_benchmark.py -q` зелёный.
- `python scripts/regression_eval.py --baseline ollama-small --candidate claude-haiku ...`
  работает в mock mode без `--allow-paid-apis`.
- Report содержит `mode`, pass rate, avg latency, total cost и refusal rate
  для baseline/candidate.
- Без явного allow flag paid APIs не вызываются.

## Notes
- Mock benchmark может использовать curated expected answers и synthetic token
  estimates; goal — reproducible CI-safe comparison, а не идеальная симуляция.
- Exit codes regression gate должны остаться совместимыми с существующим
  workflow Arc 6.

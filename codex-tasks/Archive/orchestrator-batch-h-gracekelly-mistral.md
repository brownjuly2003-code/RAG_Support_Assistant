# Orchestrator — Batch H (GraceKelly + Mistral)

## Goal
Закрыть provider follow-up после Batch G: direct Mistral для внешнего деплоя,
GraceKelly как основной local orchestrator, local-only failover и удаление
мёртвого direct Claude/OpenAI/Gemini кода.

## Dependency graph

1. `task-150-mistral-provider.md`
   Why first: независимый paid provider, нужен как отдельный runtime target.
2. `task-151-gracekelly-provider-and-failover.md`
   Depends on: базовый provider runtime из Batch G.
   Blocks: финальный profile revamp.
3. `task-152-routing-profiles-and-cleanup.md`
   Depends on: 150 + 151.
   Why last: меняет default profile, тесты, docs и удаляет legacy files.

## Execution notes

- TDD: сначала `tests/test_mistral_provider.py`, затем
  `tests/test_gracekelly_provider.py` и `tests/test_failover_chain.py`,
  затем обновления batch G provider tests.
- Verification order:
  1. targeted provider tests
  2. provider-facing regression tests (`test_provider_*`)
  3. full `pytest tests/ -q`
  4. `ruff check .`
- Failover policy:
  only `gracekelly-primary` may auto-fallback, and only to local Ollama.
- Cost policy:
  direct Mistral respects `DAILY_COST_LIMIT_USD`; GraceKelly remains `cost_usd=0`.

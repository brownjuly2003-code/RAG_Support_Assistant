# Task 149 - Batch G verification and closure

## Goal
Закрыть Arc 7 / Batch G формальным verification sweep'ом и cleanup перед
коммитами/архивацией.

## Context
- Batch G затрагивает runtime, tracing, metrics, benchmark tooling, admin UI и
  docs. Это легко сломать незаметно без отдельного финального sweep.
- В Batch F уже использовался подход verification-first вместо декларативного
  “done”.

## Deliverables
1. Targeted pytest sweep
   - `tests/test_provider_registry.py`
   - `tests/test_provider_settings.py`
   - `tests/test_provider_abstraction.py`
   - `tests/test_provider_graph_integration.py`
   - `tests/test_provider_cost_accounting.py`
   - `tests/test_provider_benchmark.py`
   - `tests/test_provider_admin_surface.py`
2. Existing regression safety net
   - relevant legacy provider/graph tests
   - `tests/integration -q`
3. Lint
   - `ruff check .`
4. Cleanup
   - удалить временные pytest artifacts
   - проверить `git status`
5. Closure note
   - зафиксировать, нужен ли отдельный archive step после коммитов

## Acceptance
- Targeted provider pytest sweep зелёный.
- `pytest tests/integration -q` зелёный.
- `ruff check .` clean.
- Working tree не содержит случайных runtime artifacts вроде `pytest_full.log`.
- Final status явно перечисляет, что ещё не сделано только если это реально
  осталось blocker'ом.

## Notes
- Если полный `pytest tests/ -q` слишком тяжёлый для одного прогона, это
  должно быть явно отмечено в closure note вместе с тем, какие safety nets
  были использованы вместо него.
- Архивация task-spec'ов делается после коммитов, не до них.

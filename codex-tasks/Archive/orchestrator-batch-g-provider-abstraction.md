# Orchestrator - Batch G (Provider abstraction, arc 7)

## Overview
Batch G переводит проект из Ollama-first режима в provider-aware runtime:
registry, abstraction layer, cost accounting, benchmark flow и admin
observability. Foundation уже есть в Arc 6: curated dataset, experiments,
regression runner и trace analytics.

## Tasks
| # | Task | Blocked by | Parallel with | Est. hours |
|---|------|------------|----------------|-----------|
| 143 | Provider registry + settings validation | - | - | 3-4 |
| 144 | Provider runtime abstraction + graph integration | 143 | 146 | 4-5 |
| 145 | Provider cost accounting + Prometheus | 143, 144 | 146 | 3-4 |
| 146 | Provider benchmark (mock-by-default) | 143 | 144, 145 | 4-5 |
| 147 | Admin providers API + UI tab | 143, 145 | 146 | 3-4 |
| 148 | Docs and operator config surface | 143-147 | - | 2-3 |
| 149 | Verification sweep and closure | 143-148 | - | 2-3 |

## Recommended execution order

### Round 1 - foundation
- **task-143** (provider registry + settings validation)

Без единого registry дальше нельзя корректно делать aliases, pricing, profiles
и startup validation.

### Round 2 - runtime and benchmark branch
После merge task-143:
- **task-144** (provider abstraction + graph runtime)
- **task-146** (provider benchmark)

Эти задачи завязаны на registry, но могут продвигаться параллельно: runtime
нужен для live path, benchmark — для mock path и report format.

### Round 3 - economics and admin surface
После merge task-144:
- **task-145** (cost attribution + Prometheus)
- **task-147** (admin providers endpoint + UI)

Admin Providers surface должен строиться на уже записываемых
provider/model/cost traces, иначе UI получится декоративным.

### Round 4 - documentation
После merge 143-147:
- **task-148** (README, `.env.example`, changelog, roadmap)

Сначала закрываем фактическую реализацию, потом фиксируем operator/developer
story по реальным интерфейсам, а не по плану.

### Round 5 - closing sweep
После merge 143-148:
- **task-149** (verification sweep, lint, cleanup, closure notes)

## Commit and verify strategy
После каждого таска:
1. Прогнать только связанный pytest subset.
2. Проверить hard gates: fail-fast validation, no paid calls in tests, mock
   benchmark default.
3. Зафиксировать evidence против acceptance criteria task-spec'а.
4. Коммитить отдельно per task, а не batch-монолитом.

Финальный sweep для batch G:
- `pytest tests/test_provider_registry.py tests/test_provider_settings.py tests/test_provider_abstraction.py tests/test_provider_graph_integration.py tests/test_provider_cost_accounting.py tests/test_provider_benchmark.py tests/test_provider_admin_surface.py -q`
- `pytest tests/integration -q`
- `ruff check .`

## Success criteria for Arc 7 / Batch G
- `config/providers.yml` валиден по schema и загружается на startup.
- `LLM_PROVIDER_PROFILE` переключает runtime profile без поломки Ollama flow.
- Trace steps сохраняют `provider_name` и корректный `cost_usd`.
- `/metrics` отдаёт `llm_cost_usd_total{provider,model,tenant}`.
- `scripts/regression_eval.py` умеет provider aliases и по умолчанию работает
  в mock-provider-benchmark mode.
- Admin UI показывает Providers tab с реальными usage/cost fields.
- README, changelog, roadmap и task docs синхронизированы с реализацией.

## Out of scope for Batch G
- Автоматический tenant-scoped provider override через tenant metadata.
- A/B rollout automation и auto-promotion experiments.
- Provider-specific tool-use/structured-output specialization beyond common API.
- Full disaster recovery / chaos expansion.

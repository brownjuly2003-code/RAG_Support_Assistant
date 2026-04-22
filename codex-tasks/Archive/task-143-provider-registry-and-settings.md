# Task 143 - Provider registry and settings validation

## Goal
Ввести единый provider registry и fail-fast startup validation для routing
profiles, pricing metadata и paid-provider credentials.

## Context
- Arc 6 оставил систему в Ollama-first режиме без отдельного provider registry.
- Для batch G нужен source of truth для providers, aliases, pricing,
  capabilities и rate limits.
- `.env.example` должен содержать только placeholder secrets, а startup должен
  считать `changeme` отсутствующим ключом.

## Deliverables
1. `config/provider_schema.py`
   - Pydantic schema для providers, models, routing profiles и aliases.
   - Loader/validator для YAML registry.
2. `config/providers.yml`
   - Providers: `ollama`, `claude`, `openai`, `gemini`.
   - Pricing per model ($/1M input/output tokens), capabilities, rate limits,
     default fast/strong models, aliases.
   - Profiles: `latency-first`, `cost-first`, `quality-first`.
3. `config/settings.py`
   - `provider_registry_path`
   - `llm_provider_profile`
   - `llm_benchmark_allow_paid_apis`
   - `daily_cost_limit_usd`
   - `validate()` загружает registry, проверяет profile и требует реальные
     API keys для paid profiles.
4. Tests
   - `tests/test_provider_registry.py`
   - `tests/test_provider_settings.py`

## Acceptance
- `pytest tests/test_provider_registry.py tests/test_provider_settings.py -q`
  зелёный.
- `Settings.validate()`:
  - разрешает `latency-first` без paid keys
  - отклоняет unknown profile
  - отклоняет missing/placeholder (`changeme`) keys для paid profile
- `config/providers.yml` проходит schema validation.

## Notes
- Никаких секретов в registry; только metadata.
- Default profile должен оставаться `latency-first`.
- Placeholder pricing допустим, но должен быть явно редактируемым в YAML.

# Task 148 - Provider docs and operator configuration

## Goal
Синхронизировать operator/developer documentation с provider abstraction
runtime, guardrails и admin surface.

## Context
- После tasks 143-147 появляются новые env vars, routing profiles, benchmark
  modes и admin endpoint'ы.
- Без обновления docs `.env.example` и README будут вводить в заблуждение.

## Deliverables
1. `.env.example`
   - `PROVIDER_REGISTRY_PATH`
   - `LLM_PROVIDER_PROFILE`
   - `LLM_BENCHMARK_ALLOW_PAID_APIS`
   - `DAILY_COST_LIMIT_USD`
   - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
2. `README.md`
   - разделы `Providers` и `Provider benchmarking`
   - env vars и API-key setup
   - `GET /api/admin/providers`
   - `llm_cost_usd_total{provider,model,tenant}`
3. `docs/CHANGELOG.md`
   - новая секция `Arc 7 / Batch G - Provider abstraction`
4. `codex-tasks/ROADMAP.md`
   - next-arc status для Arc 7 / Batch G

## Acceptance
- README описывает profiles `latency-first`, `cost-first`, `quality-first`.
- README документирует mock-by-default benchmark и явный `--allow-paid-apis`.
- `.env.example` не содержит real secrets и явно говорит, что `changeme`
  считается отсутствующим ключом.
- CHANGELOG и ROADMAP отражают фактический scope batch G.

## Notes
- Не документировать tenant-scoped provider override как completed feature,
  если он не реализован в batch G.
- Предпочтительно описывать `config/providers.yml` как source of truth, а
  legacy pricing env vars — как fallback compatibility path.

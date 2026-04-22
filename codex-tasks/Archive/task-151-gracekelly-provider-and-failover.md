# Task 151 — GraceKelly Provider And Failover

## Goal
Сделать GraceKelly основным local orchestrator backend и добавить
контролируемый local-only failover на Ollama.

## Context
- GraceKelly уже поднимает `/healthz/ready` и `/api/v1/smart` на `:8011`.
- На стороне RAG Support Assistant GraceKelly считается proxy-orchestrator:
  платные costs не атрибутируются.
- Failover должен быть осознанным и не уходить в direct paid spend.

## Deliverables
- `llm/providers/gracekelly.py`
- `ProviderUnavailable` в `llm/providers/base.py`
- failover logic в `llm/providers/runtime.py`
- settings/env entries для GraceKelly и failover cache
- Prometheus counter `llm_provider_fallback_total`
- `tests/test_gracekelly_provider.py`
- `tests/test_failover_chain.py`
- README section про GraceKelly profile и failover semantics

## Acceptance
- `pytest tests/test_gracekelly_provider.py tests/test_failover_chain.py -q`
- `ruff check llm/providers/gracekelly.py llm/providers/runtime.py`
- no real HTTP calls to a running GraceKelly instance in tests

## Notes
- Health check lazy: только перед первым запросом provider instance.
- Auto-failover только на declared local fallback и только после
  `ProviderUnavailable`.

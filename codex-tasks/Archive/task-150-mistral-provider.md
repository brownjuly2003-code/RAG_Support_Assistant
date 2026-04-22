# Task 150 — Mistral Provider

## Goal
Добавить direct Mistral provider как дешёвый внешний runtime и fallback option
для deployment'ов без локального GraceKelly.

## Context
- Batch G уже ввёл общий `llm/providers/*` runtime.
- В `.env` есть валидный `MISTRAL_API_KEY`, но тесты не должны делать real calls.
- Нужен OpenAI-compatible chat-completions provider с учётом pricing и usage.

## Deliverables
- `llm/providers/mistral.py`
- branch в `llm/providers/runtime.py`
- provider entry в `config/providers.yml`
- `MISTRAL_API_KEY=changeme` в `.env.example`
- `tests/test_mistral_provider.py`
- README section про direct Mistral profile

## Acceptance
- `pytest tests/test_mistral_provider.py -q`
- `ruff check llm/providers/mistral.py tests/test_mistral_provider.py`
- no real paid HTTP calls in tests

## Notes
- Placeholder key `changeme` трактуется как missing.
- Rate-limit response должен маппиться в retryable error class.

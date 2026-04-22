# Task 152 — Routing Profiles And Cleanup

## Goal
Переключить проект на новый active provider set:
`ollama + gracekelly + mistral`, убрать старые paid direct providers и
синхронизировать tests/docs/operator surface.

## Context
- Старые `cost-first` / `quality-first` больше не соответствуют реальному
  deployment profile пользователя.
- GraceKelly закрывает "дорогие" модели через свой orchestration layer.
- Direct Mistral остаётся единственным осознанным paid external path.

## Deliverables
- `config/providers.yml` с `local-first`, `gracekelly-primary`,
  `external-mistral`
- default `LLM_PROVIDER_PROFILE=local-first`
- удаление `llm/providers/{anthropic,openai,gemini}.py`
- обновлённые provider tests (`test_provider_*`)
- `scripts/regression_eval.py` без legacy paid alias assumptions
- docs refresh: README, CHANGELOG, ROADMAP, arc-7 proposal

## Acceptance
- targeted provider test sweep green
- `pytest tests/ -q`
- `ruff check .`

## Notes
- `gracekelly-primary` может fallback only to Ollama.
- Исторические docs из `Archive/` можно не переписывать под новый active set.

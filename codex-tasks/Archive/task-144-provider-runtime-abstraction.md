# Task 144 - Provider runtime abstraction and graph integration

## Goal
Сделать Ollama, Claude, OpenAI и Gemini взаимозаменяемыми через общий runtime
API, не ломая существующий graph flow.

## Context
- `agent/graph.py` исторически создавал Ollama-backed LLM напрямую.
- Batch G требует profiles `latency-first`, `cost-first`, `quality-first`.
- Experiment overrides из Arc 6 уже умеют менять settings и подходят для
  provider profile selection.

## Deliverables
1. Пакет `llm/providers/`
   - `base.py`: `LLMProvider`, `LLMResponse`, shared helpers.
   - `ollama.py`, `anthropic.py`, `openai.py`, `gemini.py`.
   - `runtime.py`: `build_provider_runtime(settings)` и profile resolution.
2. `llm/__init__.py` и `llm/providers/__init__.py`
   - canonical imports для runtime layer.
3. `agent/graph.py`
   - при отсутствии injected `llm` использует provider runtime builder.
   - existing Ollama behavior остаётся рабочим через `latency-first`.
   - usage metadata из provider response прокидывается в state.
4. `agent/state.py`
   - поля для provider/model/token/cost attribution.
5. Tests
   - `tests/test_provider_abstraction.py`
   - `tests/test_provider_graph_integration.py`

## Acceptance
- `pytest tests/test_provider_abstraction.py tests/test_provider_graph_integration.py -q`
  зелёный.
- `latency-first` использует Ollama runtime.
- `quality-first` / `cost-first` выбирают корректные providers/models из
  registry.
- `CURRENT_EXPERIMENT.settings_overrides.llm_provider_profile` может override'ить
  active profile в runtime.
- Существующий graph API не меняет публичную форму ответа.

## Notes
- Не вводить provider-specific branching внутрь graph, если это можно скрыть
  за общим runtime API.
- Fallback path на локальный Ollama допустим только как compatibility behavior,
  не как новый отдельный кодовый слой.

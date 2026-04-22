# Task 166 — Tool-use unification across providers

## Closed
- Provider abstraction exposes `generate_with_tools()`.
- GraceKelly, Mistral and Ollama providers implement tool-use paths.
- `agent/graph.py` provider tool loop now uses provider-native tool calling instead of Ollama-only logic.
- Capability checks surface readable errors for unsupported providers.

## Verified by
- `tests/test_agent_tools.py`
- `tests/test_provider_abstraction.py`
- `tests/test_mistral_provider.py`
- `tests/test_ollama_provider.py`


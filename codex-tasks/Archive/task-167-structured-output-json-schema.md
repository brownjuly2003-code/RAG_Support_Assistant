# Task 167 — Structured output via JSON schema

## Closed
- Provider abstraction exposes `generate_with_schema()`.
- GraceKelly, Mistral and Ollama providers support schema-constrained responses.
- `classify_complexity` and `grade_docs` moved to provider schema path with existing fallback preserved.
- Structured output validation is enforced in provider/base helpers.

## Verified by
- `tests/test_provider_graph_integration.py`
- `tests/test_provider_abstraction.py`
- `tests/test_mistral_provider.py`
- `tests/test_ollama_provider.py`


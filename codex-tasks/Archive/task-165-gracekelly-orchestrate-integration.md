# Task 165 — GraceKelly orchestrate integration

## Closed
- `GraceKellyProvider` now decides between `/api/v1/smart` and `/api/v1/orchestrate`.
- Added `generate_with_tools()` and `generate_with_schema()`.
- `LLMResponse` carries `tool_calls` and `structured_output`.
- Added `gracekelly_use_orchestrate_for_tools` runtime flag.

## Verified by
- `tests/test_gracekelly_provider.py`
- `tests/test_provider_abstraction.py`


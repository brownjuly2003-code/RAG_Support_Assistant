# Task 169 — Streaming response through provider runtime

## Closed
- Provider abstraction exposes `generate_stream()`.
- GraceKelly, Mistral and Ollama providers expose streaming iterators.
- API adds `/api/chat/stream` while keeping `/api/ask/stream`.
- `static/chat.html` switches to the new endpoint when `STREAMING_ENABLED=true`.
- `/api/health` exposes `features.streaming_enabled` for the UI.

## Verified by
- `tests/test_chat_streaming.py`
- `tests/test_new_features.py`
- `tests/integration/test_streaming.py`


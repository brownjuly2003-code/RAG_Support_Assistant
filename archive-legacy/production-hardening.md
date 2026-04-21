# Production Hardening — RAG Support Assistant

## Goal
Сделать систему надёжной для 1000+ req/day: error handling в пайплайне, health checks, rate limiting, structured logging, config validation.

## Tasks

- [x] Task 1: `requirements.txt` — добавить `slowapi>=0.1.9`
- [x] Task 2: `state.py` — добавить поля `error: bool`, `error_message: str`, `error_node: str`; расширить `route` до `Literal["auto","human","retry","error"]`
- [x] Task 3: `graph.py` — обернуть каждый узел в try/except; добавить узел `handle_error`; обновить `_should_retry` (ветка `"error"`); добавить `"error": "handle_error"` в `add_conditional_edges`
- [x] Task 4: `config/logging_config.py` (новый) — JSON-форматтер, `setup_logging()`
- [x] Task 5: `config/settings.py` — добавить `REQUIRE_OLLAMA: bool`, метод `validate()`
- [x] Task 6: `api/app.py` — реальный `/api/health` (Ollama + ChromaDB + SQLite); slowapi rate limiting; startup lifespan с `setup_logging()` + `settings.validate()`
- [x] Task 7: Заменить `print()` на `logger` в `graph.py`, `manager.py`, `ingestion/pipeline.py`

## Done When
- [ ] Любое исключение в пайплайне → пользователь получает сообщение + тикет в inbox
- [ ] `/api/health` возвращает реальный статус зависимостей
- [ ] 429 при превышении rate limit
- [ ] Все логи — JSON с trace_id
- [ ] `REQUIRE_OLLAMA=true` → app не стартует без Ollama

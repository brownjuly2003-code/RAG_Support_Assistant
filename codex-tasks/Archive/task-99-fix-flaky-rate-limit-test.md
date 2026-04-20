# Task 99 — Fix flaky `test_ask_returns_429_after_60_requests`

## Context
`tests/test_rate_limiting.py::test_ask_returns_429_after_60_requests` —
проходит в изоляции, падает в полном прогоне. Причина: slowapi держит
state (in-memory counter) глобально в `Limiter`, и counter не сбрасывается
между тестами. Соседние тесты, которые тоже дергают `/api/ask`, уже
накачали counter, так что этот тест либо получает 429 раньше 60 запросов
(false-positive), либо counter уже выше и не достигает нужного окна.

Приоритет — низкий (не блокер), но раздражает: надо повторять пайплайн.

## Goal
Сделать тест детерминированным. Варианты:
1. Сброс state в `conftest.py` через `autouse` fixture — очищает
   `limiter._storage` между тестами
2. Monkeypatch уникального IP per-test (чтобы counter был per-test)

Предпочитаю **вариант 1** — один централизованный сброс, не надо трогать
тесты по одному.

## Files to change
- `tests/conftest.py` — добавить autouse fixture `_reset_rate_limiter`
- Возможно `tests/test_rate_limiting.py` — убрать локальные workaround'ы,
  если они есть

## Implementation

### `tests/conftest.py`

```python
@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear slowapi in-memory state between tests to prevent counter leak."""
    try:
        from api.app import limiter  # или откуда реально import'ится
        # slowapi хранит state в limiter._storage (dict для in-memory).
        # Очистка полностью сбрасывает все окна.
        storage = getattr(limiter, "_storage", None)
        if storage is not None and hasattr(storage, "storage"):
            storage.storage.clear()
        elif storage is not None and hasattr(storage, "_storage"):
            storage._storage.clear()
    except Exception:
        pass  # в тестах где limiter не import'ится — ок
    yield
```

**Замечание:** точный путь к storage зависит от версии slowapi — в
последних `limiter._storage.storage` (dict), в старых `.storage` напрямую.
Проверить через `python -c "from api.app import limiter; print(vars(limiter._storage))"`
и адаптировать. Fallback `try/except pass` защищает от ломающихся апгрейдов.

## CONSTRAINTS
- Не трогать `api/app.py` — только test-side fix
- `pytest tests/ -v --count=3 tests/test_rate_limiting.py::test_ask_returns_429_after_60_requests`
  (через pytest-repeat если есть) должен пройти 3/3 раза
- `pytest tests/ -q` — **214 passed** (или 215 если добавишь регрессионный
  тест на flakiness)
- ruff 0 errors

## DONE WHEN
- [ ] autouse fixture в `conftest.py` сбрасывает slowapi state
- [ ] Тест стабильно проходит в полном прогоне 3 раза подряд
- [ ] 214+ passed, ruff clean
- [ ] Commit: "Fix flaky rate-limit test: reset slowapi state in conftest (task-99)"

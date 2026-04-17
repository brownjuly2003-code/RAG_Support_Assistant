# Task 37 — SEC-2: Timing-safe сравнение API key

## Goal
`_require_api_key()` использует `!=` для сравнения ключей (строка 116).
Это уязвимо к timing attack — атакующий может побайтово угадать ключ,
замеряя время ответа. Нужно заменить на `hmac.compare_digest()`.

## Files to change
- `api/app.py` — функция `_require_api_key`, строка ~116

---

## api/app.py

Добавить import (вверху файла, рядом с другими stdlib-импортами):
```python
import hmac
```

Заменить функцию `_require_api_key`:

было:
```python
def _require_api_key(request: Request) -> None:
    """FastAPI dependency — validates X-API-Key header if API_KEY is configured."""
    settings = get_settings()
    expected = getattr(settings, "api_key", "")
    if not expected:
        return
    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

стало:
```python
def _require_api_key(request: Request) -> None:
    """FastAPI dependency — validates X-API-Key header if API_KEY is configured."""
    settings = get_settings()
    expected = getattr(settings, "api_key", "")
    if not expected:
        return
    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")
```

---

## CONSTRAINTS
- Изменить только `api/app.py` — одну функцию + один import
- Поведение не меняется: 401 без ключа, 403 с неверным, пропуск если ключ верный
- `pytest tests/ -v` — проходит (существующие тесты auth не ломаются)

## DONE WHEN
- [ ] `import hmac` добавлен в начало api/app.py
- [ ] `provided != expected` заменён на `not hmac.compare_digest(provided.encode(), expected.encode())`
- [ ] `grep -n "provided != expected" api/app.py` — 0 результатов
- [ ] `pytest tests/ -v` — проходит

# Task 39 — SEC-4: CORS middleware

## Goal
Нет CORS headers — браузерный фронтенд на другом домене не сможет делать запросы,
а без ограничений любой сайт может вызывать API.
Добавить `CORSMiddleware` с configurable origins через env var `CORS_ORIGINS`.

## Files to change
- `config/settings.py` — новое поле `cors_origins`
- `api/app.py` — добавить CORSMiddleware
- `.env.example` — документация нового параметра

---

## 1. config/settings.py

Добавить поле после `api_key` (строка ~133):

```python
    # CORS: список допустимых origins через запятую.
    # "*" = разрешить всё (только для dev). Пример: "https://app.example.com,https://admin.example.com"
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        ]
    )
```

Добавить `from dataclasses import dataclass, field` — уже импортирован (строка 31).

---

## 2. api/app.py

Добавить import (после существующих FastAPI-импортов):
```python
from fastapi.middleware.cors import CORSMiddleware
```

Добавить middleware после строки `app = FastAPI(...)` (строка ~903), перед `@app.middleware("http")`:

```python
# CORS
_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)
```

---

## 3. .env.example

Добавить после строки `API_KEY=`:

```
# CORS allowed origins. Comma-separated. Use "*" for dev, specific origins for production.
# Example: CORS_ORIGINS=https://app.example.com,https://admin.example.com
CORS_ORIGINS=*
```

---

## CONSTRAINTS
- Изменить только `config/settings.py`, `api/app.py`, `.env.example`
- По умолчанию `*` — чтобы не ломать текущую разработку
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `CORS_ORIGINS` парсится из env var в `settings.cors_origins`
- [ ] `CORSMiddleware` добавлен в FastAPI app
- [ ] `OPTIONS /api/ask` возвращает `Access-Control-Allow-Origin` header
- [ ] `.env.example` содержит `CORS_ORIGINS`
- [ ] `pytest tests/ -v` — проходит

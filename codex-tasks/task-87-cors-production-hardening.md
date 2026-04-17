# Task 87 — SECURITY: CORS hardening для production

## Goal
В `api/app.py:1790-1797`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins,    # default ["*"] !!
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
```

В `config/settings.py:193-199`:
```python
cors_origins: list[str] = field(
    default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
)
```

Две реальные проблемы:

### 1. Default `"*"` в production
Если инженер забыл `CORS_ORIGINS` в `.env` на проде — **любой origin** может
слать запросы к API. С учётом `X-API-Key` в `allow_headers`, злонамеренный
сайт, на который пользователь зайдёт в той же вкладке что и наше приложение,
может JavaScript'ом сделать запросы с API-ключом пользователя.

Starlette специально обрабатывает случай `*` + `allow_credentials=True`
(не шлёт `Access-Control-Allow-Credentials: true` когда origin'="*"), но это
хрупкое спасение: достаточно одного клиента, который **сам** выставит
`X-API-Key`/Bearer в fetch-запросе, и CORS не помеха (preflight пройдёт,
request улетит).

### 2. Нет startup-валидации
Никакой проверки на «prod-ready CORS». Деплой на прод с `*` проходит молча.

## Решение
1. Новый env-флаг `RAG_ENV` (`development`/`staging`/`production`), default
   `development`.
2. При `RAG_ENV=production` и `CORS_ORIGINS=*` — **startup validation
   падает с RuntimeError**. Как уже падает `REQUIRE_OLLAMA=true` без Ollama
   (task-68 / settings validate).
3. В **любом** режиме — warning в лог при `*`.
4. Env-флаг `CORS_MAX_AGE_SEC` (default 600) — preflight caching, меньше
   нагрузки на OPTIONS-запросы.
5. Не трогаем `allow_credentials` — JWT в Authorization header работает
   и без него, но текущий API ключ в `X-API-Key` ожидает browser credentials
   для некоторых сценариев. Миграция на только-Bearer — отдельная задача.

## Files to change
- `config/settings.py` — 2 env-флага + валидация в `validate()`
- `api/app.py` — передать `max_age` в CORSMiddleware, warning на startup
- `.env.example`, `README.md`

## Files to create
- `tests/test_cors_hardening.py` — 5 тестов

---

## 1. `config/settings.py`

Рядом с `cors_origins`:

```python
    rag_env: str = field(
        default_factory=lambda: os.getenv("RAG_ENV", "development").strip().lower()
    )
    cors_max_age_sec: int = field(
        default_factory=lambda: int(os.getenv("CORS_MAX_AGE_SEC", "600"))
    )
```

Расширить существующий `validate()` (там уже есть REQUIRE_OLLAMA check):

```python
    def validate(self) -> None:
        # ... существующие проверки ...

        # CORS в production: запрещаем "*"
        if self.rag_env == "production":
            if "*" in self.cors_origins or self.cors_origins == []:
                raise RuntimeError(
                    "\nERROR: CORS_ORIGINS='*' (or empty) is not allowed in production.\n"
                    "       Set CORS_ORIGINS to an explicit comma-separated list of allowed origins,\n"
                    "       e.g. CORS_ORIGINS='https://app.example.com,https://admin.example.com'\n"
                    f"       Current RAG_ENV={self.rag_env}, CORS_ORIGINS={self.cors_origins}"
                )
```

Если `validate()` ещё не вызывается в lifespan — подключить (в task-80
`_lifespan` уже зовёт `settings.validate()` на startup, иначе добавить).
В `api/app.py::_lifespan` проверить: вызов должен быть **до** создания
background tasks.

---

## 2. `api/app.py` — warning + max_age

Рядом с CORS middleware:

было:
```python
_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
```

стало:
```python
_cors_settings = get_settings()

if "*" in _cors_settings.cors_origins:
    if _cors_settings.rag_env == "development":
        logger.warning(
            "CORS_ORIGINS='*' — OK for development, but set explicit origins "
            "before deploying to production (RAG_ENV=production will refuse to start)."
        )
    else:
        # staging — мягкое предупреждение, без падения (fail'им только в prod)
        logger.error(
            "CORS_ORIGINS='*' in RAG_ENV=%s — tighten before production",
            _cors_settings.rag_env,
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
    max_age=_cors_settings.cors_max_age_sec,
)
```

**`max_age` в CORSMiddleware** — Starlette поддерживает этот параметр
с 0.27+. Браузеры кэшируют preflight на `max_age` секунд, снижая OPTIONS-
запросы для одного и того же endpoint'а. 600 = 10 минут, стандарт.

---

## 3. `.env.example`

```
# Окружение: development | staging | production
# В production CORS_ORIGINS="*" запрещён (validate() падает на старте).
RAG_ENV=development

# Preflight cache TTL (сек). Снижает OPTIONS-нагрузку.
CORS_MAX_AGE_SEC=600
```

## 4. `README.md`

В таблицу env vars:
```
| `RAG_ENV` | `development` | окружение: development/staging/production |
| `CORS_MAX_AGE_SEC` | `600` | TTL preflight cache браузеров |
```

Дописать в существующую строку `CORS_ORIGINS`:
```
| `CORS_ORIGINS` | `*` | comma-separated list разрешённых origins. При RAG_ENV=production `*` не принимается. |
```

---

## 5. `tests/test_cors_hardening.py`

```python
"""Тесты startup validation для CORS в production."""
from __future__ import annotations

import pytest


def _reload_settings(monkeypatch: pytest.MonkeyPatch):
    """Перезагрузить settings, чтобы default_factory перечитал env."""
    import config.settings as _s
    _s._settings = None
    return _s.get_settings()


def test_wildcard_cors_ok_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    s = _reload_settings(monkeypatch)
    # validate() не должен падать
    s.validate()


def test_wildcard_cors_fails_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    s = _reload_settings(monkeypatch)
    with pytest.raises(RuntimeError) as exc_info:
        s.validate()
    assert "CORS_ORIGINS" in str(exc_info.value)


def test_explicit_origins_ok_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com,https://admin.example.com")
    s = _reload_settings(monkeypatch)
    s.validate()  # не падает
    assert "https://app.example.com" in s.cors_origins
    assert "https://admin.example.com" in s.cors_origins


def test_empty_origins_fails_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORS_ORIGINS='' (пустой список) тоже запрещён в prod."""
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "")
    s = _reload_settings(monkeypatch)
    with pytest.raises(RuntimeError):
        s.validate()


def test_cors_max_age_passed_to_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """CORSMiddleware получает max_age из settings."""
    monkeypatch.setenv("CORS_MAX_AGE_SEC", "1234")
    _reload_settings(monkeypatch)

    # Reimport app чтобы пересобрать middleware stack
    import importlib
    import api.app as _app
    importlib.reload(_app)

    # Достать CORSMiddleware из stack'а
    from starlette.middleware.cors import CORSMiddleware
    cors_middleware = None
    for m in _app.app.user_middleware:
        if m.cls is CORSMiddleware:
            cors_middleware = m
            break
    assert cors_middleware is not None
    # kwargs передаются позиционно/именованно в зависимости от версии starlette
    kwargs = getattr(cors_middleware, "kwargs", None) or getattr(cors_middleware, "options", {})
    assert kwargs.get("max_age") == 1234
```

**Замечание:** `test_cors_max_age_passed_to_middleware` требует
`importlib.reload(api.app)`. Это тяжёлый тест, может конфликтовать с
другими. Если флапает — упростить: проверять через поведение (OPTIONS-запрос
с `Origin: ...` возвращает `Access-Control-Max-Age: 1234`). Но reload-вариант
чище и быстрее.

---

## CONSTRAINTS
- Никаких новых зависимостей. Starlette уже поддерживает `max_age`.
- `pytest tests/ -v` — **156+ passed** (151 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Default `RAG_ENV=development` сохраняет текущее поведение для всех
  существующих деплоев (они не выставляют `RAG_ENV`).
- `validate()` в staging только логирует error'ом, но не падает —
  staging часто имитирует prod, но хочет быстрый итерационный цикл.
- Existing tests в `test_cors_origins.py` (если есть) должны продолжать
  работать. Проверить grep'ом `test_cors`.

## DONE WHEN
- [ ] `rag_env` и `cors_max_age_sec` в Settings (default_factory)
- [ ] `validate()` падает при `rag_env=production` + `cors_origins`
      содержит `*` или пустой
- [ ] `api/app.py` логирует warning при `*` в development, error в staging
- [ ] `CORSMiddleware` получает `max_age=_cors_settings.cors_max_age_sec`
- [ ] `.env.example` и README описывают `RAG_ENV` и `CORS_MAX_AGE_SEC`
- [ ] `tests/test_cors_hardening.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 156+ passed
- [ ] `ruff check .` — 0 errors

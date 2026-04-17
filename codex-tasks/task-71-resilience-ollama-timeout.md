# Task 71 — RESILIENCE: Request timeout для Ollama

## Goal
Завершить цепочку устойчивости (timeout → retry → circuit breaker).

Сейчас `langchain_community.llms.Ollama(model=model_name)` в `graph.py:175`
создаётся **без timeout'а**. Это делает retry и circuit breaker из task-69/70
почти бесполезными на реальной деградации:

- Если Ollama не упала, а зависла (CPU swap, OOM-kill в процессе, длинный prompt
  на холодной модели) — HTTP-запрос будет висеть **неограниченно**.
- `retry_with_backoff` не сработает, потому что исключение никогда не поднимется.
- Circuit breaker тоже не откроется — ему нужен `raise`, а не `wait forever`.
- FastAPI-воркер висит, пока не истечёт общий таймаут uvicorn (по умолчанию не
  настроен). Один такой запрос ≡ один потерянный воркер.

Нужно: жёсткий per-request таймаут, после которого httpx/requests поднимет
`ReadTimeout` — это уже в allowlist'е `_RETRYABLE_EXC_NAMES`, дальше всё
работает само.

## Files to change
- `config/settings.py` — 1 env-флаг
- `graph.py` — передать `timeout=` в `Ollama(...)`
- `.env.example` — документировать переменную
- `README.md` — одна строка в таблицу env vars

## Files to create
- `tests/test_ollama_timeout.py` — 3 теста: параметр пробрасывается, дефолт, custom

---

## 1. Settings (`config/settings.py`)

Рядом с `ollama_retry_*` добавить:

```python
    ollama_request_timeout_sec: float = float(
        os.getenv("OLLAMA_REQUEST_TIMEOUT_SEC", "60")
    )
```

Дефолт 60 сек — хватает для qwen2.5:7b на CPU с длинным prompt'ом, но не
«бесконечность». Если модель отвечает дольше, почти всегда это значит, что она
зависла.

---

## 2. Интеграция в `graph.py`

В `LocalOllamaLLM.__init__`:

было:
```python
        from langchain_community.llms import Ollama
        from config.settings import get_settings
        from utils.retry import retry_with_backoff

        self._llm = Ollama(model=model_name)
        self._breaker = get_default_breaker() if breaker is _USE_DEFAULT_BREAKER else breaker
        settings = get_settings()
```

стало:
```python
        from langchain_community.llms import Ollama
        from config.settings import get_settings
        from utils.retry import retry_with_backoff

        settings = get_settings()
        self._llm = Ollama(
            model=model_name,
            timeout=getattr(settings, "ollama_request_timeout_sec", 60.0),
        )
        self._breaker = get_default_breaker() if breaker is _USE_DEFAULT_BREAKER else breaker
```

Замечания:
- `settings = get_settings()` поднимается выше, чтобы использовать и для timeout,
  и для retry-параметров — settings читаются один раз.
- `langchain_community.llms.Ollama` принимает `timeout` как `Optional[int]`
  (проверено на v0.3.x) и пробрасывает его в внутренний httpx-клиент.
  В старых версиях параметр назывался `request_timeout` — если `Ollama(...)`
  упадёт с `TypeError: unexpected keyword argument 'timeout'`, попробовать
  `request_timeout=...` как fallback.

**Fallback-стратегия**, если класс не принимает `timeout`:

```python
try:
    self._llm = Ollama(
        model=model_name,
        timeout=getattr(settings, "ollama_request_timeout_sec", 60.0),
    )
except TypeError:
    # старая версия langchain-community
    self._llm = Ollama(
        model=model_name,
        request_timeout=getattr(settings, "ollama_request_timeout_sec", 60.0),
    )
```

---

## 3. `.env.example`

Блок после retry:

```
# Timeout для одного HTTP-вызова Ollama (сек)
OLLAMA_REQUEST_TIMEOUT_SEC=60
```

## 4. `README.md`

В таблицу env vars добавить одну строку:

```
| `OLLAMA_REQUEST_TIMEOUT_SEC` | `60` | timeout одного HTTP-вызова Ollama; ReadTimeout → retry → breaker |
```

---

## 5. `tests/test_ollama_timeout.py`

Тесты «белого ящика»: не запускаем реальный Ollama, только проверяем что
параметр пробрасывается в конструктор.

```python
"""Тесты для проброса OLLAMA_REQUEST_TIMEOUT_SEC в LocalOllamaLLM."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def _reset_graph_state():
    """Сбрасывает singleton breaker'а между тестами."""
    import graph

    graph._default_breaker = None
    yield
    graph._default_breaker = None


def test_default_timeout_is_60_seconds(monkeypatch, _reset_graph_state):
    monkeypatch.delenv("OLLAMA_REQUEST_TIMEOUT_SEC", raising=False)
    import config.settings as settings_module
    settings_module._settings = None

    captured_kwargs: dict = {}

    def fake_ollama(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()

    import graph
    monkeypatch.setattr(
        "langchain_community.llms.Ollama", fake_ollama
    )

    graph.LocalOllamaLLM(model_name="test-model", breaker=None)

    timeout = captured_kwargs.get("timeout") or captured_kwargs.get("request_timeout")
    assert timeout == pytest.approx(60.0)


def test_custom_timeout_from_env(monkeypatch, _reset_graph_state):
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SEC", "15.5")
    import config.settings as settings_module
    settings_module._settings = None

    captured_kwargs: dict = {}

    def fake_ollama(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()

    import graph
    monkeypatch.setattr(
        "langchain_community.llms.Ollama", fake_ollama
    )

    graph.LocalOllamaLLM(model_name="test-model", breaker=None)

    timeout = captured_kwargs.get("timeout") or captured_kwargs.get("request_timeout")
    assert timeout == pytest.approx(15.5)


def test_timeout_setting_reachable_from_settings(monkeypatch):
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SEC", "120")
    import config.settings as settings_module
    settings_module._settings = None

    s = settings_module.get_settings()
    assert s.ollama_request_timeout_sec == pytest.approx(120.0)
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **88+ passed** (85 было + 3 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Если `langchain_community.llms.Ollama` не принимает ни `timeout`, ни
  `request_timeout` — откатить изменения и сообщить в отчёте; не ломать проект.
- `settings = get_settings()` зовётся один раз в `__init__`, не при каждом
  `invoke`.

## DONE WHEN
- [ ] `ollama_request_timeout_sec` в `Settings`, `.env.example`, README
- [ ] `Ollama(...)` в `graph.py` создаётся с `timeout=` (или `request_timeout=`
      как fallback)
- [ ] `tests/test_ollama_timeout.py` — 3 теста, все проходят
- [ ] `pytest tests/ -v` — 88+ passed
- [ ] `ruff check .` — 0 errors
- [ ] При `OLLAMA_REQUEST_TIMEOUT_SEC=5` реальный hung-запрос к Ollama поднимает
      `ReadTimeout` через 5 сек (ручная проверка, не в тестах)

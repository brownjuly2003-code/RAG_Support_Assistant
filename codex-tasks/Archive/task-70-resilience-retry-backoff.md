# Task 70 — RESILIENCE: Retry с exponential backoff для Ollama

## Goal
Circuit breaker из task-69 быстро отказывает при **устойчивых** падениях Ollama,
но не помогает при **коротких** транзитных ошибках (сеть моргнула, модель холодно
стартует, httpx timeout). Сейчас любая транзитная ошибка сразу инкрементит счётчик
breaker'а — 5 моргов подряд за сутки = OPEN, хотя каждая отдельная ошибка решалась
бы одной ретраевой попыткой.

Добавить retry с exponential backoff + jitter **внутри** breaker'а, так что
breaker видит только «окончательные» неудачи (все попытки исчерпаны), а транзитные
ошибки гасятся бесшумно.

Никаких новых зависимостей (не тащить `tenacity` / `backoff`) — 40-50 строк своей
реализации, как и с circuit breaker.

## Files to create
- `utils/retry.py` — `retry_with_backoff` + `is_retryable_error`
- `tests/test_retry.py` — 8 тестов: попытки, backoff, jitter, non-retryable, интеграция

## Files to change
- `config/settings.py` — 4 новых env-флага
- `graph.py` — обернуть `self._llm.invoke` в retry **до** передачи в breaker
- `.env.example` — документировать переменные
- `README.md` — 4 строки в таблице env vars

---

## 1. Layering (важно понять до написания кода)

Порядок обёрток вокруг raw-вызова Ollama:

```
CircuitBreaker.call(                              ← внешний: fast-fail
    retry_with_backoff(                           ← средний:  гасит транзитные
        self._llm.invoke                          ← внутренний: реальный HTTP
    ),
    prompt,
)
```

Смысл: если 3 попытки с backoff прошли успешно — breaker видит **один success**.
Если все 3 исчерпаны — breaker видит **одну failure** (а не три). Иначе breaker
откроется слишком рано на одной долгой сетевой деградации.

---

## 2. Settings (`config/settings.py`)

Рядом с блоком `circuit_breaker_*` добавить:

```python
    # --- Retry с backoff для Ollama (транзитные сетевые ошибки) ---
    ollama_retry_max_attempts: int = int(
        os.getenv("OLLAMA_RETRY_MAX_ATTEMPTS", "3")
    )
    ollama_retry_base_delay_sec: float = float(
        os.getenv("OLLAMA_RETRY_BASE_DELAY_SEC", "0.5")
    )
    ollama_retry_max_delay_sec: float = float(
        os.getenv("OLLAMA_RETRY_MAX_DELAY_SEC", "5.0")
    )
    ollama_retry_jitter: bool = os.getenv(
        "OLLAMA_RETRY_JITTER", "true"
    ).strip().lower() in ("1", "true", "yes")
```

`OLLAMA_RETRY_MAX_ATTEMPTS=1` отключает retry (останется одна попытка без пауз).

---

## 3. `utils/retry.py`

```python
"""Exponential backoff retry для сетевых вызовов Ollama."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

# Имена классов исключений, которые считаем транзитными. Сверяем по имени,
# чтобы не тащить httpx/ollama в прямые imports и не ломать окружения без них.
_RETRYABLE_EXC_NAMES = frozenset({
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "NetworkError",
    "RemoteProtocolError",
    "ResponseError",  # ollama.ResponseError — обычно на cold-start модели
})


def is_retryable_error(exc: BaseException) -> bool:
    """True если исключение похоже на транзитную сетевую ошибку."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _RETRYABLE_EXC_NAMES:
            return True
    return False


def retry_with_backoff(
    fn: Callable[..., T],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 5.0,
    jitter: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = is_retryable_error,
) -> Callable[..., T]:
    """Оборачивает `fn` в retry с exponential backoff.

    - Делает до `max_attempts` попыток (включая первую).
    - Задержка между попытками: min(base * 2**n, max), с опциональным jitter ±50%.
    - Ретраит только если `is_retryable(exc)` True; иначе пробрасывает сразу.
    - `sleep` и `is_retryable` параметризованы для тестов.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def wrapped(*args, **kwargs) -> T:
        last_exc: BaseException | None = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                if not is_retryable(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    break
                delay = min(base_delay_sec * (2 ** attempt), max_delay_sec)
                if jitter:
                    delay = delay * (0.5 + random.random())  # 0.5x..1.5x
                    delay = min(delay, max_delay_sec)
                logger.info(
                    "retry_with_backoff: attempt %d/%d failed (%s); sleeping %.2fs",
                    attempt + 1,
                    max_attempts,
                    type(exc).__name__,
                    delay,
                )
                sleep(delay)
        assert last_exc is not None  # unreachable if max_attempts >= 1
        raise last_exc

    return wrapped
```

Замечания:
- Никаких внешних зависимостей — только stdlib.
- `is_retryable_error` смотрит на `__mro__`, чтобы ловить subclass'ы.
- `BaseException` (не `Exception`) специально — чтобы `KeyboardInterrupt` тоже
  проходил через `is_retryable` и НЕ ретраился (его имени нет в allowlist).
- `sleep` и `is_retryable` инжектируются — тесты не спят реально.

---

## 4. Интеграция в `graph.py`

В `LocalOllamaLLM.__init__` сохранить retry-параметры и применять retry **до**
breaker'а:

было:
```python
class LocalOllamaLLM:
    def __init__(
        self,
        model_name: str = "mistral",
        breaker: CircuitBreaker | None | object = _USE_DEFAULT_BREAKER,
    ):
        from langchain_community.llms import Ollama
        self._llm = Ollama(model=model_name)
        self._breaker = get_default_breaker() if breaker is _USE_DEFAULT_BREAKER else breaker

    def invoke(self, prompt: str) -> str:
        if self._breaker is None:
            return self._llm.invoke(prompt)
        return self._breaker.call(self._llm.invoke, prompt)
```

стало:
```python
class LocalOllamaLLM:
    def __init__(
        self,
        model_name: str = "mistral",
        breaker: CircuitBreaker | None | object = _USE_DEFAULT_BREAKER,
    ):
        from langchain_community.llms import Ollama
        from config.settings import get_settings
        from utils.retry import retry_with_backoff

        self._llm = Ollama(model=model_name)
        self._breaker = get_default_breaker() if breaker is _USE_DEFAULT_BREAKER else breaker

        s = get_settings()
        self._invoke_with_retry = retry_with_backoff(
            self._llm.invoke,
            max_attempts=getattr(s, "ollama_retry_max_attempts", 3),
            base_delay_sec=getattr(s, "ollama_retry_base_delay_sec", 0.5),
            max_delay_sec=getattr(s, "ollama_retry_max_delay_sec", 5.0),
            jitter=getattr(s, "ollama_retry_jitter", True),
        )

    def invoke(self, prompt: str) -> str:
        if self._breaker is None:
            return self._invoke_with_retry(prompt)
        return self._breaker.call(self._invoke_with_retry, prompt)
```

**Важно:** retry-обёртка строится один раз в `__init__` — не пересоздавать в
каждом `invoke`. Settings читаются один раз при создании `LocalOllamaLLM`.

---

## 5. `.env.example`

Блок после circuit breaker:

```
# Retry для Ollama (транзитные сетевые ошибки)
OLLAMA_RETRY_MAX_ATTEMPTS=3
OLLAMA_RETRY_BASE_DELAY_SEC=0.5
OLLAMA_RETRY_MAX_DELAY_SEC=5.0
OLLAMA_RETRY_JITTER=true
```

## 6. `README.md`

В таблицу env vars добавить:

```
| `OLLAMA_RETRY_MAX_ATTEMPTS` | `3` | попыток включая первую; 1 = без retry |
| `OLLAMA_RETRY_BASE_DELAY_SEC` | `0.5` | базовая задержка между попытками |
| `OLLAMA_RETRY_MAX_DELAY_SEC` | `5.0` | верхняя граница задержки |
| `OLLAMA_RETRY_JITTER` | `true` | случайный jitter ±50% в задержке |
```

---

## 7. `tests/test_retry.py`

```python
"""Тесты для utils.retry."""
from __future__ import annotations

import pytest

from utils.retry import is_retryable_error, retry_with_backoff


class _ConnectError(Exception):
    """Симулирует httpx.ConnectError (сверка по имени класса)."""


class _ReadTimeout(Exception):
    """Симулирует httpx.ReadTimeout."""


class _Fatal(Exception):
    """Non-retryable (например, bad request)."""


def test_is_retryable_matches_by_class_name():
    assert is_retryable_error(_ConnectError("boom"))
    assert is_retryable_error(_ReadTimeout("boom"))
    assert not is_retryable_error(_Fatal("boom"))
    assert not is_retryable_error(ValueError("boom"))


def test_returns_value_on_first_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)
    assert wrapped() == "ok"
    assert calls["n"] == 1


def test_retries_transient_then_succeeds():
    seq = iter([_ConnectError("x"), _ReadTimeout("y"), "ok"])
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        val = next(seq)
        if isinstance(val, BaseException):
            raise val
        return val

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)
    assert wrapped() == "ok"
    assert calls["n"] == 3


def test_gives_up_after_max_attempts():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _ConnectError("nope")

    wrapped = retry_with_backoff(fn, max_attempts=3, sleep=lambda _: None)
    with pytest.raises(_ConnectError):
        wrapped()
    assert calls["n"] == 3


def test_does_not_retry_non_retryable():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _Fatal("bad request")

    wrapped = retry_with_backoff(fn, max_attempts=5, sleep=lambda _: None)
    with pytest.raises(_Fatal):
        wrapped()
    assert calls["n"] == 1


def test_backoff_respects_base_and_cap_without_jitter():
    sleeps: list[float] = []

    def fn():
        raise _ConnectError("x")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=4,
        base_delay_sec=1.0,
        max_delay_sec=3.0,
        jitter=False,
        sleep=sleeps.append,
    )
    with pytest.raises(_ConnectError):
        wrapped()
    # attempts: 0,1,2 (last has no sleep after) → sleeps after 0,1,2 = 1, 2, min(4,3)=3
    assert sleeps == [1.0, 2.0, 3.0]


def test_jitter_stays_within_half_to_max():
    sleeps: list[float] = []

    def fn():
        raise _ConnectError("x")

    wrapped = retry_with_backoff(
        fn,
        max_attempts=4,
        base_delay_sec=1.0,
        max_delay_sec=3.0,
        jitter=True,
        sleep=sleeps.append,
    )
    with pytest.raises(_ConnectError):
        wrapped()
    # Each sleep must be in [0.5*base*2^n, max_delay_sec]
    # attempt 0: base 1 → range [0.5, 1.5], capped by 3.0
    # attempt 1: base 2 → range [1.0, 3.0]
    # attempt 2: base 4 capped to 3 → range [1.5, 3.0]
    assert 0.5 <= sleeps[0] <= 1.5
    assert 1.0 <= sleeps[1] <= 3.0
    assert 1.5 <= sleeps[2] <= 3.0


def test_max_attempts_one_is_single_call_no_sleep():
    sleeps: list[float] = []
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _ConnectError("x")

    wrapped = retry_with_backoff(
        fn, max_attempts=1, sleep=sleeps.append, jitter=False
    )
    with pytest.raises(_ConnectError):
        wrapped()
    assert calls["n"] == 1
    assert sleeps == []
```

---

## 8. Интеграционный тест в `tests/test_retry.py`

Добавить проверку, что `LocalOllamaLLM` использует retry-обёртку:

```python
def test_local_ollama_llm_retries_transient(monkeypatch):
    import graph

    seq = iter([_ConnectError("x"), _ConnectError("y"), "answer"])

    class FakeLLM:
        def invoke(self, prompt):
            _ = prompt
            val = next(seq)
            if isinstance(val, BaseException):
                raise val
            return val

    llm = graph.LocalOllamaLLM.__new__(graph.LocalOllamaLLM)
    llm._llm = FakeLLM()
    llm._breaker = None
    llm._invoke_with_retry = retry_with_backoff(
        llm._llm.invoke, max_attempts=3, sleep=lambda _: None, jitter=False
    )

    assert llm.invoke("q") == "answer"
```

---

## CONSTRAINTS
- Никаких новых зависимостей в `requirements.txt`.
- `pytest tests/ -v` — **85+ passed** (76 было + 9 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Настройки читаются один раз в `LocalOllamaLLM.__init__`, не при каждом `invoke`.
- Retry применяется **до** передачи в circuit breaker — всё в порядке наслоения.
- При `OLLAMA_RETRY_MAX_ATTEMPTS=1` поведение эквивалентно отсутствию retry
  (одна попытка, без `sleep`).
- `KeyboardInterrupt` / `SystemExit` не ретраятся (имён нет в allowlist).

## DONE WHEN
- [ ] `utils/retry.py` с `retry_with_backoff` и `is_retryable_error`
- [ ] 4 новых env-флага в `Settings`, `.env.example`, README
- [ ] `LocalOllamaLLM.__init__` строит `_invoke_with_retry` один раз
- [ ] `LocalOllamaLLM.invoke` использует retry → breaker (правильный layering)
- [ ] `tests/test_retry.py` — 9 тестов, все проходят
- [ ] `pytest tests/ -v` — 85+ passed
- [ ] `ruff check .` — 0 errors

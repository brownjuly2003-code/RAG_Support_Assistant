# Task 69 — RESILIENCE: Circuit breaker для Ollama

## Goal
Сейчас при зависании или падении Ollama LangGraph-пайплайн просто ждёт таймаута на каждом
узле (`transform_query`, `generate`, `evaluate`, `grade_docs`) — каждый запрос тратит
десятки секунд и забивает пул воркеров. Это прямой провал из `rec.md` §2.2
("Circuit breaker — нет fallback если Ollama зависает, просто ждёт").

Ввести минимальный in-process circuit breaker вокруг `LocalOllamaLLM.invoke`:
после N подряд идущих ошибок — открывать цепь и быстро возвращать `CircuitOpenError`,
который `handle_error` уже умеет маршрутизировать в `route=human` + эскалацию.

Никаких внешних зависимостей (не тащить `pybreaker`) — своя реализация на ~80 строк.

## Files to create
- `utils/circuit_breaker.py` — state machine + декоратор
- `tests/test_circuit_breaker.py` — state transitions + интеграция с `LocalOllamaLLM`

## Files to change
- `config/settings.py` — 3 новых env-флага
- `graph.py` — обернуть `LocalOllamaLLM.invoke`
- `.env.example` — документировать новые переменные
- `README.md` — одна строка в таблице env vars

---

## 1. Settings (`config/settings.py`)

В класс `Settings` рядом с `require_ollama` добавить:

```python
    # --- Circuit breaker (устойчивость к падениям Ollama) ---
    circuit_breaker_enabled: bool = os.getenv(
        "CIRCUIT_BREAKER_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    circuit_breaker_failure_threshold: int = int(
        os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
    )
    circuit_breaker_reset_timeout_sec: float = float(
        os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT_SEC", "30")
    )
```

Дефолты подобраны так, чтобы не ломать dev-разработку (5 ошибок подряд — редкая ситуация).

---

## 2. `utils/circuit_breaker.py`

Трёхсостояточная машина: `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`.

```python
"""Минимальный circuit breaker для защиты LLM-вызовов."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when call is rejected because the circuit is OPEN."""


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker.

    Состояния:
    - CLOSED: вызовы проходят; после `failure_threshold` подряд идущих
      исключений → OPEN.
    - OPEN: все вызовы немедленно падают с `CircuitOpenError`.
      Через `reset_timeout_sec` → HALF_OPEN.
    - HALF_OPEN: пропускаем ровно один пробный вызов;
      успех → CLOSED, ошибка → OPEN.
    """

    failure_threshold: int = 5
    reset_timeout_sec: float = 30.0
    name: str = "ollama"

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self.reset_timeout_sec:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        state = self.state
        if state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is OPEN — fast-failing to avoid cascading latency"
            )
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if (
                self._state == CircuitState.HALF_OPEN
                or self._consecutive_failures >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED

    def reset(self) -> None:
        """Форсированный сброс (только для тестов/админ-эндпоинтов)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0
```

Замечания:
- Никакой внешней зависимости — только stdlib.
- `threading.Lock` достаточен: пайплайн синхронный, FastAPI — threadpool.
- `CircuitOpenError` наследует `RuntimeError`, чтобы попасть в существующий
  `except Exception` в `graph.py::handle_error` без специальной обработки.

---

## 3. Интеграция в `graph.py`

В `LocalOllamaLLM` добавить опциональный breaker и использовать его в `invoke`:

было:
```python
class LocalOllamaLLM:
    """Обёртка над локальной моделью Ollama."""

    def __init__(self, model_name: str = "mistral"):
        from langchain_community.llms import Ollama
        self._llm = Ollama(model=model_name)

    def invoke(self, prompt: str) -> str:
        return self._llm.invoke(prompt)
```

стало:
```python
class LocalOllamaLLM:
    """Обёртка над локальной моделью Ollama."""

    def __init__(self, model_name: str = "mistral", breaker: "CircuitBreaker | None" = None):
        from langchain_community.llms import Ollama
        self._llm = Ollama(model=model_name)
        self._breaker = breaker

    def invoke(self, prompt: str) -> str:
        if self._breaker is None:
            return self._llm.invoke(prompt)
        return self._breaker.call(self._llm.invoke, prompt)
```

Добавить модуль-уровневую фабрику (там же, рядом с `LocalOllamaLLM`):

```python
_default_breaker: "CircuitBreaker | None" = None


def get_default_breaker() -> "CircuitBreaker | None":
    """Глобальный breaker для Ollama. None если отключён в settings."""
    global _default_breaker
    if _default_breaker is not None:
        return _default_breaker
    from config.settings import get_settings
    from utils.circuit_breaker import CircuitBreaker

    s = get_settings()
    if not s.circuit_breaker_enabled:
        return None
    _default_breaker = CircuitBreaker(
        failure_threshold=s.circuit_breaker_failure_threshold,
        reset_timeout_sec=s.circuit_breaker_reset_timeout_sec,
        name="ollama",
    )
    return _default_breaker
```

Найти все места, где создаётся `LocalOllamaLLM(...)` (включая `main.py` и
`graph.py::_build_graph`-образные инициализации), и передавать
`breaker=get_default_breaker()`. **Не обёртывать** вызовы в тестах, где
`LocalOllamaLLM` не используется.

---

## 4. `.env.example`

Добавить блок рядом с `REQUIRE_OLLAMA`:

```
# Circuit breaker для Ollama — быстро отказывать при падении LLM
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RESET_TIMEOUT_SEC=30
```

## 5. `README.md`

В таблицу env vars добавить три строки:

```
| `CIRCUIT_BREAKER_ENABLED` | `true` | circuit breaker вокруг вызовов Ollama |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | подряд идущих ошибок до OPEN |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SEC` | `30` | сек до HALF_OPEN пробы |
```

---

## 6. `tests/test_circuit_breaker.py`

```python
"""Тесты для utils.circuit_breaker."""
import time

import pytest

from utils.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def _boom():
    raise RuntimeError("ollama down")


def _ok():
    return "ok"


def test_initial_state_is_closed():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=0.1)
    assert cb.state == CircuitState.CLOSED


def test_stays_closed_below_threshold():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=0.1)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    assert cb.state == CircuitState.CLOSED


def test_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=0.1)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    assert cb.state == CircuitState.OPEN


def test_open_circuit_fast_fails():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=10)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    # real fn was never called again — CircuitOpenError raised before entry
    calls = []

    def tracker():
        calls.append(1)
        return "x"

    with pytest.raises(CircuitOpenError):
        cb.call(tracker)
    assert calls == []


def test_half_open_after_reset_timeout():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    time.sleep(0.06)
    assert cb.call(_ok) == "ok"
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens_circuit():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=0.05)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    time.sleep(0.06)
    # probe fails
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    assert cb.state == CircuitState.OPEN


def test_success_resets_failure_counter():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_sec=10)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    cb.call(_ok)
    # need another 3 in a row, not 1
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    assert cb.state == CircuitState.CLOSED


def test_reset_clears_state():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_sec=10)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_local_ollama_llm_uses_breaker(monkeypatch):
    """LocalOllamaLLM пропускает вызов через breaker, если он передан."""
    from graph import LocalOllamaLLM

    class FakeLLM:
        def invoke(self, prompt):
            raise RuntimeError("ollama down")

    llm = LocalOllamaLLM.__new__(LocalOllamaLLM)  # bypass Ollama init
    llm._llm = FakeLLM()
    llm._breaker = CircuitBreaker(failure_threshold=2, reset_timeout_sec=10)

    with pytest.raises(RuntimeError):
        llm.invoke("hi")
    with pytest.raises(RuntimeError):
        llm.invoke("hi")
    # next call must be fast-failed
    with pytest.raises(CircuitOpenError):
        llm.invoke("hi")
```

---

## CONSTRAINTS
- Никаких новых зависимостей в `requirements.txt`.
- `pytest tests/ -v` — **75+ passed**, 0 regressions (66 было + 9 новых).
- `ruff check .` — 0 errors.
- При `CIRCUIT_BREAKER_ENABLED=false` поведение идентично текущему
  (`LocalOllamaLLM.invoke` вызывает `self._llm.invoke` напрямую).
- `CircuitOpenError(RuntimeError)` — ловится существующим `handle_error`
  без правок в узлах графа.

## DONE WHEN
- [ ] `utils/circuit_breaker.py` реализован с `CircuitBreaker` и `CircuitOpenError`
- [ ] `LocalOllamaLLM` принимает опциональный `breaker` и использует его в `invoke`
- [ ] `get_default_breaker()` возвращает singleton из settings
- [ ] Все инстанциации `LocalOllamaLLM(...)` в продакшн-коде передают breaker
- [ ] 3 новых env-флага добавлены в `Settings`, `.env.example`, README
- [ ] `tests/test_circuit_breaker.py` — 10 тестов, все проходят
- [ ] `pytest tests/ -v` — 75+ passed, 0 warnings про circuit breaker
- [ ] `ruff check .` — 0 errors

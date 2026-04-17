# Task 73 — OBSERVABILITY: Retry metrics в Prometheus

## Goal
task-72 сделала circuit breaker наблюдаемым. Но **retry остался чёрным ящиком**.

Сценарий, который мы **не увидим** сейчас:
- Ollama флапает с 30% транзитных ошибок (сеть, cold-start, ReadTimeout).
- Retry с 3 попытками восстанавливает 99% из них → breaker **никогда не
  откроется** (все вызовы в итоге успешны).
- Но каждый пользовательский запрос теперь тратит +1-2 секунды на retry-паузы.
- `/api/metrics` latency p95 уползает с 2с до 8с.
- Мы видим симптом («p95 вырос»), но не видим причину («retry работает на
  пределе, Ollama нестабильна»).

Нужно: Prometheus-counter, который трекает каждую попытку retry + итог
(успех с первой, восстановлен ретраем, исчерпан).

Это ≪completes the observability loop≫ поверх task-69/70/71/72.

## Files to change
- `utils/retry.py` — опциональный `on_event` callback
- `monitoring/prometheus.py` — один новый counter + helper
- `graph.py::LocalOllamaLLM.__init__` — подключить Prometheus-хук

## Files to create
- `tests/test_retry_observability.py` — 5 тестов

---

## 1. `utils/retry.py`

Добавить `on_event` параметр. События: `attempt`, `success`, `retry`, `exhausted`.

**Семантика событий** (важно одинаково во всех местах использования):
- `attempt` — каждый вызов `fn(...)`, включая первый. Прямо перед вызовом.
- `success` — после успешного возврата `fn`, один раз на всю цепочку.
- `retry` — после transient-ошибки, если осталась ещё попытка. Перед `sleep`.
- `exhausted` — после последней неудачной попытки, прямо перед `raise`.

**Инварианты:**
- На один вызов `wrapped(...)`:
  - 1..N событий `attempt`.
  - Ровно одно из `success` или `exhausted` в конце.
  - 0..N-1 событий `retry` между ними.

```python
from typing import Literal, Optional

RetryEvent = Literal["attempt", "success", "retry", "exhausted"]
RetryCallback = Callable[[RetryEvent], None]


def retry_with_backoff(
    fn: Callable[..., T],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 5.0,
    jitter: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = is_retryable_error,
    on_event: Optional[RetryCallback] = None,
) -> Callable[..., T]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def _emit(event: RetryEvent) -> None:
        if on_event is None:
            return
        try:
            on_event(event)
        except Exception:
            logger.exception("retry on_event callback raised")

    def wrapped(*args, **kwargs) -> T:
        last_exc: BaseException | None = None
        for attempt in range(max_attempts):
            _emit("attempt")
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                if not is_retryable(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    _emit("exhausted")
                    break
                _emit("retry")
                delay = min(base_delay_sec * (2 ** attempt), max_delay_sec)
                if jitter:
                    delay = min(delay * (0.5 + random.random()), max_delay_sec)
                logger.info(
                    "retry_with_backoff: attempt %d/%d failed (%s); sleeping %.2fs",
                    attempt + 1,
                    max_attempts,
                    type(exc).__name__,
                    delay,
                )
                sleep(delay)
            else:
                _emit("success")
                return result
        raise last_exc  # type: ignore[misc]

    return wrapped
```

**Важно:** `_emit` ловит и логирует исключение колбэка — как и у breaker
в task-72, observability не должна ломать прод.

Non-retryable исключения (ValueError, etc.) вылетают до `_emit("exhausted")` —
и это правильно: `exhausted` по смыслу ≠ «non-retryable ошибка», а «retry
исчерпан». Non-retryable статистика — отдельная история, в эту задачу не входит.

---

## 2. `monitoring/prometheus.py`

Один counter с label:

В `__all__` добавить:

```python
    "OLLAMA_RETRY_EVENTS",
    "record_ollama_retry_event",
```

В `except ImportError`:

```python
    OLLAMA_RETRY_EVENTS = _NoopMetric()
```

В `else`:

```python
    OLLAMA_RETRY_EVENTS = Counter(
        "rag_ollama_retry_events_total",
        "Retry wrapper events around Ollama calls",
        ["event"],
        registry=REGISTRY,
    )
```

Helper:

```python
def record_ollama_retry_event(event: str) -> None:
    """Bump the retry counter. `event` ∈ {attempt, success, retry, exhausted}."""
    OLLAMA_RETRY_EVENTS.labels(event=event).inc()
```

---

## 3. `graph.py::LocalOllamaLLM.__init__`

Передать `on_event` в `retry_with_backoff`:

было:
```python
        self._invoke_with_retry = retry_with_backoff(
            self._llm.invoke,
            max_attempts=getattr(settings, "ollama_retry_max_attempts", 3),
            base_delay_sec=getattr(settings, "ollama_retry_base_delay_sec", 0.5),
            max_delay_sec=getattr(settings, "ollama_retry_max_delay_sec", 5.0),
            jitter=getattr(settings, "ollama_retry_jitter", True),
        )
```

стало:
```python
        def _retry_prom_hook(event: str) -> None:
            try:
                from monitoring.prometheus import record_ollama_retry_event
                record_ollama_retry_event(event)
            except Exception:
                pass  # observability не должна ломать прод

        self._invoke_with_retry = retry_with_backoff(
            self._llm.invoke,
            max_attempts=getattr(settings, "ollama_retry_max_attempts", 3),
            base_delay_sec=getattr(settings, "ollama_retry_base_delay_sec", 0.5),
            max_delay_sec=getattr(settings, "ollama_retry_max_delay_sec", 5.0),
            jitter=getattr(settings, "ollama_retry_jitter", True),
            on_event=_retry_prom_hook,
        )
```

---

## 4. `tests/test_retry_observability.py`

```python
"""Тесты наблюдаемости retry: on_event колбэк + Prometheus hook."""
from __future__ import annotations

import pytest

from utils.retry import retry_with_backoff


class _ConnectError(Exception):
    """Transient — имя в allowlist."""


class _Fatal(Exception):
    """Non-retryable."""


def test_success_first_try_emits_attempt_and_success():
    events: list[str] = []

    def fn():
        return "ok"

    wrapped = retry_with_backoff(
        fn, max_attempts=3, sleep=lambda _: None, on_event=events.append
    )
    assert wrapped() == "ok"
    assert events == ["attempt", "success"]


def test_recovered_after_retries_emits_retry_sequence():
    seq = iter([_ConnectError("x"), _ConnectError("y"), "ok"])
    events: list[str] = []

    def fn():
        val = next(seq)
        if isinstance(val, BaseException):
            raise val
        return val

    wrapped = retry_with_backoff(
        fn, max_attempts=3, sleep=lambda _: None, on_event=events.append
    )
    assert wrapped() == "ok"
    # attempt → retry → attempt → retry → attempt → success
    assert events == ["attempt", "retry", "attempt", "retry", "attempt", "success"]


def test_exhausted_emits_final_event():
    events: list[str] = []

    def fn():
        raise _ConnectError("nope")

    wrapped = retry_with_backoff(
        fn, max_attempts=3, sleep=lambda _: None, on_event=events.append
    )
    with pytest.raises(_ConnectError):
        wrapped()
    # attempt → retry → attempt → retry → attempt → exhausted
    assert events == ["attempt", "retry", "attempt", "retry", "attempt", "exhausted"]
    assert events.count("success") == 0


def test_non_retryable_skips_exhausted_event():
    events: list[str] = []

    def fn():
        raise _Fatal("bad")

    wrapped = retry_with_backoff(
        fn, max_attempts=5, sleep=lambda _: None, on_event=events.append
    )
    with pytest.raises(_Fatal):
        wrapped()
    # single attempt, no retry/exhausted — non-retryable не идёт через retry-логику
    assert events == ["attempt"]


def test_callback_exception_does_not_break_retry():
    def bad_hook(event):
        raise ValueError("hook failed")

    def fn():
        return "ok"

    wrapped = retry_with_backoff(
        fn, max_attempts=3, sleep=lambda _: None, on_event=bad_hook
    )
    # должно вернуть "ok", несмотря на падающий колбэк
    assert wrapped() == "ok"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **98+ passed** (93 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `on_event` никогда не ломает retry — исключение в колбэке логируется через
  `logger.exception`, но не пробрасывается (покрыто тестом
  `test_callback_exception_does_not_break_retry`).
- Существующие тесты `test_retry.py` должны продолжать работать без изменений
  (новый параметр `on_event` имеет `None` дефолт).

## DONE WHEN
- [ ] `retry_with_backoff` принимает `on_event: Optional[Callable[[str], None]]`
- [ ] События `attempt`, `success`, `retry`, `exhausted` генерируются согласно
      инвариантам (1+ attempt, ровно один финальный, retry между attempt'ами)
- [ ] `monitoring/prometheus.py` экспортирует `OLLAMA_RETRY_EVENTS` +
      `record_ollama_retry_event`
- [ ] `LocalOllamaLLM.__init__` подключает Prometheus-хук через `on_event`
- [ ] `tests/test_retry_observability.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 98+ passed
- [ ] `ruff check .` — 0 errors
- [ ] Ручная проверка: `curl /api/metrics | grep rag_ollama_retry_events_total` —
      строка присутствует после первого `/api/ask`

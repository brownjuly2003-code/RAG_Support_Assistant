# Task 72 — OBSERVABILITY: Circuit breaker state в Prometheus + /api/health

## Goal
task-69/70/71 замкнули resilience-цепочку, но она пока **невидима для ops**.
Если breaker откроется ночью — узнаем только по жалобам пользователей в
эскалациях (route=human), и только если кто-то смотрит Bitrix. Нужно:

1. **Prometheus gauge** `rag_circuit_breaker_state{name}` — 0/1/2 для
   CLOSED/HALF_OPEN/OPEN. Можно строить графики + alert в Grafana/Alertmanager.
2. **Prometheus counter** `rag_circuit_breaker_transitions_total{name, to_state}` —
   считать переходы (пригодится для RCA «когда именно открылся breaker сегодня»).
3. **Поле `circuit_breakers` в `/api/health`** — снапшот состояний всех
   зарегистрированных breaker'ов. Не влияет на overall status (Ollama-probe
   уже покрывает этот сигнал); чисто диагностический payload.

Без этого task-69 — «чёрный ящик, который иногда глотает запросы».

## Files to change
- `utils/circuit_breaker.py` — optional `on_state_change` callback + публичный
  `snapshot()`
- `monitoring/prometheus.py` — два новых metric'а
- `graph.py::get_default_breaker()` — подключить Prometheus-хук
- `api/app.py::health_check` — добавить breaker'ы в ответ
- `api/app.py` — модель `HealthResponse` (или как она сейчас называется)
  с новым опциональным полем

## Files to create
- `tests/test_circuit_breaker_observability.py` — 5 тестов

---

## 1. `utils/circuit_breaker.py`

Добавить колбэк и снапшот. **Важно:** колбэк вызывается вне lock, чтобы
исключение в пользовательском коде не заклинило breaker.

```python
from typing import Callable, Optional

StateChangeCallback = Callable[[str, CircuitState, CircuitState], None]
# args: (breaker_name, from_state, to_state)


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout_sec: float = 30.0
    name: str = "ollama"
    on_state_change: Optional[StateChangeCallback] = None

    # ... существующие поля ...

    def snapshot(self) -> dict:
        """Thread-safe снапшот текущего состояния для /api/health."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "opened_at_monotonic": self._opened_at if self._opened_at else None,
            }
```

Во всех местах, где меняется `self._state`, после выхода из lock вызывать
колбэк с `(self.name, old_state, new_state)`.

Логика патча (псевдо):

```python
def call(self, fn, *args, **kwargs):
    with self._lock:
        old_state = self._state
        # ... существующая логика проверки OPEN/HALF_OPEN ...
        new_state = self._state
    self._emit_state_change(old_state, new_state)
    # ... try/except вокруг fn ...


def _record_failure(self) -> None:
    with self._lock:
        old_state = self._state
        # ... существующая логика ...
        new_state = self._state
    self._emit_state_change(old_state, new_state)


def _record_success(self) -> None:
    with self._lock:
        old_state = self._state
        # ... существующая логика ...
        new_state = self._state
    self._emit_state_change(old_state, new_state)


def _emit_state_change(self, old: CircuitState, new: CircuitState) -> None:
    if old == new or self.on_state_change is None:
        return
    try:
        self.on_state_change(self.name, old, new)
    except Exception:
        # Никогда не даём пользовательскому колбэку сломать breaker.
        logger = logging.getLogger(__name__)
        logger.exception("on_state_change callback raised")
```

Добавить `import logging` в файл.

**Ключевые инварианты:**
- Колбэк зовётся **только** при `old != new`.
- Колбэк зовётся **вне** `self._lock` — deadlock-safe.
- Исключение в колбэке логируется, но не пробрасывается.

---

## 2. `monitoring/prometheus.py`

Расширить `__all__` и добавить два метрик'а:

```python
__all__ = [
    "ACTIVE_SESSIONS",
    "CIRCUIT_BREAKER_STATE",
    "CIRCUIT_BREAKER_TRANSITIONS",
    "CONTENT_TYPE_LATEST",
    "ESCALATION_TOTAL",
    "FEEDBACK_COUNT",
    "PROMETHEUS_AVAILABLE",
    "QUALITY_SCORE",
    "REGISTRY",
    "REQUEST_COUNT",
    "REQUEST_DURATION",
    "VECTOR_STORE_DOCS",
    "generate_latest",
]
```

В `except ImportError` блоке:

```python
    CIRCUIT_BREAKER_STATE = _NoopMetric()
    CIRCUIT_BREAKER_TRANSITIONS = _NoopMetric()
```

В `else` (после `VECTOR_STORE_DOCS`):

```python
    CIRCUIT_BREAKER_STATE = Gauge(
        "rag_circuit_breaker_state",
        "Current circuit breaker state: 0=closed, 1=half_open, 2=open",
        ["name"],
        registry=REGISTRY,
    )

    CIRCUIT_BREAKER_TRANSITIONS = Counter(
        "rag_circuit_breaker_transitions_total",
        "Total circuit breaker state transitions",
        ["name", "to_state"],
        registry=REGISTRY,
    )
```

Добавить helper в этом же файле:

```python
_STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def record_circuit_breaker_change(name: str, from_state: str, to_state: str) -> None:
    """Обновить Prometheus-метрики при смене состояния breaker'а."""
    CIRCUIT_BREAKER_STATE.labels(name=name).set(_STATE_VALUE.get(to_state, 0))
    CIRCUIT_BREAKER_TRANSITIONS.labels(name=name, to_state=to_state).inc()
```

Экспортировать в `__all__`.

---

## 3. `graph.py::get_default_breaker()`

Подключить хук при создании breaker'а:

было:
```python
    _default_breaker = CircuitBreaker(
        failure_threshold=getattr(settings, "circuit_breaker_failure_threshold", 5),
        reset_timeout_sec=getattr(settings, "circuit_breaker_reset_timeout_sec", 30.0),
        name="ollama",
    )
```

стало:
```python
    def _prom_hook(name: str, old_state, new_state) -> None:
        try:
            from monitoring.prometheus import record_circuit_breaker_change
            record_circuit_breaker_change(name, old_state.value, new_state.value)
        except Exception:
            pass  # обсервабилити не должна ломать прод

    _default_breaker = CircuitBreaker(
        failure_threshold=getattr(settings, "circuit_breaker_failure_threshold", 5),
        reset_timeout_sec=getattr(settings, "circuit_breaker_reset_timeout_sec", 30.0),
        name="ollama",
        on_state_change=_prom_hook,
    )
    # Инициализировать gauge в CLOSED (0), чтобы метрика появилась сразу
    try:
        from monitoring.prometheus import record_circuit_breaker_change
        record_circuit_breaker_change("ollama", "closed", "closed")
    except Exception:
        pass
```

Замечание: `pass`-ветка намеренная — если prometheus_client не установлен,
`_NoopMetric` всё равно отработает, но защищаемся от любых неожиданностей
в импорте.

---

## 4. `api/app.py::health_check`

В ответ `/api/health` добавить массив breaker'ов. Не меняем overall status.

Найти `HealthResponse` (или как называется Pydantic-модель; искать в `api/app.py`
и рядом). Добавить поле:

```python
class HealthResponse(BaseModel):
    # ... существующие поля ...
    circuit_breakers: list[dict] = Field(default_factory=list)
```

В `health_check()` перед `return JSONResponse(...)`:

```python
    from graph import get_default_breaker
    breakers_snap: list[dict] = []
    breaker = get_default_breaker()
    if breaker is not None:
        breakers_snap.append(breaker.snapshot())

    response = HealthResponse(
        # ... существующие поля ...
        circuit_breakers=breakers_snap,
    )
```

Если breaker disabled в settings — массив пустой, что ок.

---

## 5. `tests/test_circuit_breaker_observability.py`

```python
"""Тесты наблюдаемости circuit breaker: колбэки + /api/health + Prometheus hook."""
from __future__ import annotations

import pytest

from utils.circuit_breaker import CircuitBreaker, CircuitState


def test_on_state_change_fires_on_open():
    events: list[tuple] = []

    def hook(name, old, new):
        events.append((name, old, new))

    cb = CircuitBreaker(failure_threshold=2, reset_timeout_sec=10, on_state_change=hook)

    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert events == []  # still CLOSED after 1 failure

    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    # 2nd failure → CLOSED → OPEN
    assert events == [("ollama", CircuitState.CLOSED, CircuitState.OPEN)]


def test_on_state_change_fires_on_close_after_success():
    events: list[tuple] = []

    def hook(name, old, new):
        events.append((name, old, new))

    cb = CircuitBreaker(
        failure_threshold=1, reset_timeout_sec=0.01, on_state_change=hook
    )

    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    import time
    time.sleep(0.02)

    assert cb.call(lambda: "ok") == "ok"
    # events should include: CLOSED→OPEN, then OPEN/HALF_OPEN→CLOSED
    to_states = [e[2] for e in events]
    assert CircuitState.OPEN in to_states
    assert CircuitState.CLOSED in to_states[-2:]


def test_callback_exception_does_not_break_breaker():
    def bad_hook(*args, **kwargs):
        raise ValueError("hook failed")

    cb = CircuitBreaker(
        failure_threshold=1, reset_timeout_sec=10, on_state_change=bad_hook
    )

    # callback raises, but breaker must still transition to OPEN
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cb.state == CircuitState.OPEN


def test_snapshot_returns_state_and_counters():
    cb = CircuitBreaker(failure_threshold=5, reset_timeout_sec=10, name="ollama")

    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

    snap = cb.snapshot()
    assert snap["name"] == "ollama"
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 1


def test_health_endpoint_includes_circuit_breaker_snapshot(client):
    # client fixture — из tests/conftest.py
    resp = client.get("/api/health")
    data = resp.json()
    assert "circuit_breakers" in data
    # если breaker enabled в default settings — там ровно один элемент
    assert isinstance(data["circuit_breakers"], list)
    if data["circuit_breakers"]:
        entry = data["circuit_breakers"][0]
        assert entry["name"] == "ollama"
        assert entry["state"] in ("closed", "half_open", "open")
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **93+ passed** (88 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Колбэк **никогда** не зовётся внутри `self._lock` (проверяется ревью + тестом
  `test_callback_exception_does_not_break_breaker`).
- Prometheus-хук не должен импортироваться на top-level `graph.py` — только
  лениво внутри `get_default_breaker()` (иначе импорт graph зависит от
  prometheus_client при тестах без него).
- Если `PROMETHEUS_AVAILABLE=False` — метрики-noop, тесты всё равно проходят.
- Overall status в `/api/health` **не** меняется на основании breaker'а
  (Ollama-probe уже даёт этот сигнал; не дублируем 503).

## DONE WHEN
- [ ] `CircuitBreaker.on_state_change` колбэк поддерживается, зовётся только
      при реальной смене состояния, вне lock
- [ ] `CircuitBreaker.snapshot()` возвращает thread-safe dict
- [ ] `monitoring/prometheus.py` экспортирует `CIRCUIT_BREAKER_STATE`,
      `CIRCUIT_BREAKER_TRANSITIONS`, `record_circuit_breaker_change`
- [ ] `graph.py::get_default_breaker()` регистрирует Prometheus-хук
- [ ] `/api/health` содержит поле `circuit_breakers: list[dict]`
- [ ] `tests/test_circuit_breaker_observability.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 93+ passed
- [ ] `ruff check .` — 0 errors
- [ ] Ручная проверка: `curl /api/metrics | grep rag_circuit_breaker_state` —
      строка присутствует после первого запроса к `/api/ask`

# Task 86 — SECURITY: rate limit + failed-login observability на `/auth/login`

## Goal
Проверил `api/app.py::login` (строка 1463): три security-пробела.

### 1. Нет rate limit на `/auth/login`
```python
@router.post("/auth/login", response_model=TokenResponse)
async def login(...) -> TokenResponse:
```

**Нет** `@limiter.limit(...)`. Остальные endpoint'ы защищены (60/min ask,
10/min upload). Login — самая атакуемая точка:
- **Credential stuffing**: leaked password list → 1000 попыток/секунда
  до угаданного совпадения. Без лимита — никаких препятствий.
- **Password spraying**: одно и то же слабое пароль на миллионе
  username'ов.
- **Brute-force**: даже с bcrypt hash'ем — 10⁴ попыток в минуту даёт
  10⁷ попыток за день на одном пароле.

### 2. Failed logins не попадают в audit
Успешный login → `log_audit(action="login", ...)` (строки 1479, 1497).
Неудачный → `raise HTTPException(401)` и **ничего** не пишется. 
Security investigation «кто пытался взломать нас в 2:47?» — невозможна.

### 3. Нет Prometheus-метрики на failures
Ни одного счётчика. Невозможно заалертиться на spike (>100 failed в 5 мин =
активная атака).

## Решение
1. `@limiter.limit("5/minute")` на `/auth/login` — индустриальный дефолт.
2. Counter `rag_auth_failures_total{reason}` для алертинга.
3. `log_audit(action="login_failed", detail={reason})` с клиентским IP.
4. Alert rule в `monitoring/alert_rules.yml` (дополнение к task-78).

## Files to change
- `api/app.py::login` — rate-limit декоратор, counter-инкременты,
  audit на failure
- `monitoring/prometheus.py` — counter + helper
- `monitoring/alert_rules.yml` — 1 новое правило
- `README.md` — отметить новый rate-limit

## Files to create
- `tests/test_auth_hardening.py` — 5 тестов

---

## 1. `monitoring/prometheus.py`

В `__all__`:
```python
    "AUTH_FAILURES",
    "record_auth_failure",
```

В `except ImportError`:
```python
    AUTH_FAILURES = _NoopMetric()
```

В `else`:
```python
    AUTH_FAILURES = Counter(
        "rag_auth_failures_total",
        "Failed /auth/login attempts",
        ["reason"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_auth_failure(reason: str) -> None:
    """reason ∈ {unknown_user, bad_password, bad_request}."""
    AUTH_FAILURES.labels(reason=reason).inc()
```

---

## 2. `api/app.py::login`

было:
```python
@router.post("/auth/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT tokens."""
    from auth.jwt_handler import create_access_token, create_refresh_token
    ...
```

стало (полная функция):
```python
@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT tokens.

    Rate-limited at 5/minute per client IP to deter credential stuffing
    and brute-force attempts. All failed attempts are recorded in
    audit_log and the rag_auth_failures_total counter.
    """
    from auth.jwt_handler import create_access_token, create_refresh_token

    import os

    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    client_ip = request.client.host if request.client else None

    async def _record_failure(reason: str) -> None:
        try:
            prometheus_metrics.record_auth_failure(reason)
        except Exception:
            pass
        await log_audit(
            actor=body.username or "<anonymous>",
            action="login_failed",
            resource="auth",
            detail={"reason": reason},
            ip_address=client_ip,
        )

    if not admin_hash:
        # Dev-режим: только admin/admin
        if body.username == "admin" and body.password == "admin":
            response = TokenResponse(
                access_token=create_access_token("admin", "admin"),
                refresh_token=create_refresh_token("admin", "admin"),
            )
            await log_audit(
                actor=body.username,
                action="login",
                resource="auth",
                ip_address=client_ip,
            )
            return response
        await _record_failure("bad_credentials_dev")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from passlib.hash import bcrypt

    if body.username != admin_user:
        await _record_failure("unknown_user")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.verify(body.password, admin_hash):
        await _record_failure("bad_password")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = TokenResponse(
        access_token=create_access_token(body.username, "admin"),
        refresh_token=create_refresh_token(body.username, "admin"),
    )
    await log_audit(
        actor=body.username,
        action="login",
        resource="auth",
        ip_address=client_ip,
    )
    return response
```

**Инварианты:**
- **Detail в ответе одинаковый** для всех failures (`"Invalid credentials"`)
  — не намекаем атакующему, username валидный или нет (user-enum leak).
  **Reason** в audit/metric различный — он нам нужен для investigation.
- `_record_failure` — локальная helper-функция, чтобы не повторять блок
  из 3 строк трижды.
- Exception из prometheus-хука съедается (как везде в проекте) —
  observability не ломает 401.

---

## 3. `monitoring/alert_rules.yml`

Добавить в группу `rag-resilience` (task-78):

```yaml
      - alert: AuthFailureSpike
        expr: |
          sum(rate(rag_auth_failures_total[5m])) > 1
        for: 5m
        labels:
          severity: warning
          component: auth
        annotations:
          summary: ">60 failed login attempts per 5-minute window"
          description: |
            rag_auth_failures_total is averaging >1/sec over 5 minutes.
            With a 5/min per-IP rate limit this means multiple IPs are
            hammering /auth/login — likely a credential-stuffing campaign.
            Check audit_log for action="login_failed" and consider
            temporary IP-level blocks at the edge.
```

После обновления — тест `test_alert_rules.py::test_expressions_reference_declared_metrics`
увидит новую метрику и должен продолжить проходить.

---

## 4. `README.md`

В Rate limits секции:
```
Rate limits: 60 req/min на /api/ask, 10 req/min на /api/upload,
**5 req/min на /api/auth/login** (per client IP, anti-brute-force).
```

---

## 5. `tests/test_auth_hardening.py`

```python
"""Тесты rate-limit + observability на /auth/login."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


def test_failed_login_returns_401_and_records_audit(
    monkeypatch, client: TestClient
):
    """Неправильный пароль → 401, audit_log пишется с action=login_failed."""
    audit_calls: list[dict] = []

    async def _fake_log_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"

    failed = [c for c in audit_calls if c.get("action") == "login_failed"]
    assert failed, f"no login_failed audit entry, got: {audit_calls}"


def test_failure_detail_is_generic(monkeypatch, client: TestClient):
    """Unknown user и bad password возвращают одинаковый detail."""
    async def _noop(**kwargs):
        pass

    monkeypatch.setattr("api.app.log_audit", _noop)

    resp_unknown = client.post(
        "/api/auth/login", json={"username": "nobody", "password": "x"}
    )
    resp_bad = client.post(
        "/api/auth/login", json={"username": "admin", "password": "x"}
    )
    assert resp_unknown.status_code == 401
    assert resp_bad.status_code == 401
    assert resp_unknown.json()["detail"] == resp_bad.json()["detail"]


def test_auth_failure_counter_increments(monkeypatch, client: TestClient):
    from monitoring.prometheus import AUTH_FAILURES, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _sum() -> float:
        total = 0.0
        for m in AUTH_FAILURES.collect():
            for s in m.samples:
                if s.name.endswith("_total"):
                    total += s.value
        return total

    async def _noop(**kwargs):
        pass

    monkeypatch.setattr("api.app.log_audit", _noop)

    before = _sum()
    client.post(
        "/api/auth/login", json={"username": "admin", "password": "x"}
    )
    after = _sum()
    assert after > before


def test_rate_limit_kicks_after_5_attempts(monkeypatch, client: TestClient):
    """6-я попытка за минуту → 429."""
    async def _noop(**kwargs):
        pass

    monkeypatch.setattr("api.app.log_audit", _noop)

    last_status = None
    for _ in range(8):
        resp = client.post(
            "/api/auth/login",
            json={"username": "attacker", "password": "x"},
        )
        last_status = resp.status_code
        if last_status == 429:
            break

    assert last_status == 429


def test_successful_login_does_not_increment_failure_counter(
    monkeypatch, client: TestClient
):
    from monitoring.prometheus import AUTH_FAILURES, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _sum() -> float:
        total = 0.0
        for m in AUTH_FAILURES.collect():
            for s in m.samples:
                if s.name.endswith("_total"):
                    total += s.value
        return total

    async def _noop(**kwargs):
        pass

    monkeypatch.setattr("api.app.log_audit", _noop)

    before = _sum()
    # Dev-mode admin/admin (ADMIN_PASSWORD_HASH не установлен в тесте)
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    after = _sum()
    assert after == before, "counter changed on successful login"
```

**Замечания:**
- `test_rate_limit_kicks_after_5_attempts` — slowapi хранит счётчик в памяти,
  он не сбрасывается между тестами автоматически. Если тесты начинают
  флапать — добавить в `conftest.py` fixture, который ресетит лимитер,
  либо использовать уникальный IP через `monkeypatch.setattr` на
  `get_remote_address`.
- В тестах `ADMIN_PASSWORD_HASH` **не** установлен — попадаем в dev-ветку
  где валидно только admin/admin. Это соответствует `test_login_dev_mode`
  в существующем `test_jwt_auth.py`.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **151+ passed** (146 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Detail в 401 **одинаковый** для всех failures (no user-enum leak).
- Exception из prometheus не ломает 401-handler.
- Успешный login **не** инкрементит failure-counter (покрыто тестом).
- `test_alert_rules.py::test_expressions_reference_declared_metrics`
  должен по-прежнему проходить с новой метрикой.

## DONE WHEN
- [ ] `@limiter.limit("5/minute")` на `/auth/login`
- [ ] `rag_auth_failures_total{reason}` counter и `record_auth_failure`
      экспортируются
- [ ] Все три failure-ветки (unknown_user, bad_password, dev bad creds)
      пишут audit `action="login_failed"` и инкрементят counter
- [ ] Detail в 401 — `"Invalid credentials"` во всех failure-ветках
- [ ] `AuthFailureSpike` alert rule в `monitoring/alert_rules.yml`
- [ ] README упоминает 5/min limit
- [ ] `tests/test_auth_hardening.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 151+ passed, включая обновлённый
      `test_alert_rules.py`
- [ ] `ruff check .` — 0 errors

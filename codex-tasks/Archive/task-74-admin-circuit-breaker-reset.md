# Task 74 — ADMIN: Endpoint для ручного сброса circuit breaker

## Goal
После task-69/72 мы **видим** когда breaker открылся (Prometheus gauge +
`/api/health`), но **не можем повлиять** на него быстрее, чем через
`reset_timeout_sec` (30с). Реальные сценарии:

- Ollama упала на 5 минут, breaker открылся. Мы вручную перезапустили Ollama
  и точно знаем что она жива. Но breaker всё ещё OPEN 30с — пользователи
  продолжают видеть эскалации на human.
- Плановое обслуживание модели: мы хотим прогреть breaker сразу после
  деплоя новой модели, а не ждать «естественной» HALF_OPEN-пробы.

Нужен административный рычаг: `POST /api/admin/circuit-breaker/reset`,
который зовёт `breaker.reset()` (уже есть в task-69) и пишет audit-log.

**Это НЕ дублирование `/api/health`.** health читает состояние, admin —
его меняет. RBAC обязателен (только admin), audit обязателен.

## Files to change
- `api/app.py` — новый endpoint
- `tests/test_admin_endpoints.py` — если уже существует, дополнить; иначе создать

## Files to create
- `tests/test_admin_endpoints.py` (если не существует) — 4 теста

---

## 1. Endpoint в `api/app.py`

Разместить рядом с другими RBAC-эндпоинтами (где есть `Depends(require_role("admin"))`).

Паттерн в проекте уже устоявшийся (`auth.dependencies.require_role` +
`db.audit.log_audit`):

```python
@app.post("/api/admin/circuit-breaker/reset", response_model=None)
async def admin_reset_circuit_breaker(
    request: Request,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Форсированно сбрасывает circuit breaker в CLOSED.

    Используется, когда ops знает, что upstream восстановлен, и хочет
    быстрее прогреть breaker, чем через reset_timeout_sec.
    """
    from db.audit import log_audit
    from graph import get_default_breaker

    breaker = get_default_breaker()
    if breaker is None:
        return JSONResponse(
            status_code=409,
            content={
                "status": "disabled",
                "detail": "circuit breaker disabled via CIRCUIT_BREAKER_ENABLED=false",
            },
        )

    previous = breaker.snapshot()
    breaker.reset()
    new_state = breaker.snapshot()

    await log_audit(
        actor=_user["sub"],
        action="circuit_breaker_reset",
        resource=f"breaker/{breaker.name}",
        detail={
            "previous_state": previous["state"],
            "previous_consecutive_failures": previous["consecutive_failures"],
        },
        ip_address=_client_ip(request) if "_client_ip" in globals() else None,
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "reset",
            "breaker": breaker.name,
            "previous": previous,
            "current": new_state,
        },
    )
```

**Замечание про `_client_ip`:** в `api/app.py` уже есть хелпер
`_client_ip(request)` (используется в других audit-вызовах, найти и применить
его). Если хелпер называется иначе — использовать существующий паттерн
получения IP из `request`.

---

## 2. `tests/test_admin_endpoints.py`

Если файл уже существует (после task-47 RBAC), дополнить. Если нет — создать.

```python
"""Тесты административных endpoint'ов: RBAC + audit."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _admin_token(client: TestClient) -> str:
    """Login as admin, вернуть Bearer token."""
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _viewer_token(client: TestClient) -> str:
    """Если в проекте есть dev-viewer, использовать его; иначе создать.

    Мы знаем из auth/dependencies.py, что без API_KEY и без Bearer токена
    возвращается {"role": "admin"} как anonymous — это не то, что нужно.
    Поэтому тут используем низкопривилегированный access-token, созданный
    напрямую через create_access_token (как в других RBAC-тестах).
    """
    from auth.jwt_handler import create_access_token
    return create_access_token("viewer-user", "viewer")


def test_admin_can_reset_circuit_breaker(client: TestClient) -> None:
    # Принудительно открыть breaker через serverside manipulation
    import graph
    graph._default_breaker = None  # сбросить singleton
    breaker = graph.get_default_breaker()
    if breaker is None:
        # disabled — отдельный тест ниже
        import pytest
        pytest.skip("breaker disabled in this env")
    # открыть breaker вручную
    for _ in range(breaker.failure_threshold):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        except RuntimeError:
            pass
    assert breaker.snapshot()["state"] == "open"

    token = _admin_token(client)
    resp = client.post(
        "/api/admin/circuit-breaker/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reset"
    assert data["previous"]["state"] == "open"
    assert data["current"]["state"] == "closed"

    # breaker действительно сброшен
    assert breaker.snapshot()["state"] == "closed"


def test_viewer_is_forbidden(client: TestClient) -> None:
    token = _viewer_token(client)
    resp = client.post(
        "/api/admin/circuit-breaker/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_unauthenticated_is_rejected(client: TestClient) -> None:
    # без токена; если в env не выставлен API_KEY — conftest выдаёт anonymous=admin,
    # поэтому нужна изоляция. Тест проверяет поведение с явно выставленным API_KEY.
    import os
    os.environ["API_KEY"] = "some-secret-to-force-auth"
    try:
        import config.settings as _s
        _s._settings = None
        from api.app import app
        c = TestClient(app)
        resp = c.post("/api/admin/circuit-breaker/reset")
        assert resp.status_code in (401, 403)
    finally:
        os.environ.pop("API_KEY", None)
        import config.settings as _s
        _s._settings = None


def test_reset_returns_409_when_breaker_disabled(monkeypatch, client: TestClient) -> None:
    monkeypatch.setenv("CIRCUIT_BREAKER_ENABLED", "false")
    import config.settings as _s
    _s._settings = None
    import graph
    graph._default_breaker = None

    token = _admin_token(client)
    resp = client.post(
        "/api/admin/circuit-breaker/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.json()["status"] == "disabled"
```

**Замечание:** тест `test_admin_can_reset_circuit_breaker` должен запускаться
в окружении, где breaker enabled (default). Если в conftest он принудительно
отключён — тест skip'ается, это ок.

---

## 3. Audit-запись

Обязательно. После выполнения reset пишется:

```
actor=<jwt.sub>
action="circuit_breaker_reset"
resource="breaker/ollama"
detail={"previous_state": "open|half_open|closed", "previous_consecutive_failures": N}
ip_address=<client-ip>
```

Тест на audit-запись **не** добавляем (это tested отдельно в
`test_audit_log.py` из task-62), но делаем одну assert-проверку, что
`log_audit` вызвался — через monkeypatch, если хочется ужесточить. В этой
задаче пропускаем, чтобы не перегружать.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **102+ passed** (98 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Endpoint использует **существующий** `require_role("admin")` из
  `auth.dependencies` — не создавать свою проверку.
- Endpoint использует **существующий** `log_audit` из `db.audit` — не дублировать.
- `breaker.reset()` уже существует (task-69), не переписывать.
- Отклик: 200 с телом `{status, breaker, previous, current}`; 409 если
  breaker disabled; 401/403 если не админ.

## DONE WHEN
- [ ] `POST /api/admin/circuit-breaker/reset` существует в `api/app.py`
- [ ] Защищён `Depends(require_role("admin"))`
- [ ] Возвращает 200 с `{status: "reset", breaker, previous, current}` при успехе
- [ ] Возвращает 409 с `{status: "disabled", detail}` если breaker выключен
- [ ] Возвращает 401 без auth и 403 для не-admin ролей
- [ ] Пишет audit-запись через `log_audit(...)` с корректным actor/action/resource/detail
- [ ] `tests/test_admin_endpoints.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 102+ passed
- [ ] `ruff check .` — 0 errors

# Task 88 — SECURITY: Request body size limits (DoS protection)

## Goal
Проверил `api/app.py` — Pydantic ограничивает **поля** (`question max_length=2000`
и т.д.), но:

1. **`/api/upload` не имеет file-size limit.** `UploadFile` FastAPI стримит
   по частям, но без явной проверки размера можно послать 10GB файл →
   диск наполнится, `SpooledTemporaryFile` выплеснется в `/tmp`, worker
   встанет.

2. **Нет global body-size middleware.** Злой клиент POST'ит 100MB JSON на
   `/api/ask`:
   - Pydantic в итоге отклонит на `question max_length=2000`.
   - **Но** всё тело уже прочитано в память ещё до валидации. При 16 worker'ах
     × 100MB = 1.6GB RSS от одного атакующего.
   - Memory pressure → OOM-kill → рестарт всего процесса.

## Решение
Два комплементарных лимита:

1. **Global Content-Length middleware** — отклоняет ранее всего
   `Content-Length > MAX_REQUEST_BODY_SIZE_BYTES` (default 1 MiB) через
   `413 Request Entity Too Large`. Читаем header, не body → O(1).
2. **Upload-specific limit** — в `/api/upload` проверяем фактический
   размер прочитанных байт (header можно подделать или не прислать),
   `MAX_UPLOAD_SIZE_BYTES` (default 50 MiB).
3. Counter `rag_body_size_rejections_total{reason}` для наблюдения
   (возможные DoS-atari).

**Разные лимиты по причине:** 1 MiB на `/api/ask` с лихвой хватает
(`question max=2000` символов), но upload документов — совсем другая
история (50 MiB PDF — нормально для корпоративных мануалов).

## Files to change
- `config/settings.py` — 2 env-флага
- `api/app.py` — middleware + upload check + counter
- `monitoring/prometheus.py` — counter + helper
- `.env.example`, `README.md`

## Files to create
- `tests/test_body_size_limits.py` — 5 тестов

---

## 1. `config/settings.py`

Рядом с `cors_max_age_sec`:

```python
    max_request_body_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1 * 1024 * 1024)))  # 1 MiB
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  # 50 MiB
    )
```

---

## 2. `monitoring/prometheus.py`

В `__all__`:
```python
    "BODY_SIZE_REJECTIONS",
    "record_body_size_rejection",
```

В `except ImportError`:
```python
    BODY_SIZE_REJECTIONS = _NoopMetric()
```

В `else`:
```python
    BODY_SIZE_REJECTIONS = Counter(
        "rag_body_size_rejections_total",
        "Requests rejected due to body size limits",
        ["reason"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_body_size_rejection(reason: str) -> None:
    """reason ∈ {content_length_too_large, upload_too_large}."""
    BODY_SIZE_REJECTIONS.labels(reason=reason).inc()
```

---

## 3. `api/app.py` — middleware

Middleware должен стоять **рано** — до pydantic-валидации, до роутинга.
Зарегистрировать **последним** (stack в обратном порядке, поэтому
последний зарегистрированный = первый вызванный).

Наиболее безопасно — новый middleware декоратором после `_request_id`:

```python
@app.middleware("http")
async def _body_size_limit(request: Request, call_next: Any) -> Any:
    """Отклоняет запросы с Content-Length > max_request_body_bytes.

    Работает только для endpoint'ов **кроме** /api/upload — upload имеет
    свой лимит ≈ 50 MiB, а общий лимит для /api/ask и т.п. — 1 MiB.
    """
    path = request.url.path

    # Upload-эндпоинт обрабатывает свой лимит отдельно
    if path == "/api/upload":
        return await call_next(request)

    settings = get_settings()
    limit = getattr(settings, "max_request_body_bytes", 1024 * 1024)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            size = int(content_length)
        except ValueError:
            size = -1
        if size > limit:
            try:
                from monitoring.prometheus import record_body_size_rejection
                record_body_size_rejection("content_length_too_large")
            except Exception:
                pass
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large ({size} bytes, limit {limit})"
                },
            )

    return await call_next(request)
```

**Инварианты:**
- `/api/upload` исключён — он сам накладывает свой лимит. Если мы
  применим 1 MiB ко всем, upload 50 MiB PDF'ов сломается.
- `Content-Length` — header, клиент может не прислать. Для chunked
  transfer-encoding length неизвестен. Для таких случаев upload endpoint
  считает байты реальные (§4).
- 413 — RFC-корректный код («Payload Too Large»).

---

## 4. `api/app.py::upload_document` — проверка фактического размера

Найти endpoint `/api/upload` и добавить проверку после получения
`UploadFile`:

```python
@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _user: dict = Depends(require_role("agent", "admin")),
) -> UploadResponse:
    # ... существующая валидация filename / extension ...

    settings = get_settings()
    upload_limit = getattr(settings, "max_upload_bytes", 50 * 1024 * 1024)

    # Читаем стримом, чтобы поймать большие файлы до того, как всё
    # окажется в памяти/на диске.
    content = bytearray()
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > upload_limit:
            try:
                from monitoring.prometheus import record_body_size_rejection
                record_body_size_rejection("upload_too_large")
            except Exception:
                pass
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds limit of {upload_limit} bytes",
            )

    # Дальше — существующая логика, но вместо file.read() передаём bytes(content)
    # ... use bytes(content) where file content is needed ...
```

**Замечание:** если существующий код делает `content = await file.read()` —
заменить этот single read на chunked read выше. Все последующие
использования `content` (сохранение на диск, ingestion) — байты
идентичные, просто накопленные постепенно.

Если код вызывает `file.read()` несколько раз — `file.seek(0)` между
вызовами, иначе второй read вернёт пусто. С bytearray накопленным
напрямую в `content` — seek не нужен.

---

## 5. `.env.example`

```
# Макс. размер тела запроса (байт) — anti-DoS. Default 1 MiB.
# /api/upload имеет свой отдельный лимит MAX_UPLOAD_BYTES.
MAX_REQUEST_BODY_BYTES=1048576
# Макс. размер загружаемого файла (байт). Default 50 MiB.
MAX_UPLOAD_BYTES=52428800
```

## 6. `README.md`

В таблицу env vars:
```
| `MAX_REQUEST_BODY_BYTES` | `1048576` | 1 MiB лимит на тело запроса (кроме /api/upload) |
| `MAX_UPLOAD_BYTES` | `52428800` | 50 MiB лимит для /api/upload |
```

---

## 7. `tests/test_body_size_limits.py`

```python
"""Тесты размеров тел запросов: 413, counter, корректные пути."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


def test_large_body_rejected_413(monkeypatch, client: TestClient) -> None:
    """POST /api/ask с Content-Length > limit → 413."""
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1024")  # 1 KiB
    import config.settings as _s
    _s._settings = None

    big_question = "x" * 2000  # ~2KiB JSON-string
    resp = client.post(
        "/api/ask",
        content=(b'{"question":"' + big_question.encode() + b'"}'),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_small_body_passes(mock_pipeline, client: TestClient) -> None:
    """Обычный запрос не должен триггерить 413."""
    resp = client.post("/api/ask", json={"question": "короткий вопрос"})
    assert resp.status_code == 200


def test_upload_rejected_when_too_large(monkeypatch, client: TestClient) -> None:
    """Upload > MAX_UPLOAD_BYTES → 413 от endpoint'а."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "512")
    import config.settings as _s
    _s._settings = None

    from auth.jwt_handler import create_access_token
    token = create_access_token("admin", "admin")

    big_content = b"A" * 2000
    resp = client.post(
        "/api/upload",
        files={"file": ("big.txt", io.BytesIO(big_content), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 413


def test_rejection_counter_increments(monkeypatch, client: TestClient) -> None:
    from monitoring.prometheus import BODY_SIZE_REJECTIONS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _sum() -> float:
        total = 0.0
        for m in BODY_SIZE_REJECTIONS.collect():
            for s in m.samples:
                if s.name.endswith("_total"):
                    total += s.value
        return total

    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "100")
    import config.settings as _s
    _s._settings = None

    before = _sum()
    client.post(
        "/api/ask",
        content=b'{"question":"' + b"x" * 500 + b'"}',
        headers={"Content-Type": "application/json"},
    )
    after = _sum()
    assert after > before


def test_upload_path_bypasses_body_middleware(
    monkeypatch, client: TestClient
) -> None:
    """Middleware не должна ломать /api/upload общим 1 MiB лимитом."""
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "100")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
    import config.settings as _s
    _s._settings = None

    from auth.jwt_handler import create_access_token
    token = create_access_token("admin", "admin")

    # 5 KiB файл — намного больше MAX_REQUEST_BODY_BYTES=100, но в
    # пределах MAX_UPLOAD_BYTES. Должно пройти (или провалиться на
    # реальной логике ingestion'а, но не на 413).
    content = b"hello world\n" * 500
    resp = client.post(
        "/api/upload",
        files={"file": ("small.txt", io.BytesIO(content), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    # НЕ 413 — middleware пропустила upload; дальше endpoint может
    # ответить 200 / 4xx по контент-логике, но именно size-check
    # не сработал
    assert resp.status_code != 413
```

**Замечания:**
- Fixture `client_with_key` не обязателен — отдельные тесты создают свой
  JWT token через `create_access_token`.
- Тест `test_large_body_rejected_413` посылает raw `content=...` вместо
  `json=...`, чтобы самому контролировать `Content-Length` header.
  TestClient считает длину автоматически.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **161+ passed** (156 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Middleware **пропускает** `/api/upload` — иначе 1 MiB лимит сломает
  обычные PDF-документы.
- Upload проверяет **реальный** размер прочитанных байт (не доверяя
  Content-Length header'у).
- Exception из prometheus не ломает 413-handler.

## DONE WHEN
- [ ] `max_request_body_bytes` и `max_upload_bytes` в Settings
- [ ] Middleware отклоняет `Content-Length > max_request_body_bytes`
      для endpoint'ов **кроме** `/api/upload`
- [ ] `/api/upload` проверяет фактический размер и 413 при превышении
- [ ] `rag_body_size_rejections_total{reason}` counter инкрементится
      для обоих reasons
- [ ] `.env.example` и README описывают два env-флага
- [ ] `tests/test_body_size_limits.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 161+ passed
- [ ] `ruff check .` — 0 errors

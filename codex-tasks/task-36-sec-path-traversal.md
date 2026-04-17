# Task 36 — SEC-1: Исправить path traversal в upload

## Goal
`file.filename` из multipart-запроса используется напрямую в пути сохранения.
Атакующий может передать `../../etc/passwd` и перезаписать произвольный файл.
Нужно санитизировать имя файла через `os.path.basename()` + whitelist символов.

## Files to change
- `api/app.py` — строка 772, функция `upload_document`
- `tests/test_upload_security.py` — новый файл

---

## 1. api/app.py

В функции `upload_document`, после проверки расширения (строка ~762), заменить:

было:
```python
    file_path = upload_dir / file.filename
```

стало:
```python
    import re as _re
    safe_name = os.path.basename(file.filename)
    safe_name = _re.sub(r'[^\w\-.]', '_', safe_name)
    if not safe_name or safe_name.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = upload_dir / safe_name
```

Также добавить `import os` в начало файла, если отсутствует (уже есть через `from pathlib import Path`, но `os.path.basename` нужен явно — впрочем, можно использовать `Path(file.filename).name`).

Упрощённый вариант без `import os`:

было:
```python
    file_path = upload_dir / file.filename
```

стало:
```python
    import re as _re
    safe_name = Path(file.filename).name
    safe_name = _re.sub(r'[^\w\-.]', '_', safe_name)
    if not safe_name or safe_name.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = upload_dir / safe_name
```

Далее в ответах `UploadResponse` ниже по функции заменить `file.filename` на `safe_name`:

было:
```python
                    return UploadResponse(
                        status="ok",
                        filename=file.filename,
```

стало:
```python
                    return UploadResponse(
                        status="ok",
                        filename=safe_name,
```

Аналогично для всех остальных `UploadResponse(... filename=file.filename ...)` в этой функции (4 места).

---

## 2. tests/test_upload_security.py (новый)

```python
"""Тесты безопасности upload: path traversal, dot-файлы, спецсимволы."""
import io
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import config.settings as _s
    _s._settings = None
    from api.app import app
    return TestClient(app)


@pytest.mark.parametrize("malicious_name", [
    "../../etc/passwd",
    "../../../windows/system32/config/sam",
    "..\\..\\etc\\passwd",
    ".hidden_file.txt",
    "",
])
def test_upload_rejects_malicious_filenames(client, malicious_name):
    """Path traversal и dot-файлы должны отклоняться с 400."""
    files = {"file": (malicious_name, io.BytesIO(b"test"), "text/plain")}
    resp = client.post("/api/upload", files=files)
    assert resp.status_code == 400


def test_upload_sanitizes_filename(client):
    """Имя с спецсимволами должно быть очищено, не содержать / или \\."""
    files = {"file": ("my file (1).txt", io.BytesIO(b"hello"), "text/plain")}
    resp = client.post("/api/upload", files=files)
    # Не должно быть 400 — файл валидный после санитизации
    assert resp.status_code != 400
```

---

## CONSTRAINTS
- Изменить только `api/app.py` (функция `upload_document`) и новый тест
- Не менять логику индексации — только имя файла
- `pytest tests/ -v` — проходит
- `ruff check api/app.py` — 0 ошибок

## DONE WHEN
- [ ] `Path("../../etc/passwd").name` → `passwd`, но regex дополнительно чистит спецсимволы
- [ ] Filename с `..` не позволяет выйти за пределы upload_dir
- [ ] Dot-файлы (`.hidden`) отклоняются с 400
- [ ] Пустое имя файла → 400
- [ ] Все `UploadResponse` используют `safe_name`, а не `file.filename`
- [ ] `pytest tests/ -v` — проходит

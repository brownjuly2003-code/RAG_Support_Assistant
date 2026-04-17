# Task 65 — CODE-5: Общий conftest.py для тестов

## Goal
Каждый тест-файл переизобретает stub-инфраструктуру (100+ строк бойлерплейта).
Вынести общие fixtures в `tests/conftest.py`.

## Files to create
- `tests/conftest.py`

## Files to change
- Существующие тест-файлы — заменить inline fixtures на conftest imports

---

## tests/conftest.py

```python
"""Shared test fixtures for RAG Support Assistant."""
import os
import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset settings singleton before each test."""
    import config.settings as _s
    _s._settings = None
    yield
    _s._settings = None


@pytest.fixture
def client():
    """FastAPI TestClient without auth."""
    os.environ.pop("API_KEY", None)
    import config.settings as _s
    _s._settings = None
    from api.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def client_with_key(monkeypatch):
    """FastAPI TestClient with API key auth enabled."""
    monkeypatch.setenv("API_KEY", "test-secret-key")
    import config.settings as _s
    _s._settings = None
    from api.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def mock_pipeline(monkeypatch):
    """Mock the RAG pipeline so tests don't need Ollama."""
    mock_result = {
        "answer": "Тестовый ответ",
        "quality_score": 75,
        "route": "auto",
        "sources": [],
        "trace_id": "test-trace-id",
    }
    mock_fn = MagicMock(return_value=mock_result)
    monkeypatch.setattr("api.app._run_qa_pipeline", mock_fn, raising=False)
    return mock_fn


@pytest.fixture
def temp_upload_dir(tmp_path):
    """Temporary upload directory."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return upload_dir
```

---

## Миграция существующих тестов

В каждом существующем тест-файле, если есть inline `client` fixture:

было:
```python
@pytest.fixture
def client():
    import config.settings as _s
    _s._settings = None
    from api.app import app
    return TestClient(app)
```

стало: удалить — conftest предоставит автоматически.

Аналогично для `client_with_key`, `_reset_settings` и подобных.

---

## CONSTRAINTS
- Создать `tests/conftest.py` с общими fixtures
- Обновить существующие тесты — убрать дублирующие fixtures
- `autouse=True` на `_reset_settings` — все тесты получают чистый singleton
- `pytest tests/ -v` — проходит (все существующие тесты)
- Не менять логику тестов — только вынести infrastructure

## DONE WHEN
- [ ] `tests/conftest.py` существует с 4+ fixtures
- [ ] `_reset_settings` autouse — singleton сбрасывается
- [ ] Дублирующие `client` fixtures удалены из тест-файлов
- [ ] `pytest tests/ -v` — все тесты проходят
- [ ] Ни один тест-файл не содержит `_s._settings = None` inline

# Task 49 — ASYNC-1: Celery task queue для document upload

## Goal
Загрузка и индексация документов выполняется синхронно и блокирует API.
Перенести на Celery + Redis: upload возвращает task_id мгновенно,
клиент poll-ит `/api/tasks/{id}` для статуса.

## Dependencies
- task-42 (Redis в docker-compose)
- task-45 (Redis cache layer)

## Files to create
- `tasks/__init__.py`
- `tasks/celery_app.py` — Celery конфигурация
- `tasks/ingest_task.py` — task для индексации документа

## Files to change
- `requirements.txt` — добавить celery
- `api/app.py` — изменить /api/upload, добавить /api/tasks/{id}

---

## 1. requirements.txt

Добави��ь:
```
celery[redis]>=5.3.0
```

---

## 2. tasks/__init__.py

```python
"""Background task queue — Celery + Redis."""
```

---

## 3. tasks/celery_app.py

```python
"""Celery application config."""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rag_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,  # результаты хранятся 1 час
)

# Auto-discover task modules
celery_app.autodiscover_tasks(["tasks"])
```

---

## 4. tasks/ingest_task.py

```python
"""Background task: ingest document into vector store."""
from __future__ import annotations

import logging
from pathlib import Path

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.ingest_document")
def ingest_document(self, file_path: str) -> dict:
    """Загрузить и индексировать документ в vector store.

    Args:
        file_path: путь к сохранённому файлу.

    Returns:
        dict с результатом: status, docs_count, message.
    """
    self.update_state(state="PROCESSING", meta={"step": "loading"})

    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    try:
        from ingestion.loader import DocumentLoader
        loader = DocumentLoader(recursive=False)
        docs = loader.load_documents(str(path.parent))
    except ImportError:
        from loader import DocumentLoader
        loader = DocumentLoader(recursive=False)
        docs = loader.load_documents(str(path.parent))

    if not docs:
        return {"status": "partial", "docs_count": 0, "message": "No text content extracted"}

    self.update_state(state="PROCESSING", meta={"step": "indexing", "docs_count": len(docs)})

    try:
        try:
            from vectordb.manager import build_vector_store, get_embeddings
        except ImportError:
            from manager import build_vector_store, get_embeddings

        embeddings = get_embeddings()
        build_vector_store(docs, embeddings)
    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)
        return {"status": "error", "message": f"Indexing failed: {exc}"}

    return {
        "status": "ok",
        "docs_count": len(docs),
        "message": f"Indexed {len(docs)} document(s) from {path.name}",
    }
```

---

## 5. api/app.py — изменения

### Новая Pydantic-модель

```python
class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING | STARTED | PROCESSING | SUCCESS | FAILURE
    result: Optional[dict] = None
    meta: Optional[dict] = None
```

### Обновить /api/upload — async mode

Добавить в начало `upload_document()`, после сохранения файла на диск (строка ~775):

```python
    # Try async processing via Celery
    try:
        from tasks.ingest_task import ingest_document
        task = ingest_document.delay(str(file_path))
        return UploadResponse(
            status="accepted",
            filename=safe_name,
            message=f"File uploaded. Processing in background. task_id={task.id}",
        )
    except Exception as exc:
        logger.info("Celery not available, falling back to sync: %s", exc)
        # Fall through to sync processing below
```

### Новый endpoint /api/tasks/{task_id}

```python
@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Проверить статус background task."""
    try:
        from tasks.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        return TaskStatusResponse(
            task_id=task_id,
            status=result.status,
            result=result.result if result.ready() else None,
            meta=result.info if not result.ready() and isinstance(result.info, dict) else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Task backend error: {exc}")
```

---

## CONSTRAINTS
- Создать `tasks/` пакет, обновить `requirements.txt` и `api/app.py`
- Graceful degradation: без Celery — sync fallback (текущее поведение)
- `celery -A tasks.celery_app worker --loglevel=info` — стартует
- `pytest tests/ -v` �� проходит

## DONE WHEN
- [ ] `tasks/celery_app.py` и `tasks/ingest_task.py` созданы
- [ ] `/api/upload` при наличии Celery возвращает `status: "accepted"` + task_id
- [ ] `/api/tasks/{id}` показывает статус задачи
- [ ] Без Celery: `/api/upload` работает синхронно (fallback)
- [ ] `pytest tests/ -v` — проходит

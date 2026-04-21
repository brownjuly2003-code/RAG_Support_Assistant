from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_async_upload_flow_reports_progress_and_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    integration_api_app,
    integration_client,
    integration_headers,
) -> None:
    initialize_vector_store = MagicMock()
    fake_celery_app = types.SimpleNamespace()
    fake_ingest_task_module = types.ModuleType("tasks.ingest_task")
    fake_ingest_task_module.ingest_document = types.SimpleNamespace(
        delay=lambda file_path: SimpleNamespace(id="task-123"),
    )

    states = [
        SimpleNamespace(status="STARTED", info={"step": "indexing"}, result=None, ready=lambda: False),
        SimpleNamespace(
            status="SUCCESS",
            info=None,
            result={"status": "ok", "docs_count": 1},
            ready=lambda: True,
        ),
    ]

    def _fake_async_result(task_id: str):
        _ = task_id
        return states.pop(0)

    fake_celery_app.AsyncResult = _fake_async_result
    monkeypatch.setattr(integration_api_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(integration_api_app, "initialize_vector_store", initialize_vector_store)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_ingest_task_module)
    monkeypatch.setitem(
        sys.modules,
        "tasks.celery_app",
        types.SimpleNamespace(celery_app=fake_celery_app),
    )

    upload_response = integration_client.post(
        "/api/upload",
        files={"file": ("manual.txt", b"integration upload", "text/plain")},
        headers=integration_headers("default", "admin"),
    )

    assert upload_response.status_code == 200
    assert upload_response.json()["status"] == "accepted"
    assert "task_id=task-123" in upload_response.json()["message"]

    started = integration_client.get(
        "/api/tasks/task-123",
        headers=integration_headers("default", "admin"),
    )
    finished = integration_client.get(
        "/api/tasks/task-123",
        headers=integration_headers("default", "admin"),
    )

    assert started.status_code == 200
    assert started.json()["status"] == "STARTED"
    assert started.json()["meta"] == {"step": "indexing"}

    assert finished.status_code == 200
    assert finished.json()["status"] == "SUCCESS"
    assert finished.json()["result"] == {"status": "ok", "docs_count": 1}
    initialize_vector_store.assert_called_once()

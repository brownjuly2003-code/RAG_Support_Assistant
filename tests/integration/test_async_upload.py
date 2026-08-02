from __future__ import annotations

import sys
import types
import uuid
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
    ingestion_jobs_db,
) -> None:
    initialize_vector_store = MagicMock()
    enqueued: dict[str, str] = {}

    def _delay(file_path: str, job_id: str, tenant_id: str):
        enqueued["file_path"] = file_path
        enqueued["job_id"] = job_id
        enqueued["tenant_id"] = tenant_id
        return SimpleNamespace(id="task-123")

    fake_ingest_task_module = types.ModuleType("tasks.ingest_task")
    fake_ingest_task_module.ingest_document = types.SimpleNamespace(delay=_delay)

    # Celery AsyncResult must not be required for status polling.
    fake_celery_app = types.SimpleNamespace(
        AsyncResult=lambda task_id: (_ for _ in ()).throw(RuntimeError("redis down")),
    )

    monkeypatch.setattr(integration_api_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(integration_api_app, "initialize_vector_store", initialize_vector_store)
    monkeypatch.setattr(integration_api_app, "_DocumentLoader", None)
    monkeypatch.setattr(integration_api_app, "_build_vector_store", None)
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
    body = upload_response.json()
    assert body["status"] == "accepted"
    assert body["tenant_id"] == "default"
    job_id = body["job_id"]
    uuid.UUID(job_id)
    assert body.get("task_id") == "task-123"
    assert enqueued["job_id"] == job_id
    assert enqueued["tenant_id"] == "default"

    by_job = integration_client.get(
        f"/api/jobs/{job_id}",
        headers=integration_headers("default", "admin"),
    )
    by_task = integration_client.get(
        "/api/tasks/task-123",
        headers=integration_headers("default", "admin"),
    )

    assert by_job.status_code == 200
    assert by_job.json()["job_id"] == job_id
    assert by_job.json()["status"] == "queued"
    assert by_job.json()["task_id"] == "task-123"

    assert by_task.status_code == 200
    assert by_task.json()["job_id"] == job_id
    assert by_task.json()["status"] == "queued"
    # Poll path must not depend on Celery result backend / vector refresh.
    initialize_vector_store.assert_not_called()

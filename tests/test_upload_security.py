import io
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._route_introspection import route_endpoint_module as _route_endpoint_module

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
    "_DocumentLoader": None,
    "_build_vector_store": None,
}


def test_upload_routes_are_owned_by_upload_router(client_with_key: TestClient) -> None:
    assert _route_endpoint_module(client_with_key, "/api/upload", "POST") == "api.routers.upload"
    assert _route_endpoint_module(client_with_key, "/api/tasks/{task_id}", "GET") == "api.routers.upload"
    assert _route_endpoint_module(client_with_key, "/api/jobs/{job_id}", "GET") == "api.routers.upload"


def test_upload_router_uses_shared_app_accessor() -> None:
    import api.routers.upload as upload

    assert upload._app_module.__module__ == "api._shared"


def test_upload_router_imports_without_api_app_first() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "import collections, platform; "
        "U=collections.namedtuple('uname_result','system node release version machine processor'); "
        "platform.machine=lambda: 'AMD64'; "
        "platform.uname=lambda: U('Windows','','','','AMD64','AMD64'); "
        "platform.platform=lambda *args, **kwargs: 'Windows-AMD64'; "
        "import api.routers.upload as upload; "
        "print(upload.router)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("malicious_name", "expected_name"),
    [
        ("../../escape.txt", "escape.txt"),
        ("..\\..\\escape.txt", "escape.txt"),
    ],
)
def test_upload_sanitizes_path_traversal_and_stays_in_upload_dir(
    client_with_key: TestClient,
    tmp_path: Path,
    malicious_name: str,
    expected_name: str,
    ingestion_jobs_db,
) -> None:
    files = {"file": (malicious_name, io.BytesIO(b"test"), "text/plain")}

    resp = client_with_key.post(
        "/api/upload",
        files=files,
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == expected_name
    assert "job_id" in body
    uuid.UUID(body["job_id"])
    assert body["tenant_id"] == "default"
    assert (tmp_path / "data" / "uploads" / expected_name).read_bytes() == b"test"
    assert not (tmp_path / "escape.txt").exists()


def test_upload_rejects_dotfile_names(client_with_key: TestClient) -> None:
    files = {"file": (".hidden.txt", io.BytesIO(b"test"), "text/plain")}

    resp = client_with_key.post(
        "/api/upload",
        files=files,
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid filename"


def test_upload_sanitizes_special_characters(
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    files = {"file": ("my file (1).txt", io.BytesIO(b"hello"), "text/plain")}

    resp = client_with_key.post(
        "/api/upload",
        files=files,
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json()["filename"] == "my_file__1_.txt"
    assert resp.json()["tenant_id"] == "default"
    uuid.UUID(resp.json()["job_id"])


def test_job_status_reads_durable_row(
    client_with_key: TestClient,
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app
    from tasks.celery_app import celery_app

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(
        celery_app,
        "AsyncResult",
        lambda task_id: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
    )

    upload = client_with_key.post(
        "/api/upload",
        files={"file": ("status.txt", io.BytesIO(b"hello"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )
    assert upload.status_code == 200
    job_id = upload.json()["job_id"]

    resp = client_with_key.get(
        f"/api/jobs/{job_id}",
        headers={"X-API-Key": "secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["tenant_id"] == "default"
    assert body["status"] in {"queued", "failed", "completed", "running"}
    assert "created_at" in body


def test_task_status_alias_reads_db_not_celery(
    client_with_key: TestClient,
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app
    from tasks.celery_app import celery_app

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    def broken_result(task_id: str):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(celery_app, "AsyncResult", broken_result)

    upload = client_with_key.post(
        "/api/upload",
        files={"file": ("alias.txt", io.BytesIO(b"hello"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )
    assert upload.status_code == 200
    job_id = upload.json()["job_id"]

    resp = client_with_key.get(
        f"/api/tasks/{job_id}",
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id
    assert resp.json()["tenant_id"] == "default"


def test_task_status_unknown_id_is_404(
    client_with_key: TestClient,
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tasks.celery_app import celery_app

    monkeypatch.setattr(
        celery_app,
        "AsyncResult",
        lambda task_id: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
    )

    resp = client_with_key.get(
        f"/api/tasks/{uuid.uuid4()}",
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"


def test_file_save_failure_response_is_generic(
    client_with_key: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP detail must not include raw OSError / absolute host path."""
    secret_path = r"D:\host\secret\uploads\leak.txt"

    def _boom_write_bytes(self, data: bytes) -> None:
        raise OSError(f"[Errno 13] Permission denied: '{secret_path}'")

    monkeypatch.setattr(Path, "write_bytes", _boom_write_bytes)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("savefail.txt", io.BytesIO(b"payload"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail == "Failed to save file"
    assert secret_path not in detail
    assert "Permission denied" not in detail
    assert "Errno" not in detail

import io
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

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
) -> None:
    files = {"file": (malicious_name, io.BytesIO(b"test"), "text/plain")}

    resp = client_with_key.post(
        "/api/upload",
        files=files,
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json()["filename"] == expected_name
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


def test_upload_sanitizes_special_characters(client_with_key: TestClient) -> None:
    files = {"file": ("my file (1).txt", io.BytesIO(b"hello"), "text/plain")}

    resp = client_with_key.post(
        "/api/upload",
        files=files,
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json()["filename"] == "my_file__1_.txt"


def test_task_status_ready_success_refreshes_vector_store(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app
    from tasks.celery_app import celery_app

    calls = {"refreshed": 0}

    class FakeResult:
        status = "SUCCESS"
        result: ClassVar[dict] = {"status": "ok", "docs_count": 2}
        info = None

        def ready(self) -> bool:
            return True

    monkeypatch.setattr(celery_app, "AsyncResult", lambda task_id: FakeResult())
    monkeypatch.setattr(
        api_app,
        "initialize_vector_store",
        lambda: calls.__setitem__("refreshed", calls["refreshed"] + 1),
    )

    resp = client_with_key.get(
        "/api/tasks/task-1",
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "task_id": "task-1",
        "status": "SUCCESS",
        "result": {"status": "ok", "docs_count": 2},
        "meta": None,
    }
    assert calls == {"refreshed": 1}


def test_task_status_pending_includes_meta(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    from tasks.celery_app import celery_app

    class FakeResult:
        status = "PROCESSING"
        result = None
        info: ClassVar[dict] = {"step": "indexing"}

        def ready(self) -> bool:
            return False

    monkeypatch.setattr(celery_app, "AsyncResult", lambda task_id: FakeResult())

    resp = client_with_key.get(
        "/api/tasks/task-2",
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "task_id": "task-2",
        "status": "PROCESSING",
        "result": None,
        "meta": {"step": "indexing"},
    }


def test_task_status_reports_backend_errors(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    from tasks.celery_app import celery_app

    def broken_result(task_id: str):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(celery_app, "AsyncResult", broken_result)

    resp = client_with_key.get(
        "/api/tasks/task-3",
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Task backend error: redis unavailable"

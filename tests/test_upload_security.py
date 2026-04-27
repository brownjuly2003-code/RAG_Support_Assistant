import io
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
    "_DocumentLoader": None,
    "_build_vector_store": None,
}


def _route_endpoint_module(client: TestClient, path: str, method: str) -> str:
    for route in client.app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method not in getattr(route, "methods", set()):
            continue
        endpoint = route.endpoint
        while hasattr(endpoint, "__wrapped__"):
            endpoint = endpoint.__wrapped__
        return endpoint.__module__
    raise AssertionError(f"Route not found: {method} {path}")


def test_upload_routes_are_owned_by_upload_router(client_with_key: TestClient) -> None:
    assert _route_endpoint_module(client_with_key, "/api/upload", "POST") == "api.routers.upload"
    assert _route_endpoint_module(client_with_key, "/api/tasks/{task_id}", "GET") == "api.routers.upload"


def test_upload_router_imports_without_api_app_first() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import api.routers.upload as upload; print(upload.router)"],
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

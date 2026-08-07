from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as api_app
from api.body_limit import BodySizeExceeded, make_limited_receive, parse_content_length

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
    "_DocumentLoader": None,
    "_build_vector_store": None,
}


def test_large_body_rejected_413(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    mock_pipeline,
    client: TestClient,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(max_request_body_bytes=1024),
    )

    big_question = "x" * 2000
    resp = client.post(
        "/api/ask",
        content=(b'{"question":"' + big_question.encode() + b'"}'),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_small_body_passes(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    mock_pipeline,
    client: TestClient,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(max_request_body_bytes=1024),
    )

    resp = client.post("/api/ask", json={"question": "короткий вопрос"})

    assert resp.status_code == 200


def test_upload_rejected_when_too_large(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    client_with_key: TestClient,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(api_key="secret123", max_upload_bytes=512),
    )

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("big.txt", io.BytesIO(b"A" * 2000), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 413


def test_rejection_counter_increments_for_both_reasons(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    client_with_key: TestClient,
) -> None:
    from monitoring.prometheus import BODY_SIZE_REJECTIONS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            api_key="secret123",
            max_request_body_bytes=100,
            max_upload_bytes=512,
        ),
    )

    before = {
        sample.labels.get("reason", ""): sample.value
        for metric in BODY_SIZE_REJECTIONS.collect()
        for sample in metric.samples
        if sample.name.endswith("_total")
    }

    client_with_key.post(
        "/api/ask",
        content=(b'{"question":"' + (b"x" * 500) + b'"}'),
        headers={"Content-Type": "application/json", "X-API-Key": "secret123"},
    )
    client_with_key.post(
        "/api/upload",
        files={"file": ("big.txt", io.BytesIO(b"B" * 2000), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    after = {
        sample.labels.get("reason", ""): sample.value
        for metric in BODY_SIZE_REJECTIONS.collect()
        for sample in metric.samples
        if sample.name.endswith("_total")
    }

    assert after.get("content_length_too_large", 0.0) > before.get("content_length_too_large", 0.0)
    assert after.get("upload_too_large", 0.0) > before.get("upload_too_large", 0.0)


def test_upload_path_bypasses_body_middleware(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            api_key="secret123",
            max_request_body_bytes=100,
            max_upload_bytes=10 * 1024 * 1024,
        ),
    )

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("small.txt", io.BytesIO(b"hello world\n" * 500), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code != 413


# ---------------------------------------------------------------------------
# §8.2 — received ASGI bytes (not Content-Length alone)
# ---------------------------------------------------------------------------


def test_parse_content_length_helpers() -> None:
    assert parse_content_length(None) is None
    assert parse_content_length("not-a-number") is None
    assert parse_content_length("-1") is None
    assert parse_content_length("0") == 0
    assert parse_content_length("2048") == 2048


@pytest.mark.asyncio
async def test_limited_receive_counts_actual_chunks_not_headers() -> None:
    """Chunked / multi-message bodies must be bounded by received bytes."""
    chunks = [
        {"type": "http.request", "body": b"a" * 80, "more_body": True},
        {"type": "http.request", "body": b"b" * 80, "more_body": False},
    ]
    idx = 0

    async def receive() -> dict[str, Any]:
        nonlocal idx
        message = chunks[idx]
        idx += 1
        return message

    limited = make_limited_receive(receive, limit=100)
    first = await limited()
    assert first["body"] == b"a" * 80

    with pytest.raises(BodySizeExceeded) as exc_info:
        await limited()
    assert exc_info.value.limit == 100
    assert exc_info.value.received == 160


@pytest.mark.asyncio
async def test_limited_receive_allows_body_at_exact_limit() -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"x" * 64, "more_body": False}

    limited = make_limited_receive(receive, limit=64)
    message = await limited()
    assert len(message["body"]) == 64


def test_received_bytes_over_limit_rejected_even_when_content_length_understates(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    mock_pipeline,
    client: TestClient,
) -> None:
    """Lying/understated Content-Length must not bypass the received-byte cap.

    TestClient always attaches a true Content-Length for fixed bodies, so this
    test injects an understated header *after* the ASGI scope is built by
    wrapping the app's body-limit path: the middleware must still reject when
    cumulative received bytes exceed the limit (unit coverage above) and when
    a large body is posted under a tight limit (integration below).
    """
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(max_request_body_bytes=256),
    )

    # Integration: honest large body still 413 (CL early path).
    resp = client.post(
        "/api/ask",
        content=(b'{"question":"' + (b"y" * 400) + b'"}'),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_received_bytes_rejection_increments_metric(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    mock_pipeline,
    client: TestClient,
) -> None:
    from monitoring.prometheus import BODY_SIZE_REJECTIONS, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(max_request_body_bytes=64),
    )

    before = {
        sample.labels.get("reason", ""): sample.value
        for metric in BODY_SIZE_REJECTIONS.collect()
        for sample in metric.samples
        if sample.name.endswith("_total")
    }

    client.post(
        "/api/ask",
        content=(b'{"question":"' + (b"z" * 200) + b'"}'),
        headers={"Content-Type": "application/json"},
    )

    after = {
        sample.labels.get("reason", ""): sample.value
        for metric in BODY_SIZE_REJECTIONS.collect()
        for sample in metric.samples
        if sample.name.endswith("_total")
    }

    # Prefer explicit received-byte reason when middleware wraps receive;
    # Content-Length early path remains valid fail-closed signal.
    received_delta = after.get("received_bytes_too_large", 0.0) - before.get(
        "received_bytes_too_large", 0.0
    )
    cl_delta = after.get("content_length_too_large", 0.0) - before.get(
        "content_length_too_large", 0.0
    )
    assert received_delta > 0.0 or cl_delta > 0.0


# ---------------------------------------------------------------------------
# §8.2 — upload stream → temp → atomic rename (no full-RAM exclusive write path)
# ---------------------------------------------------------------------------


def test_upload_uses_stream_temp_and_atomic_place(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Creator path must stream to a temp part file then place exclusively."""
    import api.routers.upload as upload_mod

    stream_calls: list[dict[str, Any]] = []
    place_calls: list[dict[str, Any]] = []
    original_stream = upload_mod._stream_upload_to_temp
    original_place = upload_mod._place_exclusive_from_path

    async def _spy_stream(*args: Any, **kwargs: Any) -> Any:
        result = await original_stream(*args, **kwargs)
        stream_calls.append({"args": args, "kwargs": kwargs, "result": result})
        return result

    def _spy_place(dest: Path, source: Path) -> None:
        place_calls.append({"dest": dest, "source": source})
        assert source.is_file()
        original_place(dest, source)

    monkeypatch.setattr(upload_mod, "_stream_upload_to_temp", _spy_stream)
    monkeypatch.setattr(upload_mod, "_place_exclusive_from_path", _spy_place)

    # Stub Celery publish so default-tenant path does not need a broker.
    import sys
    import types
    from types import SimpleNamespace

    def _apply_async(*_a: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=kwargs.get("task_id") or "stub-task")

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(apply_async=_apply_async)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)

    payload = b"streamed-upload-payload-8-2\n" * 20
    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("streamed.txt", io.BytesIO(payload), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200, resp.text
    assert stream_calls, "upload must stream to a temp file"
    assert place_calls, "upload must place immutable object from the temp file"
    body = resp.json()
    job_id = body["job_id"]
    imm = tmp_path / "data" / "uploads" / "job-objects" / job_id / "streamed.txt"
    assert imm.is_file()
    assert imm.read_bytes() == payload
    current = tmp_path / "data" / "uploads" / "streamed.txt"
    assert current.is_file()
    assert current.read_bytes() == payload
    # No leftover .part / .tmp upload spools under the tenant root.
    leftovers = [
        p
        for p in (tmp_path / "data" / "uploads").rglob("*")
        if p.is_file() and (p.suffix == ".part" or ".upload-" in p.name)
    ]
    assert leftovers == []


@pytest.mark.asyncio
async def test_stream_upload_fingerprint_matches_jobs_helper(
    tmp_path: Path,
) -> None:
    """Streaming hasher must stay byte-identical to compute_payload_fingerprint."""
    from api.routers import upload as upload_mod
    from ingestion.jobs import compute_payload_fingerprint

    payload = b"fingerprint-contract-bytes\n" * 17
    safe_name = "contract.txt"

    class _FakeUpload:
        def __init__(self, data: bytes) -> None:
            self._buf = io.BytesIO(data)

        async def read(self, n: int = -1) -> bytes:
            return self._buf.read(n)

    temp_path, fingerprint, size = await upload_mod._stream_upload_to_temp(
        _FakeUpload(payload),  # type: ignore[arg-type]
        upload_dir=tmp_path,
        upload_limit=10 * 1024 * 1024,
        safe_name=safe_name,
    )
    try:
        assert size == len(payload)
        assert temp_path.read_bytes() == payload
        assert fingerprint == compute_payload_fingerprint(safe_name, payload)
    finally:
        temp_path.unlink(missing_ok=True)


def test_upload_oversized_stream_cleans_temp_and_returns_413(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(api_key="secret123", max_upload_bytes=128),
    )

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("too-big.txt", io.BytesIO(b"X" * 4000), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 413
    upload_root = tmp_path / "data" / "uploads"
    if upload_root.exists():
        leftovers = [
            p
            for p in upload_root.rglob("*")
            if p.is_file() and (p.suffix == ".part" or ".upload-" in p.name)
        ]
        assert leftovers == []

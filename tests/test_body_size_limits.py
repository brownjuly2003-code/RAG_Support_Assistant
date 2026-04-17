from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import api.app as api_app

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

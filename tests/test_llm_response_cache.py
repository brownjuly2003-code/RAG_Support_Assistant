from __future__ import annotations

import importlib
import io
import re

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")

CLIENT_SETTINGS_OVERRIDES = {
    "llm_cache_enabled": True,
    "llm_cache_ttl_seconds": 3600,
}
CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
    "llm_cache_enabled": True,
    "llm_cache_ttl_seconds": 3600,
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
}


def _metric_value(metrics_text: str, name: str, labels: str = "") -> float | None:
    label_part = f"{{{labels}}}" if labels else ""
    match = re.search(
        rf"^{re.escape(name)}{re.escape(label_part)}\s+([0-9.e+-]+)$",
        metrics_text,
        re.MULTILINE,
    )
    if match is None:
        return None
    return float(match.group(1))


def _token(tenant: str = "default", role: str = "admin") -> dict[str, str]:
    token = create_access_token("tenant-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_cache_key_is_normalized() -> None:
    k1 = api_app._cache_key("acme", "How to reset password?")
    k2 = api_app._cache_key("acme", "  how to reset password?  ")

    assert k1 == k2


def test_cache_key_isolates_tenants() -> None:
    assert api_app._cache_key("acme", "x") != api_app._cache_key("mega", "x")


def test_cached_response_returns_without_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    metrics_before = client.get("/metrics")
    before_hits = _metric_value(
        metrics_before.text,
        "llm_cache_hits_total",
        'tenant="default"',
    ) or 0.0

    session_holder: dict[str, object] = {}
    captured: dict[str, object] = {}

    class FakeSession:
        def __init__(self) -> None:
            self._history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default"):
            raise AssertionError("session.ask must not be called on cache hit")

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        _ = session_id, tenant_id
        session = FakeSession()
        session_holder["session"] = session
        return "00000000000000000000000000000001", session

    def _fake_cache_json_get(key: str):
        captured["key"] = key
        return {
            "answer": "Reset it in Settings > Security.",
            "quality_score": 91,
            "route": "auto",
            "sources": [{"source": "faq.md", "page_content": "Reset password article"}],
            "suggested_questions": ["Where can I update MFA?"],
        }

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "cache_json_get", _fake_cache_json_get)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client.post("/api/ask", json={"question": "  HOW TO RESET PASSWORD?  "})

    assert response.status_code == 200
    assert response.json()["answer"] == "Reset it in Settings > Security."
    assert response.json()["cached"] is True
    assert captured["key"] == api_app._cache_key("default", "  HOW TO RESET PASSWORD?  ")
    assert session_holder["session"]._history == [
        {"role": "user", "content": "HOW TO RESET PASSWORD?"},
        {"role": "assistant", "content": "Reset it in Settings > Security."},
    ]

    metrics_after = client.get("/metrics")
    after_hits = _metric_value(
        metrics_after.text,
        "llm_cache_hits_total",
        'tenant="default"',
    ) or 0.0
    assert after_hits == before_hits + 1.0


def test_cache_miss_invokes_pipeline_and_stores(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    metrics_before = client.get("/metrics")
    before_misses = _metric_value(
        metrics_before.text,
        "llm_cache_misses_total",
        'tenant="default"',
    ) or 0.0

    captured: dict[str, object] = {"ask_calls": 0}
    settings = settings_factory(llm_cache_enabled=True, llm_cache_ttl_seconds=123)

    class FakeSession:
        def __init__(self) -> None:
            self._history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default"):
            captured["ask_calls"] += 1
            captured["ask_question"] = question
            captured["ask_tenant"] = tenant_id
            return {
                "answer": "Download it from the customer portal.",
                "quality_score": 84,
                "route": "auto",
                "graded_docs": [
                    {
                        "page_content": "Go to the customer portal downloads page.",
                        "metadata": {"source": "downloads.md"},
                    }
                ],
                "trace_id": "trace-123",
                "suggested_questions": ["What if I lost access to the portal?"],
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        _ = session_id, tenant_id
        return "00000000000000000000000000000002", FakeSession()

    def _fake_cache_json_get(key: str):
        captured["get_key"] = key
        return None

    def _fake_cache_json_set(key: str, value, ttl_seconds: int = 3600) -> None:
        captured["set_key"] = key
        captured["set_value"] = value
        captured["set_ttl"] = ttl_seconds

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "cache_json_get", _fake_cache_json_get)
    monkeypatch.setattr(api_app, "cache_json_set", _fake_cache_json_set)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client.post("/api/ask", json={"question": "Where can I download X?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Download it from the customer portal."
    # cached is now part of the AskResponse schema (fable_com.md F-17):
    # uncached answers carry an explicit false instead of omitting the key.
    assert response.json().get("cached") is False
    assert captured["ask_calls"] == 1
    assert captured["get_key"] == api_app._cache_key("default", "Where can I download X?")
    assert captured["set_key"] == captured["get_key"]
    assert captured["set_ttl"] == 123
    assert captured["set_value"] == {
        "answer": "Download it from the customer portal.",
        "quality_score": 84,
        "route": "auto",
        "sources": [
            {
                "source": "downloads.md",
                "page_content": "Go to the customer portal downloads page.",
            }
        ],
        "suggested_questions": ["What if I lost access to the portal?"],
    }

    metrics_after = client.get("/metrics")
    after_misses = _metric_value(
        metrics_after.text,
        "llm_cache_misses_total",
        'tenant="default"',
    ) or 0.0
    assert after_misses == before_misses + 1.0


def test_cache_invalidated_on_upload(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, object] = {}

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            self.recursive = recursive

        def load_documents(self, path: str):
            captured["load_path"] = path
            return [{"page_content": "doc", "metadata": {"source": "guide.txt"}}]

    def _fake_rebuild(docs, tenant_id: str = "default") -> bool:
        captured["tenant_id"] = tenant_id
        captured["docs"] = docs
        return True

    def _fake_cache_delete_pattern(pattern: str) -> int:
        captured["pattern"] = pattern
        return 2

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _fake_rebuild)
    monkeypatch.setattr(api_app, "cache_delete_pattern", _fake_cache_delete_pattern)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client_with_key.post(
        "/api/upload",
        files={"file": ("guide.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=_token("acme", "admin"),
    )

    assert response.status_code == 200
    assert captured["tenant_id"] == "acme"
    assert captured["pattern"] == "llm_resp:acme:*"


def test_cache_disabled_flag_skips_entirely(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    settings_factory,
) -> None:
    captured = {"get_calls": 0, "set_calls": 0, "ask_calls": 0}
    settings = settings_factory(llm_cache_enabled=False, llm_cache_ttl_seconds=123)

    class FakeSession:
        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default"):
            captured["ask_calls"] += 1
            return {
                "answer": "Live answer",
                "quality_score": 80,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-disabled",
                "suggested_questions": [],
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        _ = session_id, tenant_id
        return "00000000000000000000000000000003", FakeSession()

    def _fake_cache_json_get(key: str):
        _ = key
        captured["get_calls"] += 1
        return None

    def _fake_cache_json_set(key: str, value, ttl_seconds: int = 3600) -> None:
        _ = key, value, ttl_seconds
        captured["set_calls"] += 1

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "cache_json_get", _fake_cache_json_get)
    monkeypatch.setattr(api_app, "cache_json_set", _fake_cache_json_set)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client.post("/api/ask", json={"question": "test"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Live answer"
    assert captured == {"get_calls": 0, "set_calls": 0, "ask_calls": 1}

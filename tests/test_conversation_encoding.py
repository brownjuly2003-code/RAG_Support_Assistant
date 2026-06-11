from __future__ import annotations

import importlib
from typing import Any, ClassVar

from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")


def test_ask_response_declares_utf8_for_cyrillic_payload(
    monkeypatch,
    client: TestClient,
) -> None:
    async def _noop_log_audit(**kwargs: Any) -> None:
        _ = kwargs

    def _ask(question: str, **kwargs: Any) -> dict[str, Any]:
        _ = question, kwargs
        return {
            "answer": "Чтобы оформить возврат, принесите товар и чек.",
            "quality_score": 95,
            "route": "auto",
            "context_docs": [
                {
                    "page_content": "Политика возврата: товар можно вернуть в течение 14 дней.",
                    "metadata": {"source": "returns_policy.md"},
                }
            ],
            "trace_id": "trace-utf8",
        }

    class FakeSession:
        ask = staticmethod(_ask)
        _history: ClassVar[list[dict[str, str]]] = []

    monkeypatch.setattr(api_app, "log_audit", _noop_log_audit)
    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("00000000-0000-0000-0000-000000000001", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    response = client.post(
        "/api/ask",
        json={"question": "Как оформить возврат товара?"},
    )

    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"].lower()
    assert response.content.decode("utf-8")
    payload = response.json()
    assert payload["answer"] == "Чтобы оформить возврат, принесите товар и чек."
    assert payload["sources"][0]["page_content"] == "Политика возврата: товар можно вернуть в течение 14 дней."


def test_cached_ask_response_declares_utf8_for_cyrillic_payload(
    monkeypatch,
    client: TestClient,
    settings_factory,
) -> None:
    settings = settings_factory(llm_cache_enabled=True, llm_cache_ttl_seconds=3600)

    async def _noop_log_audit(**kwargs: Any) -> None:
        _ = kwargs

    class FakeSession:
        def ask(self, question: str, **kwargs: Any) -> dict[str, Any]:
            _ = question, kwargs
            raise AssertionError("session.ask must not be called on cache hit")

        _history: ClassVar[list[dict[str, str]]] = []

    def _cache_json_get(key: str) -> dict[str, Any]:
        _ = key
        return {
            "answer": "Возврат доступен в течение 14 дней.",
            "quality_score": 95,
            "route": "auto",
            "sources": [
                {
                    "source": "returns_policy.md",
                    "page_content": "Политика возврата: товар можно вернуть в течение 14 дней.",
                }
            ],
        }

    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(api_app, "cache_json_get", _cache_json_get)
    monkeypatch.setattr(api_app, "log_audit", _noop_log_audit)
    async def _fake_get_or_create_session(session_id, tenant_id="default"):
        return ("00000000-0000-0000-0000-000000000002", FakeSession())

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    response = client.post(
        "/api/ask",
        json={"question": "Можно вернуть товар?"},
    )

    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"].lower()
    payload = response.json()
    assert payload["cached"] is True
    assert payload["answer"] == "Возврат доступен в течение 14 дней."
    assert payload["sources"][0]["page_content"] == "Политика возврата: товар можно вернуть в течение 14 дней."

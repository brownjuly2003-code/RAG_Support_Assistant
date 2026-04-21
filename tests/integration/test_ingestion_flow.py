from __future__ import annotations

import types
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_upload_then_ask_returns_uploaded_content(
    monkeypatch: pytest.MonkeyPatch,
    integration_api_app,
    integration_client,
    integration_headers,
    integration_store,
) -> None:
    uploaded_text = "Политика возврата: товар можно вернуть в течение 14 дней."

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            _ = recursive

        def load_documents(self, folder_path: str):
            _ = folder_path
            return [
                types.SimpleNamespace(
                    page_content=uploaded_text,
                    metadata={"source": "policy.txt", "doc_id": "policy-1", "title": "Возвраты"},
                )
            ]

    def _fake_rebuild_vector_store(docs, tenant_id: str = "default") -> bool:
        integration_store["docs"][tenant_id] = list(docs)
        return True

    class FakeSession:
        def __init__(self, tenant_id: str) -> None:
            self._tenant_id = tenant_id
            self._history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default") -> dict:
            _ = question, trace_id
            docs = integration_store["docs"][tenant_id]
            doc = docs[0]
            return {
                "answer": "Срок возврата составляет 14 дней.",
                "quality_score": 88,
                "route": "auto",
                "graded_docs": [
                    {"page_content": doc.page_content, "metadata": doc.metadata},
                ],
                "trace_id": "trace-upload-1",
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        normalized = session_id or uuid.uuid4().hex
        key = (tenant_id, normalized)
        sessions = integration_store["sessions"]
        if key not in sessions:
            sessions[key] = FakeSession(tenant_id)
        return normalized, sessions[key]

    monkeypatch.setattr(integration_api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(integration_api_app, "_rebuild_vector_store_from_docs", _fake_rebuild_vector_store)
    monkeypatch.setattr(integration_api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)

    upload_response = integration_client.post(
        "/api/upload",
        files={"file": ("policy.txt", uploaded_text.encode("utf-8"), "text/plain")},
        headers=integration_headers("acme", "admin"),
    )

    assert upload_response.status_code == 200
    assert upload_response.json()["status"] == "ok"

    ask_response = integration_client.post(
        "/api/ask",
        json={"question": "Какой срок возврата?"},
        headers=integration_headers("acme", "admin"),
    )

    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert "14 дней" in payload["answer"]
    assert payload["sources"][0]["source"] == "policy.txt"
    assert payload["citations"][0]["doc_id"] == "policy-1"

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, ClassVar

import pytest

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("kb-builder-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def test_generate_kb_draft_redacts_pii() -> None:
    from scripts.kb_builder import generate_kb_draft

    cluster = [
        {
            "user_question": "Как изменить адрес доставки?",
            "operator_response": "Напишите на john@example.com и позвоните +7 999 123 45 67",
        }
    ]

    class _FakeLLM:
        def invoke(self, prompt: str) -> str:
            assert "Do NOT include PII" in prompt
            return (
                '{"topic":"Доставка","content":"Свяжитесь с john@example.com '
                'или +7 999 123 45 67, чтобы обновить адрес."}'
            )

    draft = generate_kb_draft(cluster, llm=_FakeLLM())

    assert draft["topic"] == "Доставка"
    assert "john@example.com" not in draft["content"]
    assert "***@***.***" in draft["content"]


def test_admin_kb_drafts_endpoint_filters_by_status_and_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    captured: dict[str, str] = {}

    class _Draft:
        id = uuid.UUID("00000000-0000-0000-0000-000000000114")
        tenant_id = "acme"
        topic = "Возвраты"
        draft_content = "# Возврат\n\nИнструкция"
        source_ticket_ids: ClassVar[list[str]] = ["1", "2", "3"]
        status = "pending"
        created_at = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
        reviewed_at = None

    class _ScalarResult:
        def all(self):
            return [_Draft()]

    class _Result:
        def scalars(self):
            return _ScalarResult()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get(
        "/api/admin/kb-drafts?status=pending",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert "kb_drafts.tenant_id" in captured["sql"]
    assert "kb_drafts.status" in captured["sql"]
    assert response.json()["drafts"][0]["topic"] == "Возвраты"


def test_admin_kb_publish_mutates_the_manifest_active_collection_under_lock(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app
    from vectordb import manager
    from vectordb.index_manifest import publish_active_collection

    draft_id = uuid.UUID("00000000-0000-0000-0000-000000000115")
    active_name = "rag_docs-v-acme-1111111111111111"
    captured: dict[str, Any] = {"locked": False, "reset": []}

    class _Draft:
        id = draft_id
        tenant_id = "acme"
        topic = "Возвраты"
        draft_content = "Опубликованная инструкция"
        source_ticket_ids: ClassVar[list[str]] = ["ticket-1"]
        status = "pending"
        reviewed_at = None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, model, value):
            _ = model
            assert value == draft_id
            return _Draft()

        async def commit(self) -> None:
            captured["committed"] = True

    class _FakeChroma:
        def __init__(self, **kwargs: Any) -> None:
            assert captured["locked"] is True
            captured["collection_name"] = kwargs["collection_name"]

        def add_documents(self, documents: list[Any]) -> None:
            assert captured["locked"] is True
            captured["documents"] = documents

        def persist(self) -> None:
            assert captured["locked"] is True

    chroma_directory = api_app.get_settings().vectordb_chroma_dir
    with manager.tenant_index_lock("acme") as lock_token:
        publish_active_collection(
            "acme",
            active_name,
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    real_lock = manager.tenant_index_lock

    @contextmanager
    def _recording_lock(tenant_id: str):
        with real_lock(tenant_id) as lock_token:
            captured["locked"] = True
            try:
                yield lock_token
            finally:
                captured["locked"] = False

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(manager, "tenant_index_lock", _recording_lock)
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)
    monkeypatch.setattr(manager, "get_embeddings", lambda: object())
    monkeypatch.setattr(
        manager,
        "reset_retriever_cache",
        lambda tenant_id: captured["reset"].append(tenant_id),
    )

    response = client_with_key.post(
        f"/api/admin/kb-drafts/{draft_id}/publish",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert captured["collection_name"] == active_name
    assert captured["reset"] == ["acme"]
    assert captured["committed"] is True

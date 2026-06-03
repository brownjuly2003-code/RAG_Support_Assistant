from __future__ import annotations

from typing import ClassVar

import uuid
from datetime import datetime, timezone

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

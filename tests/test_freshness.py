from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("freshness-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def test_admin_stale_docs_endpoint_returns_ranked_documents(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    now = datetime.now(timezone.utc)

    class _Stat:
        doc_id = "policy-1"
        tenant_id = "acme"
        citation_count = 9
        last_cited_at = now

    class _ScalarResult:
        def all(self):
            return [_Stat()]

    class _Result:
        def scalars(self):
            return _ScalarResult()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(
        api_app,
        "_list_tenant_documents",
        lambda tenant_id: [
            {
                "doc_id": "policy-1",
                "title": "Политика возврата",
                "source": "policy-1",
                "last_updated": (now - timedelta(days=120)).isoformat(),
            }
        ],
    )

    response = client_with_key.get(
        "/api/admin/stale-docs?days=90&top_cited=5",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["documents"][0]["doc_id"] == "policy-1"
    assert response.json()["documents"][0]["citation_count"] == 9


def test_stale_doc_review_endpoint_touches_document(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    touched: dict[str, str] = {}

    def _fake_touch(tenant_id: str, doc_id: str) -> bool:
        touched["tenant_id"] = tenant_id
        touched["doc_id"] = doc_id
        return True

    monkeypatch.setattr(api_app, "_touch_tenant_document", _fake_touch)

    response = client_with_key.post(
        "/api/admin/stale-docs/policy-1/review",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert touched == {"tenant_id": "acme", "doc_id": "policy-1"}

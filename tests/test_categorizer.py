from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("categorizer-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def _write_categories_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
default:
  - name: shipping
    description: Delivery, shipping, pickup
  - name: returns
    description: Returns, refunds, cancellations
""".strip(),
        encoding="utf-8",
    )
    return path


def test_classify_document_returns_matching_categories() -> None:
    from ingestion.categorizer import classify_document

    class _FakeLLM:
        def invoke(self, prompt: str) -> str:
            assert "shipping" in prompt
            return '["shipping"]'

    categories = [
        {"name": "shipping", "description": "Delivery, shipping, pickup"},
        {"name": "returns", "description": "Returns, refunds, cancellations"},
    ]

    assert classify_document("Delivery and pickup terms", categories, llm=_FakeLLM()) == ["shipping"]


def test_classify_document_invalid_json_falls_back_to_uncategorized() -> None:
    from ingestion.categorizer import classify_document

    class _FakeLLM:
        def invoke(self, prompt: str) -> str:
            _ = prompt
            return "not-json"

    categories = [{"name": "shipping", "description": "Delivery, shipping, pickup"}]

    assert classify_document("Delivery and pickup terms", categories, llm=_FakeLLM()) == ["uncategorized"]


def test_admin_categories_endpoint_returns_default_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.categories_config_path = _write_categories_config(tmp_path / "config" / "categories.yml")
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    response = client_with_key.get("/api/admin/categories", headers=_headers())

    assert response.status_code == 200
    assert response.json()["categories"] == [
        {"name": "shipping", "description": "Delivery, shipping, pickup"},
        {"name": "returns", "description": "Returns, refunds, cancellations"},
    ]


def test_upload_response_includes_assigned_categories(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
    tmp_path: Path,
) -> None:
    import api.app as api_app
    from ingestion import categorizer as categorizer_module

    settings = api_app.get_settings()
    settings.categories_config_path = _write_categories_config(tmp_path / "config" / "categories.yml")
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    captured: dict[str, object] = {}

    class _FakeLoader:
        def __init__(self, recursive: bool = False):
            self.recursive = recursive

        def load_documents(self, path: str):
            captured["load_path"] = path
            return [
                SimpleNamespace(
                    page_content="Delivery and pickup terms",
                    metadata={"source": "guide.txt", "file_name": "guide.txt"},
                )
            ]

    def _fake_rebuild(docs, tenant_id: str = "default") -> bool:
        captured["tenant_id"] = tenant_id
        captured["categories"] = docs[0].metadata["categories"]
        captured["primary_category"] = docs[0].metadata["primary_category"]
        return True

    async def _fake_log_audit(**kwargs) -> None:
        _ = kwargs
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", _FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _fake_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(
        categorizer_module,
        "classify_document",
        lambda full_text, categories, llm=None: ["shipping"],
    )

    response = client_with_key.post(
        "/api/upload",
        files={"file": ("guide.txt", io.BytesIO(b"delivery info"), "text/plain")},
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["assigned_categories"] == ["shipping"]
    assert captured["tenant_id"] == "acme"
    assert captured["categories"] == ["shipping"]
    assert captured["primary_category"] == "shipping"


def test_retrieve_filters_documents_by_requested_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb import manager

    docs = [
        SimpleNamespace(page_content="Shipping policy", metadata={"categories": ["shipping"]}),
        SimpleNamespace(page_content="Returns policy", metadata={"categories": ["returns"]}),
    ]

    class _FakeRetriever:
        def get_relevant_documents(self, query: str):
            _ = query
            return docs

    monkeypatch.setattr(manager, "get_retriever", lambda *args, **kwargs: _FakeRetriever())

    result = manager.retrieve(
        "How long is delivery?",
        tenant_id="acme",
        categories=["shipping"],
    )

    assert [doc.page_content for doc in result] == ["Shipping policy"]

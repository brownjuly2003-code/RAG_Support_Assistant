"""Admin HTTP surface for read-only index retention preview (plan 2.3b)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token
from vectordb.index_operator import IndexRetentionPreview

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "vectordb_retention_max_versions": 3,
}

_ENDPOINT = "/api/admin/index/retention-preview"


def _admin_headers(tenant: str = "acme", sub: str = "admin-user") -> dict[str, str]:
    token = create_access_token(sub, "admin", tenant)
    return {"Authorization": f"Bearer {token}"}


def _role_headers(role: str, tenant: str = "acme") -> dict[str, str]:
    token = create_access_token(f"{role}-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def _sample_preview(
    *,
    tenant_id: str = "acme",
    max_versions: int = 2,
) -> IndexRetentionPreview:
    return IndexRetentionPreview(
        tenant_id=tenant_id,
        max_versions=max_versions,
        manifest_generation=4,
        active_collection="acme__v0000000000000004",
        previous_collection="acme__v0000000000000003",
        inventory_collections=(
            "acme__v0000000000000001",
            "acme__v0000000000000002",
            "acme__v0000000000000003",
            "acme__v0000000000000004",
        ),
        deletion_candidates=(
            "acme__v0000000000000001",
            "acme__v0000000000000002",
        ),
    )


def _install_preview(
    monkeypatch: pytest.MonkeyPatch,
    *,
    preview: IndexRetentionPreview | None = None,
    side_effect: BaseException | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recorded = calls if calls is not None else []

    def _fake_preview(
        tenant_id: str,
        *,
        max_versions: int,
        chroma_directory: str | Path | None = None,
    ) -> IndexRetentionPreview:
        recorded.append(
            {
                "tenant_id": tenant_id,
                "max_versions": max_versions,
                "chroma_directory": chroma_directory,
            }
        )
        if side_effect is not None:
            raise side_effect
        assert preview is not None
        return preview

    monkeypatch.setattr(
        "vectordb.index_operator.preview_index_retention",
        _fake_preview,
    )
    return recorded


def _install_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    audit_calls: list[dict[str, Any]] = []

    async def _fake_log_audit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)
    return audit_calls


def test_admin_success_uses_jwt_tenant_ignores_foreign_query(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    expected = _sample_preview(tenant_id="acme", max_versions=2)
    calls = _install_preview(monkeypatch, preview=expected)
    _install_audit(monkeypatch)
    chroma_dir = api_app.get_settings().vectordb_chroma_dir

    response = client_with_key.get(
        f"{_ENDPOINT}?tenant_id=foreign&max_versions=2",
        headers=_admin_headers("acme", sub="ops-admin"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "acme",
        "max_versions": 2,
        "manifest_generation": 4,
        "active_collection": "acme__v0000000000000004",
        "previous_collection": "acme__v0000000000000003",
        "inventory_collections": [
            "acme__v0000000000000001",
            "acme__v0000000000000002",
            "acme__v0000000000000003",
            "acme__v0000000000000004",
        ],
        "deletion_candidates": [
            "acme__v0000000000000001",
            "acme__v0000000000000002",
        ],
    }
    assert calls == [
        {
            "tenant_id": "acme",
            "max_versions": 2,
            "chroma_directory": chroma_dir,
        }
    ]


def test_omitted_budget_uses_settings_explicit_overrides(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    assert settings.vectordb_retention_max_versions == 3

    calls: list[dict[str, Any]] = []
    _install_preview(
        monkeypatch,
        preview=_sample_preview(max_versions=3),
        calls=calls,
    )
    _install_audit(monkeypatch)

    omitted = client_with_key.get(_ENDPOINT, headers=_admin_headers("acme"))
    assert omitted.status_code == 200
    assert omitted.json()["max_versions"] == 3
    assert calls[-1]["max_versions"] == 3
    assert calls[-1]["tenant_id"] == "acme"

    _install_preview(
        monkeypatch,
        preview=_sample_preview(max_versions=5),
        calls=calls,
    )
    explicit = client_with_key.get(
        f"{_ENDPOINT}?max_versions=5",
        headers=_admin_headers("acme"),
    )
    assert explicit.status_code == 200
    assert explicit.json()["max_versions"] == 5
    assert calls[-1]["max_versions"] == 5
    assert calls[-1]["tenant_id"] == "acme"
    # Budget is the only override; tenant still comes from JWT.
    assert calls[-1]["chroma_directory"] == settings.vectordb_chroma_dir


def test_success_audit_includes_candidate_list_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    preview = _sample_preview(tenant_id="acme", max_versions=2)
    _install_preview(monkeypatch, preview=preview)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        f"{_ENDPOINT}?max_versions=2",
        headers=_admin_headers("acme", sub="audit-admin"),
    )

    assert response.status_code == 200
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "audit-admin"
    assert entry["action"] == "index_retention_preview"
    assert entry["resource"] == "index/retention-preview"
    assert entry["tenant_id"] == "acme"
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": "success",
        "max_versions": 2,
        "manifest_generation": 4,
        "active_collection": "acme__v0000000000000004",
        "previous_collection": "acme__v0000000000000003",
        "inventory_count": 4,
        "deletion_candidates": [
            "acme__v0000000000000001",
            "acme__v0000000000000002",
        ],
    }


@pytest.mark.parametrize(
    ("headers", "status_code"),
    [
        (None, 401),
        (_role_headers("agent"), 403),
        (_role_headers("viewer"), 403),
    ],
)
def test_auth_failures_skip_preview_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    headers: dict[str, str] | None,
    status_code: int,
) -> None:
    calls = _install_preview(
        monkeypatch,
        preview=_sample_preview(),
    )
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        _ENDPOINT,
        headers=headers or {},
    )

    assert response.status_code == status_code
    assert calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    ("exc_factory", "status_code", "detail", "outcome", "error_type"),
    [
        (
            lambda: __import__(
                "vectordb.index_retention", fromlist=["IndexRetentionValidationError"]
            ).IndexRetentionValidationError("max_versions must be >= 2"),
            400,
            "invalid retention preview budget",
            "rejected",
            "IndexRetentionValidationError",
        ),
        (
            lambda: __import__(
                "vectordb.index_retention", fromlist=["IndexRetentionCorrupt"]
            ).IndexRetentionCorrupt("inventory corrupt"),
            409,
            "index retention metadata is corrupt",
            "metadata_corrupt",
            "IndexRetentionCorrupt",
        ),
        (
            lambda: __import__(
                "vectordb.index_manifest", fromlist=["IndexManifestCorrupt"]
            ).IndexManifestCorrupt("manifest corrupt"),
            409,
            "index retention metadata is corrupt",
            "metadata_corrupt",
            "IndexManifestCorrupt",
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockTimeout"]
            ).TenantIndexLockTimeout("lock timeout"),
            503,
            "index retention preview is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockTimeout",
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockUnavailable"]
            ).TenantIndexLockUnavailable("lock unavailable"),
            503,
            "index retention preview is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockUnavailable",
        ),
    ],
)
def test_typed_failures_map_to_safe_http_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    exc_factory: Any,
    status_code: int,
    detail: str,
    outcome: str,
    error_type: str,
) -> None:
    side_effect = exc_factory()
    _install_preview(monkeypatch, side_effect=side_effect)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        f"{_ENDPOINT}?max_versions=2",
        headers=_admin_headers("acme", sub="fail-admin"),
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    # Raw exception text must never leak into the HTTP body.
    body_text = response.text
    assert "corrupt" not in body_text or detail in body_text
    assert "lock timeout" not in body_text
    assert "max_versions must" not in body_text
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "fail-admin"
    assert entry["action"] == "index_retention_preview"
    assert entry["resource"] == "index/retention-preview"
    assert entry["tenant_id"] == "acme"
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": outcome,
        "max_versions": 2,
        "error_type": error_type,
    }
    # Failure audits stay free of exception text / paths / stacks.
    assert set(entry["detail"]) == {
        "tenant",
        "outcome",
        "max_versions",
        "error_type",
    }


def test_unrelated_exception_is_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_preview(monkeypatch, side_effect=RuntimeError("boom-internal"))
    audit_calls = _install_audit(monkeypatch)

    with pytest.raises(RuntimeError, match="boom-internal"):
        client_with_key.get(
            f"{_ENDPOINT}?max_versions=2",
            headers=_admin_headers("acme"),
        )

    # Only mapped typed failures audit; unrelated exceptions must not be rewritten.
    assert audit_calls == []


def test_route_is_get_only_and_repeatable_read_only(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_preview(monkeypatch, preview=_sample_preview(max_versions=2))
    audit_calls = _install_audit(monkeypatch)

    post = client_with_key.post(
        f"{_ENDPOINT}?max_versions=2",
        headers=_admin_headers("acme"),
    )
    assert post.status_code == 405
    assert calls == []
    assert audit_calls == []

    first = client_with_key.get(
        f"{_ENDPOINT}?max_versions=2",
        headers=_admin_headers("acme"),
    )
    second = client_with_key.get(
        f"{_ENDPOINT}?max_versions=2",
        headers=_admin_headers("acme"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 2
    assert len(audit_calls) == 2
    # Endpoint boundary only invokes the read-only preview primitive.
    assert all(
        set(call) == {"tenant_id", "max_versions", "chroma_directory"}
        for call in calls
    )


def test_endpoint_module_has_no_chroma_or_mutation_wiring() -> None:
    source = Path("api/routers/admin_ops.py").read_text(encoding="utf-8")
    # Narrow the retention-preview handler slice for boundary assertions.
    marker = "retention-preview"
    assert marker in source
    start = source.index('@router.get("/admin/index/retention-preview")')
    # Through end of file is fine; this module should not gain mutation wiring.
    handler = source[start:]

    forbidden_snippets = (
        "chromadb",
        "PersistentClient",
        "list_collections",
        "get_or_create_collection",
        "delete_collection",
        "execute_chroma_retention",
        "execute_bounded_retention",
        "publish_active_collection",
        "rollback_active_collection",
        "record_retention_collection",
    )
    for snippet in forbidden_snippets:
        assert snippet not in handler, f"forbidden wiring: {snippet}"
    assert "preview_index_retention" in handler
    assert "asyncio.to_thread" in handler

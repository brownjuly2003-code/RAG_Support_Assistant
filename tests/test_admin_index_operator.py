"""Admin HTTP surface for index retention preview and rollback (plan 2.3b/2.3e)."""
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
_ROLLBACK_ENDPOINT = "/api/admin/index/rollback"
_ROLLBACK_TARGET = "acme__v0000000000000004"
_ROLLBACK_BODY = {
    "expected_generation": 4,
    "target_collection": _ROLLBACK_TARGET,
}


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


def _install_rollback(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: tuple[Any, list[Any]] | None = None,
    side_effect: BaseException | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recorded = calls if calls is not None else []

    def _fake_rollback(
        tenant_id: str = "default",
        embeddings: Any | None = None,
        *,
        expected_generation: int,
        target_collection: str,
    ) -> tuple[Any, list[Any]]:
        recorded.append(
            {
                "tenant_id": tenant_id,
                "embeddings": embeddings,
                "expected_generation": expected_generation,
                "target_collection": target_collection,
            }
        )
        if side_effect is not None:
            raise side_effect
        if result is not None:
            return result
        return (object(), [])

    monkeypatch.setattr(
        "vectordb.manager.rollback_vector_store",
        _fake_rollback,
    )
    return recorded


def _expected_rollback_response(
    *,
    tenant_id: str = "acme",
    expected_generation: int = 4,
    target_collection: str = _ROLLBACK_TARGET,
) -> dict[str, Any]:
    return {
        "status": "active",
        "tenant_id": tenant_id,
        "expected_generation": expected_generation,
        "target_collection": target_collection,
        "manifest_generation": expected_generation + 1,
        "active_collection": target_collection,
    }


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
    # Isolate only the read-only retention-preview handler before rollback.
    marker = "retention-preview"
    assert marker in source
    start = source.index('@router.get("/admin/index/retention-preview")')
    end = source.index('@router.post("/admin/index/rollback")')
    handler = source[start:end]

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
        "rollback_vector_store",
        "rollback_index_version",
    )
    for snippet in forbidden_snippets:
        assert snippet not in handler, f"forbidden wiring: {snippet}"
    assert "preview_index_retention" in handler
    assert "asyncio.to_thread" in handler


def test_admin_rollback_success_uses_jwt_tenant_ignores_foreign_query(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_rollback(monkeypatch)
    _install_audit(monkeypatch)

    response = client_with_key.post(
        f"{_ROLLBACK_ENDPOINT}?tenant_id=foreign",
        headers=_admin_headers("acme", sub="ops-admin"),
        json=_ROLLBACK_BODY,
    )

    assert response.status_code == 200
    body = response.json()
    assert body == _expected_rollback_response()
    assert "store" not in body
    assert "chunks" not in body
    assert "applied" not in body
    assert calls == [
        {
            "tenant_id": "acme",
            "embeddings": None,
            "expected_generation": 4,
            "target_collection": _ROLLBACK_TARGET,
        }
    ]


def test_admin_rollback_idempotent_retry_same_response_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_rollback(monkeypatch)
    audit_calls = _install_audit(monkeypatch)
    headers = _admin_headers("acme", sub="retry-admin")

    first = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=headers,
        json=_ROLLBACK_BODY,
    )
    second = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=headers,
        json=_ROLLBACK_BODY,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json() == _expected_rollback_response()
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert len(audit_calls) == 2
    assert all(entry["detail"]["outcome"] == "success" for entry in audit_calls)


def test_admin_rollback_success_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_rollback(monkeypatch)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=_admin_headers("acme", sub="audit-admin"),
        json=_ROLLBACK_BODY,
    )

    assert response.status_code == 200
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "audit-admin"
    assert entry["action"] == "index_rollback"
    assert entry["resource"] == "index/rollback"
    assert entry["tenant_id"] == "acme"
    assert entry["ip_address"] is not None
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": "success",
        "expected_generation": 4,
        "target_collection": _ROLLBACK_TARGET,
        "manifest_generation": 5,
        "active_collection": _ROLLBACK_TARGET,
        "status": "active",
    }


@pytest.mark.parametrize(
    ("headers", "status_code"),
    [
        (None, 401),
        (_role_headers("agent"), 403),
        (_role_headers("viewer"), 403),
    ],
)
def test_admin_rollback_auth_failures_skip_runtime_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    headers: dict[str, str] | None,
    status_code: int,
) -> None:
    calls = _install_rollback(monkeypatch)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=headers or {},
        json=_ROLLBACK_BODY,
    )

    assert response.status_code == status_code
    assert calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"expected_generation": 4},
        {"target_collection": _ROLLBACK_TARGET},
        {"expected_generation": True, "target_collection": _ROLLBACK_TARGET},
        {"expected_generation": "4", "target_collection": _ROLLBACK_TARGET},
        {"expected_generation": 4, "target_collection": 123},
        {
            "expected_generation": 4,
            "target_collection": _ROLLBACK_TARGET,
            "tenant_id": "foreign",
        },
    ],
)
def test_admin_rollback_invalid_body_is_422_without_runtime_or_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    payload: dict[str, Any],
) -> None:
    calls = _install_rollback(monkeypatch)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=_admin_headers("acme"),
        json=payload,
    )

    assert response.status_code == 422
    assert calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_generation": 0, "target_collection": _ROLLBACK_TARGET},
        {"expected_generation": -1, "target_collection": _ROLLBACK_TARGET},
        {"expected_generation": 4, "target_collection": ""},
    ],
)
def test_admin_rollback_semantic_invalid_maps_to_400_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    payload: dict[str, Any],
) -> None:
    from vectordb.index_operator import IndexRollbackValidationError

    calls = _install_rollback(
        monkeypatch,
        side_effect=IndexRollbackValidationError("invalid rollback command"),
    )
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=_admin_headers("acme", sub="fail-admin"),
        json=payload,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid index rollback command"}
    assert "invalid rollback command" not in response.text
    assert len(calls) == 1
    assert calls[0]["expected_generation"] == payload["expected_generation"]
    assert calls[0]["target_collection"] == payload["target_collection"]
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["action"] == "index_rollback"
    assert entry["resource"] == "index/rollback"
    assert entry["tenant_id"] == "acme"
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": "rejected",
        "expected_generation": payload["expected_generation"],
        "target_collection": payload["target_collection"],
        "error_type": "IndexRollbackValidationError",
    }


@pytest.mark.parametrize(
    ("exc_factory", "status_code", "detail", "outcome", "error_type"),
    [
        (
            lambda: __import__(
                "vectordb.index_operator", fromlist=["IndexRollbackConflict"]
            ).IndexRollbackConflict("generation mismatch"),
            409,
            "index rollback conflicts with current state",
            "conflict",
            "IndexRollbackConflict",
        ),
        (
            lambda: __import__(
                "vectordb.index_manifest",
                fromlist=["IndexManifestRollbackUnavailable"],
            ).IndexManifestRollbackUnavailable("no previous"),
            409,
            "index rollback is unavailable",
            "unavailable",
            "IndexManifestRollbackUnavailable",
        ),
        (
            lambda: __import__(
                "vectordb.index_manifest", fromlist=["IndexManifestCorrupt"]
            ).IndexManifestCorrupt("manifest corrupt"),
            409,
            "index manifest is corrupt",
            "metadata_corrupt",
            "IndexManifestCorrupt",
        ),
        (
            lambda: __import__(
                "vectordb.index_staging", fromlist=["IndexStagingValidationError"]
            ).IndexStagingValidationError("target invalid"),
            409,
            "index rollback target validation failed",
            "target_invalid",
            "IndexStagingValidationError",
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockTimeout"]
            ).TenantIndexLockTimeout("lock timeout"),
            503,
            "index rollback is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockTimeout",
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockUnavailable"]
            ).TenantIndexLockUnavailable("lock unavailable"),
            503,
            "index rollback is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockUnavailable",
        ),
    ],
)
def test_admin_rollback_typed_failures_map_to_safe_http_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    exc_factory: Any,
    status_code: int,
    detail: str,
    outcome: str,
    error_type: str,
) -> None:
    side_effect = exc_factory()
    _install_rollback(monkeypatch, side_effect=side_effect)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _ROLLBACK_ENDPOINT,
        headers=_admin_headers("acme", sub="fail-admin"),
        json=_ROLLBACK_BODY,
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    body_text = response.text
    assert "generation mismatch" not in body_text
    assert "no previous" not in body_text
    assert "manifest corrupt" not in body_text
    assert "target invalid" not in body_text
    assert "lock timeout" not in body_text
    assert "lock unavailable" not in body_text
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "fail-admin"
    assert entry["action"] == "index_rollback"
    assert entry["resource"] == "index/rollback"
    assert entry["tenant_id"] == "acme"
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": outcome,
        "expected_generation": 4,
        "target_collection": _ROLLBACK_TARGET,
        "error_type": error_type,
    }
    assert set(entry["detail"]) == {
        "tenant",
        "outcome",
        "expected_generation",
        "target_collection",
        "error_type",
    }


def test_admin_rollback_unrelated_exception_is_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_rollback(monkeypatch, side_effect=RuntimeError("boom-internal"))
    audit_calls = _install_audit(monkeypatch)

    with pytest.raises(RuntimeError, match="boom-internal"):
        client_with_key.post(
            _ROLLBACK_ENDPOINT,
            headers=_admin_headers("acme"),
            json=_ROLLBACK_BODY,
        )

    assert audit_calls == []


def test_admin_rollback_route_is_post_only_and_uses_to_thread() -> None:
    source = Path("api/routers/admin_ops.py").read_text(encoding="utf-8")
    start = source.index('@router.post("/admin/index/rollback")')
    handler = source[start:]

    assert '@router.get("/admin/index/rollback")' not in source
    assert "asyncio.to_thread" in handler
    assert "rollback_vector_store" in handler
    # Tenant must not be a declared path/query/body override.
    signature_slice = handler.split(":", 1)[0]
    assert "tenant_id" not in signature_slice
    assert "IndexRollbackRequest" in handler


def test_admin_rollback_get_is_405(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_rollback(monkeypatch)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        _ROLLBACK_ENDPOINT,
        headers=_admin_headers("acme"),
    )

    assert response.status_code == 405
    assert calls == []
    assert audit_calls == []


def test_admin_rollback_handler_boundary_only_uses_manager_runtime() -> None:
    source = Path("api/routers/admin_ops.py").read_text(encoding="utf-8")
    start = source.index('@router.post("/admin/index/rollback")')
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
        "rollback_index_version",
        "record_retention_collection",
        "preview_index_retention",
        "_store_cache",
        "_chunks_cache",
        "_index_cache_keys",
    )
    for snippet in forbidden_snippets:
        assert snippet not in handler, f"forbidden wiring: {snippet}"
    assert "rollback_vector_store" in handler
    assert "asyncio.to_thread" in handler


# ---------------------------------------------------------------------------
# Admin retention execution (plan 2.3i)
# ---------------------------------------------------------------------------

_RETENTION_ENDPOINT = "/api/admin/index/retention"
_RETENTION_CANDIDATES = (
    "acme__v0000000000000001",
    "acme__v0000000000000002",
)
_RETENTION_BODY = {
    "expected_generation": 4,
    "expected_candidates": list(_RETENTION_CANDIDATES),
}


def _sample_retention_result(
    *,
    tenant_id: str = "acme",
    max_versions: int = 3,
    expected_generation: int = 4,
    expected_candidates: tuple[str, ...] = _RETENTION_CANDIDATES,
    deleted_collections: tuple[str, ...] | None = None,
) -> Any:
    from vectordb.index_operator import IndexRetentionExecutionResult

    deleted = (
        expected_candidates if deleted_collections is None else deleted_collections
    )
    return IndexRetentionExecutionResult(
        tenant_id=tenant_id,
        max_versions=max_versions,
        expected_generation=expected_generation,
        expected_candidates=expected_candidates,
        deleted_collections=deleted,
    )


def _install_retention(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: Any | None = None,
    side_effect: BaseException | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recorded = calls if calls is not None else []

    def _fake_retention(
        tenant_id: str = "default",
        *,
        expected_generation: int,
        expected_candidates: tuple[str, ...],
    ) -> Any:
        recorded.append(
            {
                "tenant_id": tenant_id,
                "expected_generation": expected_generation,
                "expected_candidates": expected_candidates,
            }
        )
        if side_effect is not None:
            raise side_effect
        if result is not None:
            return result
        return _sample_retention_result(
            tenant_id=tenant_id,
            expected_generation=expected_generation,
            expected_candidates=expected_candidates,
        )

    monkeypatch.setattr(
        "vectordb.manager.execute_vector_store_retention",
        _fake_retention,
    )
    return recorded


def _expected_retention_response(
    *,
    tenant_id: str = "acme",
    max_versions: int = 3,
    expected_generation: int = 4,
    expected_candidates: tuple[str, ...] = _RETENTION_CANDIDATES,
    deleted_collections: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    deleted = (
        expected_candidates if deleted_collections is None else deleted_collections
    )
    return {
        "status": "complete",
        "tenant_id": tenant_id,
        "max_versions": max_versions,
        "expected_generation": expected_generation,
        "expected_candidates": list(expected_candidates),
        "deleted_collections": list(deleted),
    }


def test_admin_retention_execution_success_uses_jwt_tenant_ignores_foreign_query(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_retention(
        monkeypatch,
        result=_sample_retention_result(),
    )
    _install_audit(monkeypatch)

    response = client_with_key.post(
        f"{_RETENTION_ENDPOINT}?tenant_id=foreign&max_versions=99",
        headers=_admin_headers("acme", sub="ops-admin"),
        json=_RETENTION_BODY,
    )

    assert response.status_code == 200
    body = response.json()
    assert body == _expected_retention_response()
    assert "store" not in body
    assert "chunks" not in body
    assert "chroma" not in body
    assert calls == [
        {
            "tenant_id": "acme",
            "expected_generation": 4,
            "expected_candidates": _RETENTION_CANDIDATES,
        }
    ]


@pytest.mark.parametrize(
    ("headers", "status_code"),
    [
        (None, 401),
        (_role_headers("agent"), 403),
        (_role_headers("viewer"), 403),
    ],
)
def test_admin_retention_execution_auth_failures_skip_runtime_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    headers: dict[str, str] | None,
    status_code: int,
) -> None:
    calls = _install_retention(monkeypatch, result=_sample_retention_result())
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _RETENTION_ENDPOINT,
        headers=headers or {},
        json=_RETENTION_BODY,
    )

    assert response.status_code == status_code
    assert calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"expected_generation": 4},
        {"expected_candidates": list(_RETENTION_CANDIDATES)},
        {"expected_generation": True, "expected_candidates": list(_RETENTION_CANDIDATES)},
        {"expected_generation": "4", "expected_candidates": list(_RETENTION_CANDIDATES)},
        {"expected_generation": 4, "expected_candidates": "not-a-list"},
        {"expected_generation": 4, "expected_candidates": [1, 2]},
        {"expected_generation": 4, "expected_candidates": [True]},
        {
            "expected_generation": 4,
            "expected_candidates": list(_RETENTION_CANDIDATES),
            "tenant_id": "foreign",
        },
        {
            "expected_generation": 4,
            "expected_candidates": list(_RETENTION_CANDIDATES),
            "max_versions": 2,
        },
        {
            "expected_generation": 4,
            "expected_candidates": list(_RETENTION_CANDIDATES),
            "chroma_directory": "/tmp/chroma",
        },
    ],
)
def test_admin_retention_execution_invalid_body_is_422_without_runtime_or_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    payload: dict[str, Any],
) -> None:
    calls = _install_retention(monkeypatch, result=_sample_retention_result())
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _RETENTION_ENDPOINT,
        headers=_admin_headers("acme"),
        json=payload,
    )

    assert response.status_code == 422
    assert calls == []
    assert audit_calls == []


def test_admin_retention_execution_forwards_exact_command_and_safe_success(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    expected = _sample_retention_result(
        max_versions=3,
        expected_candidates=_RETENTION_CANDIDATES,
        deleted_collections=_RETENTION_CANDIDATES,
    )
    calls = _install_retention(monkeypatch, result=expected)
    _install_audit(monkeypatch)

    response = client_with_key.post(
        _RETENTION_ENDPOINT,
        headers=_admin_headers("acme", sub="ops-admin"),
        json=_RETENTION_BODY,
    )

    assert response.status_code == 200
    assert response.json() == _expected_retention_response()
    assert calls == [
        {
            "tenant_id": "acme",
            "expected_generation": 4,
            "expected_candidates": _RETENTION_CANDIDATES,
        }
    ]
    # Manager call must receive an exact ordered tuple, not a list.
    assert isinstance(calls[0]["expected_candidates"], tuple)


def test_admin_retention_execution_empty_candidates_and_repeatable(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    empty_result = _sample_retention_result(
        expected_candidates=(),
        deleted_collections=(),
    )
    calls = _install_retention(monkeypatch, result=empty_result)
    audit_calls = _install_audit(monkeypatch)
    headers = _admin_headers("acme", sub="retry-admin")
    body = {"expected_generation": 4, "expected_candidates": []}

    first = client_with_key.post(_RETENTION_ENDPOINT, headers=headers, json=body)
    second = client_with_key.post(_RETENTION_ENDPOINT, headers=headers, json=body)

    expected = _expected_retention_response(
        expected_candidates=(),
        deleted_collections=(),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json() == expected
    assert len(calls) == 2
    assert calls[0] == calls[1] == {
        "tenant_id": "acme",
        "expected_generation": 4,
        "expected_candidates": (),
    }
    assert len(audit_calls) == 2
    assert all(entry["detail"]["outcome"] == "success" for entry in audit_calls)
    assert audit_calls[0]["detail"] == audit_calls[1]["detail"]


def test_admin_retention_execution_success_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_retention(
        monkeypatch,
        result=_sample_retention_result(deleted_collections=_RETENTION_CANDIDATES),
    )
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _RETENTION_ENDPOINT,
        headers=_admin_headers("acme", sub="audit-admin"),
        json=_RETENTION_BODY,
    )

    assert response.status_code == 200
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "audit-admin"
    assert entry["action"] == "index_retention"
    assert entry["resource"] == "index/retention"
    assert entry["tenant_id"] == "acme"
    assert entry["ip_address"] is not None
    assert entry["detail"] == {
        "tenant": "acme",
        "outcome": "success",
        "expected_generation": 4,
        "expected_candidates": list(_RETENTION_CANDIDATES),
        "max_versions": 3,
        "deleted_collections": list(_RETENTION_CANDIDATES),
        "deleted_count": 2,
        "status": "complete",
    }


@pytest.mark.parametrize(
    ("exc_factory", "status_code", "detail", "outcome", "error_type", "extra_body", "extra_audit"),
    [
        (
            lambda: __import__(
                "vectordb.index_operator",
                fromlist=["IndexRetentionExecutionValidationError"],
            ).IndexRetentionExecutionValidationError("expected_generation must be positive"),
            400,
            "invalid index retention command",
            "rejected",
            "IndexRetentionExecutionValidationError",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_retention",
                fromlist=["IndexRetentionValidationError"],
            ).IndexRetentionValidationError("max_versions must be >= 2"),
            400,
            "invalid index retention command",
            "rejected",
            "IndexRetentionValidationError",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_operator",
                fromlist=["IndexRetentionExecutionConflict"],
            ).IndexRetentionExecutionConflict("generation mismatch"),
            409,
            "index retention conflicts with current state",
            "conflict",
            "IndexRetentionExecutionConflict",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_retention", fromlist=["IndexRetentionCorrupt"]
            ).IndexRetentionCorrupt("inventory corrupt"),
            409,
            "index retention metadata is corrupt",
            "metadata_corrupt",
            "IndexRetentionCorrupt",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_manifest", fromlist=["IndexManifestCorrupt"]
            ).IndexManifestCorrupt("manifest corrupt"),
            409,
            "index retention metadata is corrupt",
            "metadata_corrupt",
            "IndexManifestCorrupt",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_staging", fromlist=["IndexStagingValidationError"]
            ).IndexStagingValidationError("qdrant unavailable"),
            409,
            "index retention is unavailable",
            "unavailable",
            "IndexStagingValidationError",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockTimeout"]
            ).TenantIndexLockTimeout("lock timeout"),
            503,
            "index retention is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockTimeout",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.tenant_lock", fromlist=["TenantIndexLockUnavailable"]
            ).TenantIndexLockUnavailable("lock unavailable"),
            503,
            "index retention is temporarily unavailable",
            "lock_unavailable",
            "TenantIndexLockUnavailable",
            {},
            {},
        ),
        (
            lambda: __import__(
                "vectordb.index_retention", fromlist=["IndexRetentionDeletionError"]
            ).IndexRetentionDeletionError(
                failed_collection="acme__v0000000000000001",
                deleted_collections=(),
            ),
            503,
            "index retention deletion failed",
            "deletion_failed",
            "IndexRetentionDeletionError",
            {
                "failed_collection": "acme__v0000000000000001",
                "deleted_collections": [],
            },
            {
                "failed_collection": "acme__v0000000000000001",
                "deleted_collections": [],
            },
        ),
        (
            lambda: __import__(
                "vectordb.index_retention",
                fromlist=["IndexRetentionMetadataUpdateError"],
            ).IndexRetentionMetadataUpdateError(
                deleted_collection="acme__v0000000000000001",
                deleted_collections=("acme__v0000000000000001",),
            ),
            503,
            "index retention metadata update failed",
            "metadata_update_failed",
            "IndexRetentionMetadataUpdateError",
            {
                "deleted_collection": "acme__v0000000000000001",
                "deleted_collections": ["acme__v0000000000000001"],
            },
            {
                "deleted_collection": "acme__v0000000000000001",
                "deleted_collections": ["acme__v0000000000000001"],
            },
        ),
    ],
)
def test_admin_retention_execution_typed_failures_map_to_safe_http_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    exc_factory: Any,
    status_code: int,
    detail: str,
    outcome: str,
    error_type: str,
    extra_body: dict[str, Any],
    extra_audit: dict[str, Any],
) -> None:
    side_effect = exc_factory()
    _install_retention(monkeypatch, side_effect=side_effect)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.post(
        _RETENTION_ENDPOINT,
        headers=_admin_headers("acme", sub="fail-admin"),
        json=_RETENTION_BODY,
    )

    assert response.status_code == status_code
    body = response.json()
    assert body["detail"] == detail
    for key, value in extra_body.items():
        assert body[key] == value
    body_text = response.text
    assert "expected_generation must be positive" not in body_text
    assert "max_versions must" not in body_text
    assert "generation mismatch" not in body_text
    assert "inventory corrupt" not in body_text
    assert "manifest corrupt" not in body_text
    assert "qdrant unavailable" not in body_text
    assert "lock timeout" not in body_text
    assert "lock unavailable" not in body_text
    assert "Index retention collection deletion failed" not in body_text
    assert "Index retention metadata update failed" not in body_text
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "fail-admin"
    assert entry["action"] == "index_retention"
    assert entry["resource"] == "index/retention"
    assert entry["tenant_id"] == "acme"
    expected_detail = {
        "tenant": "acme",
        "outcome": outcome,
        "expected_generation": 4,
        "expected_candidates": list(_RETENTION_CANDIDATES),
        "error_type": error_type,
        **extra_audit,
    }
    assert entry["detail"] == expected_detail


def test_admin_retention_execution_unrelated_exception_is_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_retention(monkeypatch, side_effect=RuntimeError("boom-internal"))
    audit_calls = _install_audit(monkeypatch)

    with pytest.raises(RuntimeError, match="boom-internal"):
        client_with_key.post(
            _RETENTION_ENDPOINT,
            headers=_admin_headers("acme"),
            json=_RETENTION_BODY,
        )

    assert audit_calls == []


def test_admin_retention_execution_route_is_post_only_and_uses_to_thread() -> None:
    source = Path("api/routers/admin_ops.py").read_text(encoding="utf-8")
    start = source.index('@router.post("/admin/index/retention")')
    handler = source[start:]

    assert '@router.get("/admin/index/retention")' not in source
    assert "asyncio.to_thread" in handler
    assert "execute_vector_store_retention" in handler
    assert "IndexRetentionExecutionRequest" in handler
    signature_slice = handler.split(":", 1)[0]
    assert "tenant_id" not in signature_slice


def test_admin_retention_execution_get_is_405(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    calls = _install_retention(monkeypatch, result=_sample_retention_result())
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        _RETENTION_ENDPOINT,
        headers=_admin_headers("acme"),
    )

    assert response.status_code == 405
    assert calls == []
    assert audit_calls == []


def test_admin_retention_execution_handler_boundary_only_uses_manager_runtime() -> None:
    source = Path("api/routers/admin_ops.py").read_text(encoding="utf-8")
    start = source.index('@router.post("/admin/index/retention")')
    handler = source[start:]

    forbidden_snippets = (
        "chromadb",
        "PersistentClient",
        "list_collections",
        "get_or_create_collection",
        "delete_collection",
        "execute_chroma_retention",
        "execute_bounded_retention",
        "execute_guarded_chroma_retention",
        "publish_active_collection",
        "rollback_active_collection",
        "rollback_index_version",
        "record_retention_collection",
        "preview_index_retention",
        "execute_index_retention",
        "read_index_manifest",
        "read_retention_inventory",
        "bounded_retention_candidates",
        "tenant_index_lock",
        "get_settings",
        "_store_cache",
        "_chunks_cache",
        "_index_cache_keys",
        "embeddings",
    )
    for snippet in forbidden_snippets:
        assert snippet not in handler, f"forbidden wiring: {snippet}"
    assert "execute_vector_store_retention" in handler
    assert "asyncio.to_thread" in handler

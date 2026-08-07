"""Admin HTTP surface for job-object inventory preview (plan 2.5a).

Read-only: JWT tenant scope, audit trail, no retention execute, no FS mutation.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token
from ingestion.job_object_inventory import JobObjectInventoryEntry
from ingestion.job_object_operator import OperatorPreviewReport
from ingestion.job_object_orphans import JobObjectTransitionAnnotation
from ingestion.job_object_retention import (
    JobObjectRetentionAssessment,
    JobObjectRetentionDisposition,
)

_ENDPOINT = "/api/admin/job-objects/inventory"


def _admin_headers(tenant: str = "acme", sub: str = "admin-user") -> dict[str, str]:
    token = create_access_token(sub, "admin", tenant)
    return {"Authorization": f"Bearer {token}"}


def _role_headers(role: str, tenant: str = "acme") -> dict[str, str]:
    token = create_access_token(f"{role}-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def _sample_report(*, tenant_id: str = "acme") -> OperatorPreviewReport:
    job_id = str(uuid.uuid4())
    entry = JobObjectInventoryEntry(
        relative_path=f"job-objects/{job_id}/doc.md",
        kind="job_object",
        classification="protected",
        job_id=job_id,
    )
    assessment = JobObjectRetentionAssessment(
        dispositions=(
            JobObjectRetentionDisposition(
                relative_path=entry.relative_path,
                classification=entry.classification,
                disposition="never_auto_delete",
                reason="protected_job_object",
            ),
        ),
        auto_delete_candidates=(),
    )
    note = JobObjectTransitionAnnotation(
        relative_path=entry.relative_path,
        classification=entry.classification,
        kind=entry.kind,
        job_id=job_id,
        job_status="failed",
        ownership="retained_after_failed_transition",
        auto_delete_eligible=False,
    )
    return OperatorPreviewReport(
        tenant_id=tenant_id,
        upload_dir=f"/tmp/uploads/{tenant_id}",
        known_job_count=1,
        inventory_entries=(entry,),
        assessment=assessment,
        execution=None,
        transition_annotations=(note,),
    )


def _install_preview(
    monkeypatch: pytest.MonkeyPatch,
    *,
    report: OperatorPreviewReport | None = None,
    side_effect: BaseException | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    recorded = calls if calls is not None else []

    def _fake_load_and_run(
        *,
        tenant_id: str,
        project_root: Path | str,
        upload_root: Path | str,
        execute: bool = False,
    ) -> OperatorPreviewReport:
        recorded.append(
            {
                "tenant_id": tenant_id,
                "project_root": str(project_root),
                "upload_root": str(upload_root),
                "execute": execute,
            }
        )
        if side_effect is not None:
            raise side_effect
        assert report is not None
        return report

    monkeypatch.setattr(
        "ingestion.job_object_operator.load_and_run_operator_preview",
        _fake_load_and_run,
    )
    return recorded


def _install_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    audit_calls: list[dict[str, Any]] = []

    async def _fake_log_audit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)
    return audit_calls


def test_admin_success_uses_jwt_tenant_and_never_executes(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    expected = _sample_report(tenant_id="acme")
    calls = _install_preview(monkeypatch, report=expected)
    _install_audit(monkeypatch)

    response = client_with_key.get(
        f"{_ENDPOINT}?tenant_id=foreign",
        headers=_admin_headers("acme", sub="ops-admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "acme"
    assert body["known_job_count"] == 1
    assert body["auto_delete_candidates"] == []
    assert len(body["transition_annotations"]) == 1
    note = body["transition_annotations"][0]
    assert note["ownership"] == "retained_after_failed_transition"
    assert note["auto_delete_eligible"] is False
    assert "execution" not in body
    assert calls == [
        {
            "tenant_id": "acme",
            "project_root": calls[0]["project_root"],
            "upload_root": calls[0]["upload_root"],
            "execute": False,
        }
    ]
    assert calls[0]["execute"] is False
    assert calls[0]["tenant_id"] == "acme"
    assert calls[0]["tenant_id"] != "foreign"


def test_success_audit_includes_summary(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    report = _sample_report(tenant_id="acme")
    _install_preview(monkeypatch, report=report)
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(
        _ENDPOINT,
        headers=_admin_headers("acme", sub="audit-admin"),
    )

    assert response.status_code == 200
    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["actor"] == "audit-admin"
    assert entry["action"] == "job_object_inventory_preview"
    assert entry["resource"] == "job-objects/inventory"
    assert entry["tenant_id"] == "acme"
    assert entry["detail"]["outcome"] == "success"
    assert entry["detail"]["known_job_count"] == 1
    assert entry["detail"]["inventory_count"] == 1
    assert entry["detail"]["auto_delete_candidates"] == []
    assert entry["detail"]["annotation_count"] == 1


@pytest.mark.parametrize(
    ("headers", "status_code"),
    [
        (_role_headers("user"), 403),
        (_role_headers("analyst"), 403),
        ({}, 401),
    ],
)
def test_non_admin_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    headers: dict[str, str],
    status_code: int,
) -> None:
    _install_preview(monkeypatch, report=_sample_report())
    _install_audit(monkeypatch)

    response = client_with_key.get(_ENDPOINT, headers=headers)
    assert response.status_code == status_code


def test_validation_error_returns_400_and_audits(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    from ingestion.job_object_inventory import JobObjectInventoryValidationError

    _install_preview(
        monkeypatch,
        side_effect=JobObjectInventoryValidationError("upload_dir must resolve under project_root"),
    )
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(_ENDPOINT, headers=_admin_headers("acme"))
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid job-object inventory preview"
    assert audit_calls[-1]["detail"]["outcome"] == "rejected"


def test_os_error_returns_503_and_audits(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    _install_preview(monkeypatch, side_effect=OSError("disk offline"))
    audit_calls = _install_audit(monkeypatch)

    response = client_with_key.get(_ENDPOINT, headers=_admin_headers("acme"))
    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "job-object inventory preview is temporarily unavailable"
    )
    assert audit_calls[-1]["detail"]["outcome"] == "unavailable"


def test_endpoint_does_not_accept_execute_mutation_surface(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    """Read-only contract: even if a client sends execute-like query, no execute."""
    calls = _install_preview(monkeypatch, report=_sample_report())
    _install_audit(monkeypatch)

    response = client_with_key.get(
        f"{_ENDPOINT}?execute=true",
        headers=_admin_headers("acme"),
    )
    assert response.status_code == 200
    assert calls[0]["execute"] is False
    assert "execution" not in response.json()

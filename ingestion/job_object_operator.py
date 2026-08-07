"""Tenant job-object operator composition (plan 2.4i/2.4k/2.5a).

Shared by the operator CLI and the read-only admin HTTP surface. Composes
inventory classify → fail-closed retention policy → optional guarded no-op
→ failed-transition ownership annotations.

Never invents auto-delete classes or age/budget thresholds. Under the current
policy, execute is a no-op (deleted=()) with no filesystem mutation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from ingestion.job_object_inventory import (
    JobObjectInventoryEntry,
    JobObjectInventoryPreview,
    KnownJobObjectRef,
    preview_tenant_job_object_inventory,
)
from ingestion.job_object_orphans import (
    JobObjectTransitionAnnotation,
    annotate_job_object_transition_context,
)
from ingestion.job_object_retention import (
    JobObjectRetentionAssessment,
    JobObjectRetentionExecutionResult,
    assess_job_object_retention_policy,
    execute_job_object_retention,
)
from utils.tenant_naming import physical_tenant_component


def upload_dir_for_tenant(upload_root: Path, tenant_id: str) -> Path:
    """Resolve the tenant-scoped upload directory under ``upload_root``."""
    tid = (tenant_id or "").strip() or "default"
    if tid == "default":
        return upload_root
    return upload_root / physical_tenant_component(tid, max_length=63)


@dataclass(frozen=True)
class OperatorPreviewReport:
    """Structured operator report for one tenant (read-only + optional no-op)."""

    tenant_id: str
    upload_dir: str
    known_job_count: int
    inventory_entries: tuple[JobObjectInventoryEntry, ...]
    assessment: JobObjectRetentionAssessment
    execution: JobObjectRetentionExecutionResult | None
    transition_annotations: tuple[JobObjectTransitionAnnotation, ...]


def run_operator_preview(
    *,
    tenant_id: str,
    project_root: Path | str,
    upload_root: Path | str,
    known_jobs: Sequence[KnownJobObjectRef],
    job_statuses: Mapping[str, str] | None = None,
    execute: bool = False,
) -> OperatorPreviewReport:
    """Compose load→preview→policy→optional guarded no-op→annotations.

    ``known_jobs`` and ``job_statuses`` are supplied by the caller (CLI/HTTP
    load from DB; tests inject). This function never deletes or rewrites
    filesystem state when ``execute`` is False; under current policy even
    ``execute=True`` yields deleted=().
    """
    root = Path(project_root)
    upload_base = Path(upload_root)
    upload_dir = upload_dir_for_tenant(upload_base, tenant_id)
    preview: JobObjectInventoryPreview = preview_tenant_job_object_inventory(
        upload_dir,
        tenant_id=tenant_id,
        known_jobs=known_jobs,
        project_root=root,
    )
    assessment = assess_job_object_retention_policy(preview.entries)
    execution: JobObjectRetentionExecutionResult | None = None
    if execute:
        execution = execute_job_object_retention(
            tenant_id=preview.tenant_id,
            entries=preview.entries,
            expected_candidates=assessment.auto_delete_candidates,
        )
    statuses = dict(job_statuses or {})
    annotations = annotate_job_object_transition_context(
        preview.entries,
        job_statuses=statuses,
    )
    return OperatorPreviewReport(
        tenant_id=preview.tenant_id,
        upload_dir=str(upload_dir),
        known_job_count=preview.known_job_count,
        inventory_entries=preview.entries,
        assessment=assessment,
        execution=execution,
        transition_annotations=annotations,
    )


def load_and_run_operator_preview(
    *,
    tenant_id: str,
    project_root: Path | str,
    upload_root: Path | str,
    execute: bool = False,
) -> OperatorPreviewReport:
    """Load durable job refs + statuses from DB, then compose the report.

    Read-only DB access only. ``execute`` is always a no-op under current
    fail-closed policy. Prefer ``run_operator_preview`` with injected data
    in unit tests.
    """
    from ingestion.jobs import (
        sync_list_job_statuses_for_tenant,
        sync_list_known_job_object_refs,
    )

    known = sync_list_known_job_object_refs(tenant_id)
    statuses = sync_list_job_statuses_for_tenant(tenant_id)
    return run_operator_preview(
        tenant_id=tenant_id,
        project_root=project_root,
        upload_root=upload_root,
        known_jobs=known,
        job_statuses=statuses,
        execute=execute,
    )


def report_to_jsonable(report: OperatorPreviewReport) -> dict:
    """Serialize an operator report for CLI JSON or HTTP response bodies."""
    entries = [
        {
            "relative_path": e.relative_path,
            "kind": e.kind,
            "classification": e.classification,
            "job_id": e.job_id,
        }
        for e in report.inventory_entries
    ]
    dispositions = [asdict(d) for d in report.assessment.dispositions]
    annotations = [asdict(a) for a in report.transition_annotations]
    payload: dict = {
        "tenant_id": report.tenant_id,
        "upload_dir": report.upload_dir,
        "known_job_count": report.known_job_count,
        "inventory_entries": entries,
        "auto_delete_candidates": list(report.assessment.auto_delete_candidates),
        "dispositions": dispositions,
        "transition_annotations": annotations,
        "execution": None,
    }
    if report.execution is not None:
        payload["execution"] = {
            "tenant_id": report.execution.tenant_id,
            "expected_candidates": list(report.execution.expected_candidates),
            "deleted": list(report.execution.deleted),
            "status": report.execution.status,
        }
    return payload

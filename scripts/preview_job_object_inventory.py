# ruff: noqa: E402
#!/usr/bin/env python3
"""Operator CLI for job-object inventory + retention policy (plan 2.4i).

For one tenant: load known job refs (or accept injected refs in tests),
preview/classify the job-objects tree, assess fail-closed retention policy,
and optionally run the guarded empty-candidate no-op command.

Never invents auto-delete classes or age/budget thresholds. Under the current
policy execution is always a no-op with deleted=() and no filesystem mutation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.job_object_inventory import (
    JobObjectInventoryEntry,
    JobObjectInventoryPreview,
    JobObjectInventoryValidationError,
    KnownJobObjectRef,
    preview_tenant_job_object_inventory,
)
from ingestion.job_object_retention import (
    JobObjectRetentionAssessment,
    JobObjectRetentionError,
    JobObjectRetentionExecutionResult,
    assess_job_object_retention_policy,
    execute_job_object_retention,
)
from utils.tenant_naming import physical_tenant_component


def _upload_dir_for_tenant(upload_root: Path, tenant_id: str) -> Path:
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


def run_operator_preview(
    *,
    tenant_id: str,
    project_root: Path | str,
    upload_root: Path | str,
    known_jobs: Sequence[KnownJobObjectRef],
    execute: bool = False,
) -> OperatorPreviewReport:
    """Compose load→preview→policy→optional guarded no-op for one tenant.

    ``known_jobs`` is supplied by the caller (CLI loads from DB; tests inject).
    This function never deletes or rewrites filesystem state.
    """
    root = Path(project_root)
    upload_base = Path(upload_root)
    upload_dir = _upload_dir_for_tenant(upload_base, tenant_id)
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
    return OperatorPreviewReport(
        tenant_id=preview.tenant_id,
        upload_dir=str(upload_dir),
        known_job_count=preview.known_job_count,
        inventory_entries=preview.entries,
        assessment=assessment,
        execution=execution,
    )


def _default_load_known_jobs(tenant_id: str) -> tuple[KnownJobObjectRef, ...]:
    from ingestion.jobs import sync_list_known_job_object_refs

    return sync_list_known_job_object_refs(tenant_id)


def _report_to_jsonable(report: OperatorPreviewReport) -> dict:
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
    payload: dict = {
        "tenant_id": report.tenant_id,
        "upload_dir": report.upload_dir,
        "known_job_count": report.known_job_count,
        "inventory_entries": entries,
        "auto_delete_candidates": list(report.assessment.auto_delete_candidates),
        "dispositions": dispositions,
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


def _print_human(report: OperatorPreviewReport) -> None:
    print(f"tenant: {report.tenant_id}")
    print(f"upload_dir: {report.upload_dir}")
    print(f"known_jobs: {report.known_job_count}")
    print(f"inventory_entries: {len(report.inventory_entries)}")
    for entry in report.inventory_entries:
        jid = entry.job_id or "-"
        print(
            f"  [{entry.classification}] {entry.kind} "
            f"job={jid} path={entry.relative_path}"
        )
    print(
        f"auto_delete_candidates: {len(report.assessment.auto_delete_candidates)}"
    )
    if report.assessment.auto_delete_candidates:
        for cand in report.assessment.auto_delete_candidates:
            print(f"  candidate: {cand}")
    else:
        print("  (none — current policy is fail-closed)")
    for disp in report.assessment.dispositions:
        print(
            f"  disposition: {disp.disposition} reason={disp.reason} "
            f"class={disp.classification} path={disp.relative_path}"
        )
    if report.execution is not None:
        print(
            f"execution: status={report.execution.status} "
            f"deleted={len(report.execution.deleted)}"
        )
        if report.execution.deleted:
            for path in report.execution.deleted:
                print(f"  deleted: {path}")
        else:
            print("  (no-op; no filesystem mutation)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview tenant job-object inventory and fail-closed retention "
            "policy. Optional --execute runs the guarded empty-candidate "
            "no-op command (no filesystem mutation under current policy)."
        )
    )
    parser.add_argument("--tenant", default="default")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root (default: repository root)",
    )
    parser.add_argument(
        "--upload-root",
        type=Path,
        default=None,
        help="Upload root directory (default: <project-root>/data/uploads)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Run guarded retention with expected_candidates from policy "
            "(empty under current policy → no-op; no FS mutation)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    load_known_jobs: Callable[[str], Sequence[KnownJobObjectRef]] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path(args.project_root) if args.project_root else PROJECT_ROOT
    upload_root = (
        Path(args.upload_root)
        if args.upload_root
        else project_root / "data" / "uploads"
    )
    loader = load_known_jobs or _default_load_known_jobs
    tenant = str(args.tenant or "default")

    try:
        known = tuple(loader(tenant))
        report = run_operator_preview(
            tenant_id=tenant,
            project_root=project_root,
            upload_root=upload_root,
            known_jobs=known,
            execute=bool(args.execute),
        )
    except (JobObjectInventoryValidationError, JobObjectRetentionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_report_to_jsonable(report), ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

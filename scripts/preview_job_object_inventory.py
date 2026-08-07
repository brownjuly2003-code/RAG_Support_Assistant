# ruff: noqa: E402
#!/usr/bin/env python3
"""Operator CLI for job-object inventory + retention policy (plan 2.4i/2.4k/2.5a).

Thin CLI over ``ingestion.job_object_operator``. For one tenant: load known job
refs, preview/classify the job-objects tree, assess fail-closed retention
policy, optionally run the guarded empty-candidate no-op command, and
annotate failed-transition ownership from job statuses.

Never invents auto-delete classes or age/budget thresholds. Under the current
policy execution is always a no-op with deleted=() and no filesystem mutation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.job_object_inventory import (
    JobObjectInventoryValidationError,
    KnownJobObjectRef,
)
from ingestion.job_object_operator import (
    OperatorPreviewReport,
    report_to_jsonable,
    run_operator_preview,
    upload_dir_for_tenant,
)
from ingestion.job_object_orphans import JobObjectOrphanValidationError
from ingestion.job_object_retention import JobObjectRetentionError

# Re-export for tests that import helpers from this module.
_upload_dir_for_tenant = upload_dir_for_tenant
_report_to_jsonable = report_to_jsonable


def _default_load_known_jobs(tenant_id: str) -> tuple[KnownJobObjectRef, ...]:
    from ingestion.jobs import sync_list_known_job_object_refs

    return sync_list_known_job_object_refs(tenant_id)


def _default_load_job_statuses(tenant_id: str) -> dict[str, str]:
    from ingestion.jobs import sync_list_job_statuses_for_tenant

    return sync_list_job_statuses_for_tenant(tenant_id)


def _print_human(report: OperatorPreviewReport) -> None:
    print(f"tenant: {report.tenant_id}")
    print(f"upload_dir: {report.upload_dir}")
    print(f"known_jobs: {report.known_job_count}")
    print(f"inventory_entries: {len(report.inventory_entries)}")
    for entry in report.inventory_entries:
        jid = entry.job_id or "-"
        print(f"  [{entry.classification}] {entry.kind} job={jid} path={entry.relative_path}")
    print(f"auto_delete_candidates: {len(report.assessment.auto_delete_candidates)}")
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
    print(f"transition_annotations: {len(report.transition_annotations)}")
    for note in report.transition_annotations:
        jstatus = note.job_status if note.job_status is not None else "-"
        print(
            f"  ownership={note.ownership} job_status={jstatus} "
            f"eligible={note.auto_delete_eligible} path={note.relative_path}"
        )
    if report.execution is not None:
        print(
            f"execution: status={report.execution.status} deleted={len(report.execution.deleted)}"
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
            "no-op command (no filesystem mutation under current policy). "
            "Includes failed-transition ownership annotations from job statuses."
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
    load_job_statuses: Callable[[str], Mapping[str, str]] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path(args.project_root) if args.project_root else PROJECT_ROOT
    upload_root = Path(args.upload_root) if args.upload_root else project_root / "data" / "uploads"
    loader = load_known_jobs or _default_load_known_jobs
    status_loader = load_job_statuses or _default_load_job_statuses
    tenant = str(args.tenant or "default")

    try:
        known = tuple(loader(tenant))
        statuses = dict(status_loader(tenant))
        report = run_operator_preview(
            tenant_id=tenant,
            project_root=project_root,
            upload_root=upload_root,
            known_jobs=known,
            job_statuses=statuses,
            execute=bool(args.execute),
        )
    except (
        JobObjectInventoryValidationError,
        JobObjectRetentionError,
        JobObjectOrphanValidationError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report_to_jsonable(report), ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

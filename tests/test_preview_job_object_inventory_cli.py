"""Operator CLI for job-object inventory + policy + annotations (2.4i/2.4k).

Composes tenant load → preview → fail-closed policy → optional guarded
no-op execute → transition ownership annotations. Never mutates filesystem
under current empty-candidate policy.
"""

from __future__ import annotations

import importlib
import json
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def _cli() -> ModuleType:
    return importlib.import_module("scripts.preview_job_object_inventory")


def _inv() -> ModuleType:
    return importlib.import_module("ingestion.job_object_inventory")


def _write(path: Path, data: bytes = b"payload") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_upload_dir_for_default_and_non_default_tenant(tmp_path: Path) -> None:
    cli = _cli()
    root = tmp_path / "uploads"
    assert cli._upload_dir_for_tenant(root, "default") == root
    assert cli._upload_dir_for_tenant(root, "  ") == root
    non_default = cli._upload_dir_for_tenant(root, "acme")
    assert non_default != root
    assert non_default.parent == root


def test_run_operator_preview_classifies_and_policy_fail_closed(
    tmp_path: Path,
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "doc.md",
        b"v1",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)
    orphan_id = uuid.uuid4()
    orphan = _write(
        upload_root / "job-objects" / str(orphan_id) / "orphan.md",
        b"orphan",
    )

    report = cli.run_operator_preview(
        tenant_id="default",
        project_root=project_root,
        upload_root=upload_root,
        known_jobs=(known,),
        execute=False,
    )

    assert report.tenant_id == "default"
    assert report.known_job_count == 1
    assert len(report.inventory_entries) == 2
    assert report.assessment.auto_delete_candidates == ()
    assert all(d.disposition == "never_auto_delete" for d in report.assessment.dispositions)
    assert report.execution is None
    assert absolute.is_file() and absolute.read_bytes() == b"v1"
    assert orphan.is_file() and orphan.read_bytes() == b"orphan"


def test_run_operator_preview_execute_is_noop_no_mutation(
    tmp_path: Path,
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "doc.md",
        b"keep",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    report = cli.run_operator_preview(
        tenant_id="acme",
        project_root=project_root,
        upload_root=upload_root,
        known_jobs=(known,),
        execute=True,
    )

    assert report.execution is not None
    assert report.execution.status == "complete"
    assert report.execution.deleted == ()
    assert report.execution.expected_candidates == ()
    assert absolute.is_file()
    assert absolute.read_bytes() == b"keep"


def test_main_json_output_with_injected_loader(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "a.md",
        b"a",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    code = cli.main(
        [
            "--tenant",
            "default",
            "--project-root",
            str(project_root),
            "--upload-root",
            str(upload_root),
            "--json",
            "--execute",
        ],
        load_known_jobs=lambda _tid: (known,),
        load_job_statuses=lambda _tid: {str(job_id): "completed"},
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tenant_id"] == "default"
    assert payload["known_job_count"] == 1
    assert payload["auto_delete_candidates"] == []
    assert payload["execution"]["status"] == "complete"
    assert payload["execution"]["deleted"] == []
    assert absolute.is_file()


def test_main_human_output_exit_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    upload_root.mkdir(parents=True)

    code = cli.main(
        [
            "--tenant",
            "default",
            "--project-root",
            str(project_root),
            "--upload-root",
            str(upload_root),
        ],
        load_known_jobs=lambda _tid: (),
        load_job_statuses=lambda _tid: {},
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "tenant: default" in out
    assert "auto_delete_candidates: 0" in out
    assert "fail-closed" in out
    assert "transition_annotations: 0" in out


def test_main_loader_value_error_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    upload_root.mkdir(parents=True)

    def boom(_tid: str):
        raise ValueError("tenant_id is required")

    code = cli.main(
        [
            "--tenant",
            "default",
            "--project-root",
            str(project_root),
            "--upload-root",
            str(upload_root),
        ],
        load_known_jobs=boom,
        load_job_statuses=lambda _tid: {},
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "tenant_id" in err


def test_non_default_tenant_uses_physical_upload_dir(
    tmp_path: Path,
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    tenant_upload = cli._upload_dir_for_tenant(upload_root, "tenant-x")
    job_id = uuid.uuid4()
    absolute = _write(
        tenant_upload / "job-objects" / str(job_id) / "t.md",
        b"t",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    report = cli.run_operator_preview(
        tenant_id="tenant-x",
        project_root=project_root,
        upload_root=upload_root,
        known_jobs=(known,),
        execute=False,
    )
    assert report.tenant_id == "tenant-x"
    assert Path(report.upload_dir) == tenant_upload
    assert len(report.inventory_entries) == 1
    assert report.inventory_entries[0].classification == "protected"


def test_run_operator_preview_annotates_failed_transition(
    tmp_path: Path,
) -> None:
    """2.4k: failed+protected → retained_after_failed_transition, never deletable."""
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "doc.md",
        b"kept-after-fail",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    report = cli.run_operator_preview(
        tenant_id="default",
        project_root=project_root,
        upload_root=upload_root,
        known_jobs=(known,),
        job_statuses={str(job_id): "failed"},
        execute=False,
    )

    assert len(report.transition_annotations) == 1
    note = report.transition_annotations[0]
    assert note.ownership == "retained_after_failed_transition"
    assert note.job_status == "failed"
    assert note.auto_delete_eligible is False
    assert report.assessment.auto_delete_candidates == ()
    assert absolute.is_file() and absolute.read_bytes() == b"kept-after-fail"


def test_main_json_includes_transition_annotations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "a.md",
        b"a",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    code = cli.main(
        [
            "--tenant",
            "default",
            "--project-root",
            str(project_root),
            "--upload-root",
            str(upload_root),
            "--json",
        ],
        load_known_jobs=lambda _tid: (known,),
        load_job_statuses=lambda _tid: {str(job_id): "failed"},
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    notes = payload["transition_annotations"]
    assert len(notes) == 1
    assert notes[0]["ownership"] == "retained_after_failed_transition"
    assert notes[0]["job_status"] == "failed"
    assert notes[0]["auto_delete_eligible"] is False
    assert notes[0]["job_id"] == str(job_id)
    assert absolute.is_file()


def test_main_human_shows_transition_ownership(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_root = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = _write(
        upload_root / "job-objects" / str(job_id) / "a.md",
        b"a",
    )
    source = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source)

    code = cli.main(
        [
            "--tenant",
            "default",
            "--project-root",
            str(project_root),
            "--upload-root",
            str(upload_root),
        ],
        load_known_jobs=lambda _tid: (known,),
        load_job_statuses=lambda _tid: {str(job_id): "completed"},
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "transition_annotations:" in out
    assert "retained_durable_original" in out
    assert "job_status=completed" in out
    assert absolute.is_file()

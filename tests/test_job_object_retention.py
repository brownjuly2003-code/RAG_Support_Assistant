"""Job-object retention policy (plan 2.4g).

Fail-closed eligibility assessment for immutable upload originals.
This contract never deletes, renames, or mutates files and never invents
age/budget auto-delete thresholds. Under current policy every known
classification is never auto-deletable.
"""
from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def _retention() -> ModuleType:
    return importlib.import_module("ingestion.job_object_retention")


def _inventory() -> ModuleType:
    return importlib.import_module("ingestion.job_object_inventory")


def _entry(
    *,
    relative_path: str,
    kind: str,
    classification: str,
    job_id: str | None = None,
) -> object:
    inv = _inventory()
    return inv.JobObjectInventoryEntry(
        relative_path=relative_path,
        kind=kind,
        classification=classification,
        job_id=job_id,
    )


def test_all_known_classifications_are_never_auto_deletable() -> None:
    pol = _retention()
    job_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{job_id}/a.md",
            kind="job_object",
            classification="protected",
            job_id=job_id,
        ),
        _entry(
            relative_path=f"job-objects/{uuid.uuid4()}/orphan.md",
            kind="job_object",
            classification="unrecorded",
            job_id=str(uuid.uuid4()),
        ),
        _entry(
            relative_path="job-objects/legacy-previous/" + ("a" * 64) + "/p.md",
            kind="legacy_previous",
            classification="protected",
            job_id=None,
        ),
        _entry(
            relative_path="job-objects/not-a-uuid/x.md",
            kind="malformed",
            classification="untrusted",
            job_id=None,
        ),
    )

    assessment = pol.assess_job_object_retention_policy(entries)

    assert assessment.auto_delete_candidates == ()
    assert len(assessment.dispositions) == 4
    for disp in assessment.dispositions:
        assert disp.disposition == "never_auto_delete"
        assert disp.reason
        assert "deletable" not in disp.disposition
    labels = {d.classification for d in assessment.dispositions}
    assert labels == {"protected", "unrecorded", "untrusted"}


def test_empty_inventory_yields_empty_candidates() -> None:
    pol = _retention()
    assessment = pol.assess_job_object_retention_policy(())
    assert assessment.dispositions == ()
    assert assessment.auto_delete_candidates == ()


def test_unknown_classification_fails_closed() -> None:
    pol = _retention()
    bad = _entry(
        relative_path="job-objects/x/y.md",
        kind="job_object",
        classification="orphan_candidate",
        job_id=str(uuid.uuid4()),
    )
    with pytest.raises(pol.JobObjectRetentionValidationError):
        pol.assess_job_object_retention_policy((bad,))


def test_policy_never_emits_auto_delete_vocabulary() -> None:
    pol = _retention()
    job_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{job_id}/a.md",
            kind="job_object",
            classification="unrecorded",
            job_id=job_id,
        ),
    )
    assessment = pol.assess_job_object_retention_policy(entries)
    assert assessment.auto_delete_candidates == ()
    assert "deletable" not in {d.disposition for d in assessment.dispositions}
    assert "candidate" not in {d.disposition for d in assessment.dispositions}
    # Public API must not invent age/budget fields.
    assert not hasattr(assessment, "max_age_days")
    assert not hasattr(assessment, "budget")
    assert not hasattr(assessment, "max_versions")


def test_policy_does_not_mutate_filesystem(tmp_path: Path) -> None:
    pol = _retention()
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    path = upload_dir / "job-objects" / str(job_id) / "doc.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"keep-me")

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )
    assessment = pol.assess_job_object_retention_policy(entries)

    assert assessment.auto_delete_candidates == ()
    assert path.is_file()
    assert path.read_bytes() == b"keep-me"


def test_protected_and_untrusted_have_distinct_reasons() -> None:
    pol = _retention()
    job_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{job_id}/a.md",
            kind="job_object",
            classification="protected",
            job_id=job_id,
        ),
        _entry(
            relative_path=f"job-objects/{job_id}/b.md",
            kind="job_object",
            classification="untrusted",
            job_id=job_id,
        ),
        _entry(
            relative_path=f"job-objects/{uuid.uuid4()}/c.md",
            kind="job_object",
            classification="unrecorded",
            job_id=str(uuid.uuid4()),
        ),
    )
    assessment = pol.assess_job_object_retention_policy(entries)
    by_class = {d.classification: d.reason for d in assessment.dispositions}
    assert by_class["protected"] != by_class["untrusted"]
    assert by_class["protected"] != by_class["unrecorded"]
    assert by_class["untrusted"] != by_class["unrecorded"]


def test_compose_preview_then_policy_is_fail_closed(
    tmp_path: Path,
) -> None:
    """Operator path after 2.4f: preview entries → policy; still no candidates."""
    inv = _inventory()
    pol = _retention()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    absolute = upload_dir / "job-objects" / str(job_id) / "guide.md"
    absolute.parent.mkdir(parents=True)
    absolute.write_bytes(b"v1")
    source_path = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    known = inv.KnownJobObjectRef(job_id=str(job_id), source_path=source_path)
    # Orphan on disk.
    orphan_id = uuid.uuid4()
    orphan = upload_dir / "job-objects" / str(orphan_id) / "orphan.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"orphan")

    preview = inv.preview_tenant_job_object_inventory(
        upload_dir,
        tenant_id="pol-tenant",
        known_jobs=(known,),
        project_root=project_root,
    )
    assessment = pol.assess_job_object_retention_policy(preview.entries)

    assert assessment.auto_delete_candidates == ()
    assert all(d.disposition == "never_auto_delete" for d in assessment.dispositions)
    assert absolute.is_file() and absolute.read_bytes() == b"v1"
    assert orphan.is_file() and orphan.read_bytes() == b"orphan"

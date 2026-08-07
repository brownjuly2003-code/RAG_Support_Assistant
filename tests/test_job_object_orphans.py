"""Failed-transition job-object ownership annotations (plan 2.4j).

Read-only ownership mapping for inventory entries given known job statuses.
Failed jobs that still reference on-disk originals are intentional retention,
not auto-delete candidates. This contract never mutates the filesystem.
"""
from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def _orphans() -> ModuleType:
    return importlib.import_module("ingestion.job_object_orphans")


def _inv() -> ModuleType:
    return importlib.import_module("ingestion.job_object_inventory")


def _entry(
    *,
    relative_path: str,
    kind: str,
    classification: str,
    job_id: str | None = None,
) -> object:
    inv = _inv()
    return inv.JobObjectInventoryEntry(
        relative_path=relative_path,
        kind=kind,
        classification=classification,
        job_id=job_id,
    )


def test_protected_failed_job_is_retained_not_orphan() -> None:
    mod = _orphans()
    job_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{job_id}/a.md",
            kind="job_object",
            classification="protected",
            job_id=job_id,
        ),
    )
    notes = mod.annotate_job_object_transition_context(
        entries,
        job_statuses={job_id: "failed"},
    )
    assert len(notes) == 1
    note = notes[0]
    assert note.ownership == "retained_after_failed_transition"
    assert note.auto_delete_eligible is False
    assert note.job_status == "failed"
    assert note.classification == "protected"


def test_protected_completed_job_is_durable_original() -> None:
    mod = _orphans()
    job_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{job_id}/a.md",
            kind="job_object",
            classification="protected",
            job_id=job_id,
        ),
    )
    notes = mod.annotate_job_object_transition_context(
        entries,
        job_statuses={job_id: "completed"},
    )
    assert notes[0].ownership == "retained_durable_original"
    assert notes[0].auto_delete_eligible is False


def test_unrecorded_and_untrusted_never_auto_delete() -> None:
    mod = _orphans()
    orphan_id = str(uuid.uuid4())
    entries = (
        _entry(
            relative_path=f"job-objects/{orphan_id}/orphan.md",
            kind="job_object",
            classification="unrecorded",
            job_id=orphan_id,
        ),
        _entry(
            relative_path="job-objects/not-uuid/x.md",
            kind="malformed",
            classification="untrusted",
            job_id=None,
        ),
        _entry(
            relative_path="job-objects/legacy-previous/" + ("c" * 64) + "/p.md",
            kind="legacy_previous",
            classification="protected",
            job_id=None,
        ),
    )
    notes = mod.annotate_job_object_transition_context(
        entries,
        job_statuses={},
    )
    by_class = {n.classification: n for n in notes}
    assert by_class["unrecorded"].ownership == "unrecorded_identity"
    assert by_class["untrusted"].ownership == "untrusted_layout"
    assert by_class["protected"].ownership == "legacy_recovery_object"
    assert all(n.auto_delete_eligible is False for n in notes)


def test_unknown_classification_fails_closed() -> None:
    mod = _orphans()
    bad = _entry(
        relative_path="job-objects/x/y.md",
        kind="job_object",
        classification="deletable",
        job_id=str(uuid.uuid4()),
    )
    with pytest.raises(mod.JobObjectOrphanValidationError):
        mod.annotate_job_object_transition_context((bad,), job_statuses={})


def test_no_auto_delete_vocabulary_and_no_age_budget_fields() -> None:
    mod = _orphans()
    job_id = str(uuid.uuid4())
    notes = mod.annotate_job_object_transition_context(
        (
            _entry(
                relative_path=f"job-objects/{job_id}/a.md",
                kind="job_object",
                classification="protected",
                job_id=job_id,
            ),
        ),
        job_statuses={job_id: "failed"},
    )
    assert notes[0].auto_delete_eligible is False
    assert "orphan_candidate" not in notes[0].ownership
    assert "deletable" not in notes[0].ownership
    assert not hasattr(notes[0], "max_age_days")
    assert not hasattr(notes[0], "budget")


def test_annotation_never_mutates_filesystem(tmp_path: Path) -> None:
    mod = _orphans()
    inv = _inv()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = uuid.uuid4()
    path = upload_dir / "job-objects" / str(job_id) / "doc.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"keep")
    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )
    notes = mod.annotate_job_object_transition_context(
        entries,
        job_statuses={},
    )
    assert notes
    assert all(n.auto_delete_eligible is False for n in notes)
    assert path.is_file() and path.read_bytes() == b"keep"


def test_protected_without_status_map_is_retained_unknown_status() -> None:
    mod = _orphans()
    job_id = str(uuid.uuid4())
    notes = mod.annotate_job_object_transition_context(
        (
            _entry(
                relative_path=f"job-objects/{job_id}/a.md",
                kind="job_object",
                classification="protected",
                job_id=job_id,
            ),
        ),
        job_statuses={},
    )
    assert notes[0].ownership == "retained_unknown_job_status"
    assert notes[0].job_status is None
    assert notes[0].auto_delete_eligible is False


def test_queued_and_running_statuses_are_retained_active() -> None:
    mod = _orphans()
    qid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    notes = mod.annotate_job_object_transition_context(
        (
            _entry(
                relative_path=f"job-objects/{qid}/q.md",
                kind="job_object",
                classification="protected",
                job_id=qid,
            ),
            _entry(
                relative_path=f"job-objects/{rid}/r.md",
                kind="job_object",
                classification="protected",
                job_id=rid,
            ),
        ),
        job_statuses={qid: "queued", rid: "running"},
    )
    by_id = {n.job_id: n for n in notes}
    assert by_id[qid].ownership == "retained_in_flight"
    assert by_id[rid].ownership == "retained_in_flight"
    assert all(n.auto_delete_eligible is False for n in notes)

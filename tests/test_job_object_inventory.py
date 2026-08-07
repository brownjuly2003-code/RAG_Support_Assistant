"""Job-object lifecycle inventory classification (plan 2.4e).

Read-only classification of immutable upload originals under
``job-objects/``. This contract never deletes, renames, or mutates files
and never invents a retention age/budget policy.
"""
from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def _inventory() -> ModuleType:
    return importlib.import_module("ingestion.job_object_inventory")


def _job_id() -> uuid.UUID:
    return uuid.uuid4()


def _write(path: Path, data: bytes = b"payload") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _ref(
    project_root: Path,
    upload_dir: Path,
    job_id: uuid.UUID,
    safe_name: str,
) -> object:
    inv = _inventory()
    absolute = upload_dir / "job-objects" / str(job_id) / safe_name
    source_path = absolute.resolve().relative_to(project_root.resolve()).as_posix()
    return inv.KnownJobObjectRef(job_id=str(job_id), source_path=source_path)


def test_missing_or_empty_job_objects_tree_returns_empty(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    upload_dir.mkdir(parents=True)

    assert (
        inv.classify_job_object_tree(
            upload_dir,
            known_jobs=(),
            project_root=project_root,
        )
        == ()
    )

    (upload_dir / "job-objects").mkdir()
    assert (
        inv.classify_job_object_tree(
            upload_dir,
            known_jobs=(),
            project_root=project_root,
        )
        == ()
    )


def test_referenced_job_object_is_protected(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    safe_name = "guide.md"
    absolute = _write(upload_dir / "job-objects" / str(job_id) / safe_name, b"v1")
    known = _ref(project_root, upload_dir, job_id, safe_name)

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(known,),
        project_root=project_root,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "job_object"
    assert entry.classification == "protected"
    assert entry.job_id == str(job_id)
    assert entry.relative_path == absolute.relative_to(upload_dir).as_posix()
    assert absolute.is_file()


def test_unrecorded_job_object_is_never_auto_deletable(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    orphan_id = _job_id()
    absolute = _write(
        upload_dir / "job-objects" / str(orphan_id) / "orphan.md",
        b"orphan",
    )

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "job_object"
    assert entry.classification == "unrecorded"
    assert entry.job_id == str(orphan_id)
    # Inventory is classification-only: never mutates filesystem.
    assert absolute.is_file()
    assert absolute.read_bytes() == b"orphan"


def test_legacy_previous_recovery_objects_are_always_protected(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    digest = "a" * 64
    absolute = _write(
        upload_dir
        / "job-objects"
        / "legacy-previous"
        / digest
        / "prior.md",
        b"prior-flat",
    )

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "legacy_previous"
    assert entry.classification == "protected"
    assert entry.job_id is None
    assert entry.relative_path == absolute.relative_to(upload_dir).as_posix()
    assert absolute.is_file()


def test_source_path_mismatch_is_untrusted_not_deletable(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    absolute = _write(
        upload_dir / "job-objects" / str(job_id) / "actual.md",
        b"on-disk",
    )
    # Known job points at a different path under the same job id.
    known = inv.KnownJobObjectRef(
        job_id=str(job_id),
        source_path=(
            (upload_dir / "job-objects" / str(job_id) / "other.md")
            .resolve()
            .relative_to(project_root.resolve())
            .as_posix()
        ),
    )

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(known,),
        project_root=project_root,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "job_object"
    assert entry.classification == "untrusted"
    assert entry.job_id == str(job_id)
    assert absolute.is_file()


def test_malformed_layout_is_untrusted(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    # Not a UUID job directory and not legacy-previous.
    loose = _write(upload_dir / "job-objects" / "not-a-uuid" / "x.md", b"x")
    # Extra nesting under a valid UUID is not the 2.4a layout.
    job_id = _job_id()
    nested = _write(
        upload_dir / "job-objects" / str(job_id) / "extra" / "deep.md",
        b"deep",
    )
    # File directly under job-objects root.
    root_file = _write(upload_dir / "job-objects" / "stray.md", b"stray")

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )

    by_path = {entry.relative_path: entry for entry in entries}
    assert set(by_path) == {
        loose.relative_to(upload_dir).as_posix(),
        nested.relative_to(upload_dir).as_posix(),
        root_file.relative_to(upload_dir).as_posix(),
    }
    for entry in entries:
        assert entry.kind == "malformed"
        assert entry.classification == "untrusted"
        assert entry.job_id is None
    assert loose.is_file() and nested.is_file() and root_file.is_file()


def test_flat_corpus_view_is_never_listed(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    flat = _write(upload_dir / "corpus.md", b"flat-current")
    job_id = _job_id()
    _write(upload_dir / "job-objects" / str(job_id) / "corpus.md", b"immutable")
    known = _ref(project_root, upload_dir, job_id, "corpus.md")

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(known,),
        project_root=project_root,
    )

    assert len(entries) == 1
    assert all("job-objects/" in entry.relative_path for entry in entries)
    assert flat.is_file()
    assert flat.read_bytes() == b"flat-current"


def test_classification_never_emits_deletable_or_candidate_labels(
    tmp_path: Path,
) -> None:
    """Policy boundary: this slice has no deletion/candidate vocabulary."""
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    _write(upload_dir / "job-objects" / str(job_id) / "a.md", b"a")
    _write(
        upload_dir / "job-objects" / "legacy-previous" / ("b" * 64) / "b.md",
        b"b",
    )
    _write(upload_dir / "job-objects" / "weird" / "c.md", b"c")

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(),
        project_root=project_root,
    )
    labels = {entry.classification for entry in entries}
    assert labels <= {"protected", "unrecorded", "untrusted"}
    assert "deletable" not in labels
    assert "candidate" not in labels
    assert "orphan_candidate" not in labels


def test_known_job_with_invalid_source_path_does_not_protect_unrelated(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    absolute = _write(
        upload_dir / "job-objects" / str(job_id) / "real.md",
        b"real",
    )
    known = inv.KnownJobObjectRef(
        job_id=str(job_id),
        source_path="data/uploads/job-objects/not-even-uuid/missing.md",
    )

    entries = inv.classify_job_object_tree(
        upload_dir,
        known_jobs=(known,),
        project_root=project_root,
    )

    assert len(entries) == 1
    assert entries[0].classification == "untrusted"
    assert absolute.is_file()


def test_duplicate_known_job_ids_fail_closed(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    upload_dir.mkdir(parents=True)
    job_id = str(_job_id())
    known_a = inv.KnownJobObjectRef(
        job_id=job_id,
        source_path="data/uploads/job-objects/%s/a.md" % job_id,
    )
    known_b = inv.KnownJobObjectRef(
        job_id=job_id,
        source_path="data/uploads/job-objects/%s/b.md" % job_id,
    )

    with pytest.raises(inv.JobObjectInventoryValidationError):
        inv.classify_job_object_tree(
            upload_dir,
            known_jobs=(known_a, known_b),
            project_root=project_root,
        )


def test_upload_dir_outside_project_root_is_rejected(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    project_root.mkdir()
    foreign_upload = tmp_path / "foreign" / "uploads"
    foreign_upload.mkdir(parents=True)

    with pytest.raises(inv.JobObjectInventoryValidationError):
        inv.classify_job_object_tree(
            foreign_upload,
            known_jobs=(),
            project_root=project_root,
        )

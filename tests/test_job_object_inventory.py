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
        upload_dir / "job-objects" / "legacy-previous" / digest / "prior.md",
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


# ---------------------------------------------------------------------------
# 2.4f — tenant-scoped inventory preview (load known refs + classify; no delete)
# ---------------------------------------------------------------------------


def test_preview_composes_known_refs_and_classifier_without_mutation(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    absolute = _write(
        upload_dir / "job-objects" / str(job_id) / "doc.md",
        b"immutable",
    )
    known = _ref(project_root, upload_dir, job_id, "doc.md")
    orphan_id = _job_id()
    orphan = _write(
        upload_dir / "job-objects" / str(orphan_id) / "orphan.md",
        b"orphan",
    )

    preview = inv.preview_tenant_job_object_inventory(
        upload_dir,
        tenant_id="acme",
        known_jobs=(known,),
        project_root=project_root,
    )

    assert preview.tenant_id == "acme"
    assert preview.known_job_count == 1
    assert len(preview.entries) == 2
    by_job = {entry.job_id: entry for entry in preview.entries}
    assert by_job[str(job_id)].classification == "protected"
    assert by_job[str(orphan_id)].classification == "unrecorded"
    assert absolute.is_file() and absolute.read_bytes() == b"immutable"
    assert orphan.is_file() and orphan.read_bytes() == b"orphan"
    # Preview has no deletion vocabulary.
    labels = {entry.classification for entry in preview.entries}
    assert labels <= {"protected", "unrecorded", "untrusted"}
    assert "deletable" not in labels


def test_preview_falsey_tenant_normalizes_to_default(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    upload_dir.mkdir(parents=True)

    preview = inv.preview_tenant_job_object_inventory(
        upload_dir,
        tenant_id="  ",
        known_jobs=(),
        project_root=project_root,
    )
    assert preview.tenant_id == "default"
    assert preview.known_job_count == 0
    assert preview.entries == ()


def test_preview_rejects_upload_dir_outside_project_root(
    tmp_path: Path,
) -> None:
    inv = _inventory()
    project_root = tmp_path / "project"
    project_root.mkdir()
    foreign = tmp_path / "foreign" / "uploads"
    foreign.mkdir(parents=True)

    with pytest.raises(inv.JobObjectInventoryValidationError):
        inv.preview_tenant_job_object_inventory(
            foreign,
            tenant_id="t1",
            known_jobs=(),
            project_root=project_root,
        )


def test_sync_list_known_job_object_refs_is_tenant_scoped(
    ingestion_jobs_db,
) -> None:
    from db.models import IngestionJob
    from ingestion import jobs as jobs_mod
    from ingestion.job_object_inventory import KnownJobObjectRef

    job_a = uuid.uuid4()
    job_b = uuid.uuid4()
    job_other = uuid.uuid4()
    with jobs_mod.sync_session() as session:
        session.add_all(
            [
                IngestionJob(
                    id=job_a,
                    tenant_id="tenant-a",
                    filename="a.md",
                    source_path="data/uploads/job-objects/%s/a.md" % job_a,
                    status="completed",
                ),
                IngestionJob(
                    id=job_b,
                    tenant_id="tenant-a",
                    filename="b.md",
                    source_path="data/uploads/job-objects/%s/b.md" % job_b,
                    status="failed",
                ),
                IngestionJob(
                    id=job_other,
                    tenant_id="tenant-b",
                    filename="other.md",
                    source_path="data/uploads/job-objects/%s/other.md" % job_other,
                    status="completed",
                ),
            ]
        )
        session.commit()

    refs = jobs_mod.sync_list_known_job_object_refs("tenant-a")
    assert isinstance(refs, tuple)
    assert all(isinstance(ref, KnownJobObjectRef) for ref in refs)
    assert {ref.job_id for ref in refs} == {str(job_a), str(job_b)}
    assert all(ref.source_path for ref in refs)
    # Other tenant never leaks.
    assert str(job_other) not in {ref.job_id for ref in refs}


def test_sync_list_known_job_object_refs_skips_blank_source_path(
    ingestion_jobs_db,
) -> None:
    from db.models import IngestionJob
    from ingestion import jobs as jobs_mod

    good_id = uuid.uuid4()
    blank_id = uuid.uuid4()
    with jobs_mod.sync_session() as session:
        session.add_all(
            [
                IngestionJob(
                    id=good_id,
                    tenant_id="skip-blank",
                    filename="good.md",
                    source_path="data/uploads/job-objects/%s/good.md" % good_id,
                    status="completed",
                ),
                IngestionJob(
                    id=blank_id,
                    tenant_id="skip-blank",
                    filename="blank.md",
                    source_path="   ",
                    status="completed",
                ),
            ]
        )
        session.commit()

    refs = jobs_mod.sync_list_known_job_object_refs("skip-blank")
    assert len(refs) == 1
    assert refs[0].job_id == str(good_id)


def test_sync_list_known_job_object_refs_requires_tenant(
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod

    with pytest.raises(ValueError, match="tenant_id"):
        jobs_mod.sync_list_known_job_object_refs("")
    with pytest.raises(ValueError, match="tenant_id"):
        jobs_mod.sync_list_known_job_object_refs("   ")


def test_sync_list_job_statuses_for_tenant_is_tenant_scoped(
    ingestion_jobs_db,
) -> None:
    from db.models import IngestionJob
    from ingestion import jobs as jobs_mod

    job_a = uuid.uuid4()
    job_b = uuid.uuid4()
    job_other = uuid.uuid4()
    with jobs_mod.sync_session() as session:
        session.add_all(
            [
                IngestionJob(
                    id=job_a,
                    tenant_id="tenant-a",
                    filename="a.md",
                    source_path="data/uploads/job-objects/%s/a.md" % job_a,
                    status="completed",
                ),
                IngestionJob(
                    id=job_b,
                    tenant_id="tenant-a",
                    filename="b.md",
                    source_path="data/uploads/job-objects/%s/b.md" % job_b,
                    status="failed",
                ),
                IngestionJob(
                    id=job_other,
                    tenant_id="tenant-b",
                    filename="other.md",
                    source_path="data/uploads/job-objects/%s/other.md" % job_other,
                    status="queued",
                ),
            ]
        )
        session.commit()

    statuses = jobs_mod.sync_list_job_statuses_for_tenant("tenant-a")
    assert isinstance(statuses, dict)
    assert statuses == {str(job_a): "completed", str(job_b): "failed"}
    assert str(job_other) not in statuses


def test_sync_list_job_statuses_for_tenant_covers_all_job_states(
    ingestion_jobs_db,
) -> None:
    from db.models import IngestionJob
    from ingestion import jobs as jobs_mod

    ids = {name: uuid.uuid4() for name in ("queued", "running", "completed", "failed")}
    with jobs_mod.sync_session() as session:
        session.add_all(
            [
                IngestionJob(
                    id=job_id,
                    tenant_id="all-states",
                    filename=f"{status}.md",
                    source_path="data/uploads/job-objects/%s/%s.md" % (job_id, status),
                    status=status,
                )
                for status, job_id in ids.items()
            ]
        )
        session.commit()

    statuses = jobs_mod.sync_list_job_statuses_for_tenant("all-states")
    assert statuses == {str(job_id): status for status, job_id in ids.items()}


def test_sync_list_job_statuses_for_tenant_requires_tenant(
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod

    with pytest.raises(ValueError, match="tenant_id"):
        jobs_mod.sync_list_job_statuses_for_tenant("")
    with pytest.raises(ValueError, match="tenant_id"):
        jobs_mod.sync_list_job_statuses_for_tenant("   ")


def test_tenant_preview_end_to_end_load_and_classify(
    tmp_path: Path,
    ingestion_jobs_db,
) -> None:
    """Operator path: load tenant refs from DB, classify tree, never mutate."""
    from db.models import IngestionJob
    from ingestion import jobs as jobs_mod

    inv = _inventory()
    project_root = tmp_path / "project"
    upload_dir = project_root / "data" / "uploads"
    job_id = _job_id()
    absolute = _write(
        upload_dir / "job-objects" / str(job_id) / "guide.md",
        b"v1",
    )
    source_path = absolute.resolve().relative_to(project_root.resolve()).as_posix()

    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=job_id,
                tenant_id="e2e-tenant",
                filename="guide.md",
                source_path=source_path,
                status="completed",
            )
        )
        session.commit()

    known = jobs_mod.sync_list_known_job_object_refs("e2e-tenant")
    preview = inv.preview_tenant_job_object_inventory(
        upload_dir,
        tenant_id="e2e-tenant",
        known_jobs=known,
        project_root=project_root,
    )

    assert preview.tenant_id == "e2e-tenant"
    assert preview.known_job_count == 1
    assert len(preview.entries) == 1
    assert preview.entries[0].classification == "protected"
    assert preview.entries[0].job_id == str(job_id)
    assert absolute.is_file()
    assert absolute.read_bytes() == b"v1"

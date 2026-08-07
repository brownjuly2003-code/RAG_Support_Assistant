"""Read-only inventory classification for immutable upload job objects.

Layout contract (must match ``api/routers/upload.py`` 2.4a create path):

- ``job-objects/<job_id>/<safe_name>`` — job-scoped immutable original;
  durable reference is ``IngestionJob.source_path``.
- ``job-objects/legacy-previous/<sha256>/<safe_name>`` — content-addressed
  recovery object for a pre-2.4a flat original.

This module classifies on-disk files only. It never deletes, renames, or
mutates filesystem state and does not invent age/budget deletion policy.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Keep string literals aligned with api/routers/upload.py private constants.
# Do not import upload here (FastAPI surface); do not reopen the create path.
_JOB_OBJECTS_DIRNAME = "job-objects"
_LEGACY_PREVIOUS_DIRNAME = "legacy-previous"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

_KIND_JOB_OBJECT = "job_object"
_KIND_LEGACY_PREVIOUS = "legacy_previous"
_KIND_MALFORMED = "malformed"

_CLASS_PROTECTED = "protected"
_CLASS_UNRECORDED = "unrecorded"
_CLASS_UNTRUSTED = "untrusted"


class JobObjectInventoryError(RuntimeError):
    """Base class for job-object inventory failures."""


class JobObjectInventoryValidationError(JobObjectInventoryError):
    """Raised when classification inputs violate the contract."""


@dataclass(frozen=True)
class KnownJobObjectRef:
    """Durable job reference used to protect on-disk originals.

    ``source_path`` is the project-relative path stored on
    ``IngestionJob.source_path`` (posix separators).
    """

    job_id: str
    source_path: str


@dataclass(frozen=True)
class JobObjectInventoryEntry:
    """One on-disk file under the tenant job-objects tree."""

    relative_path: str
    kind: str
    classification: str
    job_id: str | None


def _require_upload_under_project(upload_dir: Path, project_root: Path) -> Path:
    try:
        resolved_upload = upload_dir.resolve(strict=False)
        resolved_root = project_root.resolve(strict=False)
        resolved_upload.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise JobObjectInventoryValidationError(
            "upload_dir must resolve under project_root"
        ) from exc
    return resolved_upload


def _index_known_jobs(
    known_jobs: Sequence[KnownJobObjectRef],
    *,
    project_root: Path,
) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    resolved_root = project_root.resolve(strict=False)
    for ref in known_jobs:
        raw_id = str(ref.job_id or "").strip()
        if not raw_id:
            raise JobObjectInventoryValidationError("known job_id is required")
        job_id = _parse_uuid(raw_id)
        if job_id is None:
            raise JobObjectInventoryValidationError(
                "known job_id must be a UUID"
            )
        if job_id in indexed:
            raise JobObjectInventoryValidationError(
                "duplicate known job_id is not allowed"
            )
        source = str(ref.source_path or "").strip()
        if not source:
            raise JobObjectInventoryValidationError(
                "known job source_path is required"
            )
        # Resolve under project root; missing files are fine (no protect match).
        candidate = (resolved_root / Path(source)).resolve(strict=False)
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise JobObjectInventoryValidationError(
                "known job source_path escapes project_root"
            ) from exc
        indexed[job_id] = candidate
    return indexed


def _parse_uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _classify_file(
    *,
    file_path: Path,
    job_objects_root: Path,
    upload_dir: Path,
    known_by_id: dict[str, Path],
) -> JobObjectInventoryEntry:
    try:
        resolved = file_path.resolve(strict=False)
        relative_to_objects = resolved.relative_to(job_objects_root)
        relative_to_upload = resolved.relative_to(upload_dir)
    except (OSError, ValueError):
        # Escape / unlink race: report untrusted without raising mid-scan.
        return JobObjectInventoryEntry(
            relative_path=file_path.as_posix(),
            kind=_KIND_MALFORMED,
            classification=_CLASS_UNTRUSTED,
            job_id=None,
        )

    parts = relative_to_objects.parts
    relative_path = relative_to_upload.as_posix()

    # job-objects/legacy-previous/<sha256>/<safe_name>
    if (
        len(parts) == 3
        and parts[0] == _LEGACY_PREVIOUS_DIRNAME
        and _SHA256_HEX_RE.fullmatch(parts[1]) is not None
        and parts[2]
        and parts[2] not in {".", ".."}
    ):
        return JobObjectInventoryEntry(
            relative_path=relative_path,
            kind=_KIND_LEGACY_PREVIOUS,
            classification=_CLASS_PROTECTED,
            job_id=None,
        )

    # job-objects/<job_id>/<safe_name>
    if len(parts) == 2 and parts[0] and parts[1] and parts[1] not in {".", ".."}:
        job_id = _parse_uuid(parts[0])
        if job_id is not None:
            known_source = known_by_id.get(job_id)
            if known_source is None:
                return JobObjectInventoryEntry(
                    relative_path=relative_path,
                    kind=_KIND_JOB_OBJECT,
                    classification=_CLASS_UNRECORDED,
                    job_id=job_id,
                )
            if known_source == resolved:
                return JobObjectInventoryEntry(
                    relative_path=relative_path,
                    kind=_KIND_JOB_OBJECT,
                    classification=_CLASS_PROTECTED,
                    job_id=job_id,
                )
            return JobObjectInventoryEntry(
                relative_path=relative_path,
                kind=_KIND_JOB_OBJECT,
                classification=_CLASS_UNTRUSTED,
                job_id=job_id,
            )

    return JobObjectInventoryEntry(
        relative_path=relative_path,
        kind=_KIND_MALFORMED,
        classification=_CLASS_UNTRUSTED,
        job_id=None,
    )


def classify_job_object_tree(
    upload_dir: Path | str,
    *,
    known_jobs: Sequence[KnownJobObjectRef],
    project_root: Path | str,
) -> tuple[JobObjectInventoryEntry, ...]:
    """Classify files under ``upload_dir/job-objects`` without mutation.

    Safety invariants:

    - files referenced by a known job ``source_path`` are ``protected``;
    - ``legacy-previous`` recovery objects are always ``protected``;
    - valid job-object layout without a known job is ``unrecorded``
      (never auto-deletable in this slice);
    - malformed / mismatched paths are ``untrusted`` (never auto-deletable);
    - the flat corpus view outside ``job-objects/`` is never listed;
    - this function never deletes or rewrites filesystem state.
    """
    upload = Path(upload_dir)
    root = Path(project_root)
    resolved_upload = _require_upload_under_project(upload, root)
    known_by_id = _index_known_jobs(known_jobs, project_root=root)

    job_objects_root = (resolved_upload / _JOB_OBJECTS_DIRNAME).resolve(strict=False)
    try:
        job_objects_root.relative_to(resolved_upload)
    except ValueError as exc:
        raise JobObjectInventoryValidationError(
            "job-objects path escapes upload_dir"
        ) from exc

    if not job_objects_root.is_dir():
        return ()

    entries: list[JobObjectInventoryEntry] = []
    for path in sorted(job_objects_root.rglob("*")):
        if not path.is_file():
            continue
        entries.append(
            _classify_file(
                file_path=path,
                job_objects_root=job_objects_root,
                upload_dir=resolved_upload,
                known_by_id=known_by_id,
            )
        )
    return tuple(entries)

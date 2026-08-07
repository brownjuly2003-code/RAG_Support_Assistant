"""Failed-transition ownership annotations for job objects (plan 2.4j).

Investigation findings (encoded as code, not docs-only):

- Create order in ``api/routers/upload.py`` (2.4a): durable ``IngestionJob``
  row first (with ``source_path``), then exclusive immutable write under
  ``job-objects/<job_id>/``, then legacy-previous preserve, then flat
  current-view refresh. Flat is **not** refreshed unless immutable +
  preserve both succeed.
- After a successful immutable write, indexing/publish/broker failure still
  leaves the job-object on disk. The job is marked ``failed`` while
  ``source_path`` remains. The 2.4e classifier labels that object
  ``protected`` — **intentional retention**, not a GC/orphan-delete
  candidate.
- Partial create failures terminal-fail the job without publishing; any
  on-disk object still referenced by ``source_path`` stays protected.
- ``unrecorded`` / ``untrusted`` / ``legacy_previous`` remain never
  auto-deletable under 2.4g policy; this module does not invent deletion.
- Index retention (``vectordb.*``) is a separate Chroma subsystem and must
  not delete upload job-objects.

This module only annotates inventory entries given optional job statuses.
It never deletes, renames, or mutates filesystem state and does not invent
age/budget thresholds.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ingestion.job_object_inventory import JobObjectInventoryEntry

_CLASS_PROTECTED = "protected"
_CLASS_UNRECORDED = "unrecorded"
_CLASS_UNTRUSTED = "untrusted"

_KIND_LEGACY_PREVIOUS = "legacy_previous"

_STATUS_FAILED = "failed"
_STATUS_COMPLETED = "completed"
_STATUS_QUEUED = "queued"
_STATUS_RUNNING = "running"

_OWN_RETAINED_FAILED = "retained_after_failed_transition"
_OWN_RETAINED_DURABLE = "retained_durable_original"
_OWN_RETAINED_IN_FLIGHT = "retained_in_flight"
_OWN_RETAINED_UNKNOWN = "retained_unknown_job_status"
_OWN_UNRECORDED = "unrecorded_identity"
_OWN_UNTRUSTED = "untrusted_layout"
_OWN_LEGACY = "legacy_recovery_object"


class JobObjectOrphanError(RuntimeError):
    """Base class for job-object orphan ownership failures."""


class JobObjectOrphanValidationError(JobObjectOrphanError):
    """Raised when ownership annotation inputs violate the fail-closed contract."""


@dataclass(frozen=True)
class JobObjectTransitionAnnotation:
    """Ownership note for one inventory entry after failed/partial transitions.

    ``auto_delete_eligible`` is always False under the current contract.
    """

    relative_path: str
    classification: str
    kind: str
    job_id: str | None
    job_status: str | None
    ownership: str
    auto_delete_eligible: bool


def annotate_job_object_transition_context(
    entries: Sequence[JobObjectInventoryEntry],
    *,
    job_statuses: Mapping[str, str],
) -> tuple[JobObjectTransitionAnnotation, ...]:
    """Annotate inventory entries with failed-transition ownership context.

    ``job_statuses`` maps durable job UUID strings to status values
    (``queued`` / ``running`` / ``completed`` / ``failed``). Missing map
    entries yield ``retained_unknown_job_status`` for protected job objects.

    Safety invariants:

    - every annotation has ``auto_delete_eligible is False``;
    - unknown inventory classifications fail closed;
    - filesystem state is never read or written.
    """
    status_map = {
        str(k).strip(): str(v).strip().lower()
        for k, v in dict(job_statuses).items()
        if str(k).strip()
    }
    notes: list[JobObjectTransitionAnnotation] = []
    for entry in entries:
        classification = str(getattr(entry, "classification", "") or "").strip()
        kind = str(getattr(entry, "kind", "") or "").strip()
        relative_path = str(getattr(entry, "relative_path", "") or "")
        raw_job_id = getattr(entry, "job_id", None)
        job_id = str(raw_job_id).strip() if raw_job_id is not None else None
        if job_id == "":
            job_id = None

        if classification not in {
            _CLASS_PROTECTED,
            _CLASS_UNRECORDED,
            _CLASS_UNTRUSTED,
        }:
            raise JobObjectOrphanValidationError(
                f"unknown inventory classification is not auto-deletable: "
                f"{classification!r}"
            )

        job_status: str | None = None
        if job_id is not None:
            job_status = status_map.get(job_id)

        if classification == _CLASS_UNRECORDED:
            ownership = _OWN_UNRECORDED
        elif classification == _CLASS_UNTRUSTED:
            ownership = _OWN_UNTRUSTED
        elif kind == _KIND_LEGACY_PREVIOUS:
            ownership = _OWN_LEGACY
        elif classification == _CLASS_PROTECTED:
            if job_status == _STATUS_FAILED:
                ownership = _OWN_RETAINED_FAILED
            elif job_status == _STATUS_COMPLETED:
                ownership = _OWN_RETAINED_DURABLE
            elif job_status in {_STATUS_QUEUED, _STATUS_RUNNING}:
                ownership = _OWN_RETAINED_IN_FLIGHT
            else:
                ownership = _OWN_RETAINED_UNKNOWN
        else:
            # Defensive: should be unreachable given the set check above.
            raise JobObjectOrphanValidationError(
                f"unsupported classification/kind pair: "
                f"{classification!r}/{kind!r}"
            )

        notes.append(
            JobObjectTransitionAnnotation(
                relative_path=relative_path,
                classification=classification,
                kind=kind,
                job_id=job_id,
                job_status=job_status,
                ownership=ownership,
                auto_delete_eligible=False,
            )
        )
    return tuple(notes)

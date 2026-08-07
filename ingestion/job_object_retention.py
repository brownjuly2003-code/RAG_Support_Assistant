"""Fail-closed retention policy for immutable job objects (plan 2.4g).

Ownership findings (read-only investigation, encoded as code):

- Create path owner: ``api/routers/upload.py`` (slice 2.4a) — not a GC path.
- Durable reference: ``IngestionJob.source_path``.
- Classification / tenant preview: ``ingestion.job_object_inventory``
  (slices 2.4e / 2.4f).
- Index retention (``vectordb.index_retention`` and related) is a **separate**
  subsystem for Chroma collection versions; it must not delete
  ``job-objects/**`` or ``legacy-previous/**`` upload originals.
- No pre-existing job-object GC / delete executor module was found.

Policy (current, fail-closed):

- every known inventory classification is ``never_auto_delete``;
- ``auto_delete_candidates`` is always empty;
- unknown classifications raise validation errors;
- this module never deletes, renames, or mutates filesystem state and does
  not invent age/budget deletion thresholds.

A future guarded executor (later slice) must not invent auto-delete
candidates without an explicit policy expansion beyond this module.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ingestion.job_object_inventory import JobObjectInventoryEntry

_DISPOSITION_NEVER_AUTO_DELETE = "never_auto_delete"

# Keep aligned with job_object_inventory classification labels (2.4e).
_CLASS_PROTECTED = "protected"
_CLASS_UNRECORDED = "unrecorded"
_CLASS_UNTRUSTED = "untrusted"

_REASON_BY_CLASSIFICATION: dict[str, str] = {
    _CLASS_PROTECTED: "referenced_or_legacy_protected",
    _CLASS_UNRECORDED: "unknown_identity_not_auto_deletable",
    _CLASS_UNTRUSTED: "untrusted_layout_not_auto_deletable",
}


class JobObjectRetentionError(RuntimeError):
    """Base class for job-object retention policy failures."""


class JobObjectRetentionValidationError(JobObjectRetentionError):
    """Raised when retention policy inputs violate the fail-closed contract."""


@dataclass(frozen=True)
class JobObjectRetentionDisposition:
    """Per-entry retention disposition under the current fail-closed policy."""

    relative_path: str
    classification: str
    disposition: str
    reason: str


@dataclass(frozen=True)
class JobObjectRetentionAssessment:
    """Aggregate policy assessment for an inventory snapshot.

    ``auto_delete_candidates`` is always empty under the current policy.
    No age/budget fields are defined here on purpose.
    """

    dispositions: tuple[JobObjectRetentionDisposition, ...]
    auto_delete_candidates: tuple[str, ...]


def assess_job_object_retention_policy(
    entries: Sequence[JobObjectInventoryEntry],
) -> JobObjectRetentionAssessment:
    """Assess retention eligibility without mutation or auto-delete invention.

    Safety invariants:

    - known classifications map only to ``never_auto_delete``;
    - auto-delete candidate tuple is always empty;
    - unknown classifications fail closed;
    - filesystem state is never read or written by this function.
    """
    dispositions: list[JobObjectRetentionDisposition] = []
    for entry in entries:
        classification = str(getattr(entry, "classification", "") or "").strip()
        reason = _REASON_BY_CLASSIFICATION.get(classification)
        if reason is None:
            raise JobObjectRetentionValidationError(
                f"unknown inventory classification is not auto-deletable: "
                f"{classification!r}"
            )
        relative_path = str(getattr(entry, "relative_path", "") or "")
        dispositions.append(
            JobObjectRetentionDisposition(
                relative_path=relative_path,
                classification=classification,
                disposition=_DISPOSITION_NEVER_AUTO_DELETE,
                reason=reason,
            )
        )
    return JobObjectRetentionAssessment(
        dispositions=tuple(dispositions),
        auto_delete_candidates=(),
    )

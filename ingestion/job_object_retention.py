"""Fail-closed retention policy + guarded command for job objects.

Plan slices:

- **2.4g** — policy assessment (ownership findings encoded as code).
- **2.4h** — guarded retention command requiring exact
  ``expected_candidates``; under current policy only ``()`` is valid and
  execution is a no-op (no filesystem mutation).

Ownership findings:

- Create path owner: ``api/routers/upload.py`` (slice 2.4a) — not a GC path.
- Durable reference: ``IngestionJob.source_path``.
- Classification / tenant preview: ``ingestion.job_object_inventory``
  (slices 2.4e / 2.4f).
- Index retention (``vectordb.*``) is a **separate** Chroma subsystem and
  must not delete ``job-objects/**`` or ``legacy-previous/**``.
- No age/budget deletion thresholds are defined here.

Policy (current, fail-closed):

- every known inventory classification is ``never_auto_delete``;
- ``auto_delete_candidates`` is always empty;
- unknown classifications raise validation errors;
- this module never deletes, renames, or mutates filesystem state.

Guarded command (2.4h):

- requires keyword-only ``expected_candidates`` as a tuple of unique
  non-empty strings (empty tuple allowed);
- recomputes policy candidates from supplied inventory entries;
- conflicts when expected ≠ current candidates;
- on match, returns ``status=complete`` with ``deleted=()`` and never
  mutates the filesystem.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ingestion.job_object_inventory import JobObjectInventoryEntry

_DISPOSITION_NEVER_AUTO_DELETE = "never_auto_delete"
_STATUS_COMPLETE = "complete"

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


class JobObjectRetentionExecutionConflict(JobObjectRetentionError):
    """Raised when expected candidates do not match recomputed policy candidates."""


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


@dataclass(frozen=True)
class JobObjectRetentionExecutionResult:
    """Result of a guarded job-object retention command (plan 2.4h).

    Under the current policy ``deleted`` is always empty — the command is a
    validated no-op when ``expected_candidates`` matches policy candidates.
    """

    tenant_id: str
    expected_candidates: tuple[str, ...]
    deleted: tuple[str, ...]
    status: str


def _normalize_tenant_id(tenant_id: str | None) -> str:
    raw = str(tenant_id or "").strip()
    return raw if raw else "default"


def _require_expected_candidates(
    expected_candidates: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(expected_candidates, tuple):
        raise JobObjectRetentionValidationError(
            "expected_candidates must be a tuple of unique non-empty str"
        )
    seen: set[str] = set()
    for candidate in expected_candidates:
        if not isinstance(candidate, str) or not candidate:
            raise JobObjectRetentionValidationError(
                "expected_candidates must be a tuple of unique non-empty str"
            )
        if candidate in seen:
            raise JobObjectRetentionValidationError(
                "expected_candidates must be a tuple of unique non-empty str"
            )
        seen.add(candidate)
    return expected_candidates


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


def execute_job_object_retention(
    *,
    tenant_id: str,
    entries: Sequence[JobObjectInventoryEntry],
    expected_candidates: tuple[str, ...],
) -> JobObjectRetentionExecutionResult:
    """Guarded retention command: exact candidates required; no FS mutation.

    Recomputes policy candidates from ``entries`` and refuses to proceed when
    ``expected_candidates`` differs. Under the current fail-closed policy the
    only valid expected tuple is empty, so a successful call is always a
    no-op with ``deleted=()``.
    """
    normalized_tenant = _normalize_tenant_id(tenant_id)
    expected = _require_expected_candidates(expected_candidates)
    assessment = assess_job_object_retention_policy(entries)
    if expected != assessment.auto_delete_candidates:
        raise JobObjectRetentionExecutionConflict(
            "expected_candidates do not match current retention candidates"
        )
    # Current policy: zero candidates → no deletions, no filesystem I/O.
    return JobObjectRetentionExecutionResult(
        tenant_id=normalized_tenant,
        expected_candidates=expected,
        deleted=(),
        status=_STATUS_COMPLETE,
    )

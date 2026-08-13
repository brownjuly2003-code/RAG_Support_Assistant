#!/usr/bin/env python3
"""Read-only preflight for a target-specific Chroma artifact activation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_CANDIDATE = "rag_docs-v-default-3f2b79fbe1246ab3"
DEFAULT_PREVIOUS_COLLECTION = "rag_docs_default"
DEFAULT_KNOWN_QUERY = "Что означает ошибка E20?"
DEFAULT_REQUIRED_DOC_ID = "errors_e10_e30.md"
DEFAULT_SOURCE_DOCUMENTS = frozenset(
    {"errors_e10_e30.md", "returns_policy.md", "warranty.md"}
)


class PreflightError(RuntimeError):
    """Activation cannot proceed safely with the supplied inputs."""


@dataclass(frozen=True)
class TreeFingerprint:
    file_count: int
    size_bytes: int
    sha256: str


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def fingerprint_tree(path: Path) -> TreeFingerprint:
    """Hash relative names and bytes without modifying the directory tree."""
    root = Path(path)
    if root.is_symlink():
        raise PreflightError(f"directory must not be a symlink: {root}")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise PreflightError(f"directory is unavailable: {root}") from exc
    if not resolved.is_dir():
        raise PreflightError(f"path is not a directory: {resolved}")
    if not (resolved / "chroma.sqlite3").is_file():
        raise PreflightError(f"Chroma directory lacks chroma.sqlite3: {resolved}")

    hasher = hashlib.sha256()
    file_count = 0
    size_bytes = 0
    entries = sorted(resolved.rglob("*"), key=lambda item: item.relative_to(resolved).as_posix())
    for entry in entries:
        if entry.is_symlink():
            raise PreflightError(f"Chroma tree contains a symlink: {entry}")
        if not entry.is_file():
            continue
        relative = entry.relative_to(resolved).as_posix().encode("utf-8")
        hasher.update(len(relative).to_bytes(8, "big"))
        hasher.update(relative)
        file_size = entry.stat().st_size
        hasher.update(file_size.to_bytes(8, "big"))
        with entry.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        file_count += 1
        size_bytes += file_size
    if file_count == 0:
        raise PreflightError(f"Chroma directory is empty: {resolved}")
    return TreeFingerprint(
        file_count=file_count,
        size_bytes=size_bytes,
        sha256=hasher.hexdigest(),
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_paths(
    source_dir: Path,
    target_dir: Path,
    snapshot_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    if source_dir.is_symlink() or target_dir.is_symlink():
        raise PreflightError("source and target must not be symlinks")
    try:
        source = source_dir.resolve(strict=True)
        target = target_dir.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("source and target directories must exist") from exc
    if not source.is_dir() or not target.is_dir():
        raise PreflightError("source and target must be directories")
    if source == target or _is_within(source, target) or _is_within(target, source):
        raise PreflightError("source and target directories overlap")

    if snapshot_dir.exists() or snapshot_dir.is_symlink():
        raise PreflightError("snapshot path must not already exist")
    try:
        snapshot_parent = snapshot_dir.parent.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("snapshot parent directory must exist") from exc
    snapshot = snapshot_dir.resolve(strict=False)
    if (
        snapshot == source
        or snapshot == target
        or _is_within(snapshot, source)
        or _is_within(snapshot, target)
        or _is_within(source, snapshot)
        or _is_within(target, snapshot)
    ):
        raise PreflightError("snapshot path overlaps source or target")
    return source, target, snapshot, snapshot_parent


def _load_evidence(path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise PreflightError("expected evidence SHA-256 must be 64 hexadecimal characters")
    if path.is_symlink():
        raise PreflightError("evidence file must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("evidence file is unavailable") from exc
    if not resolved.is_file():
        raise PreflightError("evidence path is not a file")
    actual = _hash_file(resolved)
    if actual != expected:
        raise PreflightError("evidence SHA-256 mismatch")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("evidence JSON is unreadable") from exc
    if not isinstance(payload, dict):
        raise PreflightError("evidence JSON must be an object")
    return payload, actual


def _validate_evidence(
    payload: dict[str, Any],
    *,
    expected_candidate: str,
    expected_count: int,
    expected_dimension: int,
    expected_previous_collection: str,
    expected_generation: int,
) -> dict[str, Any]:
    if payload.get("status") != "passed":
        raise PreflightError("artifact evidence status is not passed")
    if payload.get("tenant_id") != "default":
        raise PreflightError("artifact evidence tenant is not default")
    if payload.get("collection_deletions") != []:
        raise PreflightError("artifact evidence contains collection deletions")

    manifest = payload.get("final_manifest")
    if not isinstance(manifest, dict):
        raise PreflightError("artifact evidence lacks final_manifest")
    if manifest.get("schema_version") != 1:
        raise PreflightError("artifact manifest schema version mismatch")
    if manifest.get("active_collection") != expected_candidate:
        raise PreflightError("active collection does not match expected candidate")
    if manifest.get("previous_collection") != expected_previous_collection:
        raise PreflightError("previous collection does not match rollback target")
    if manifest.get("generation") != expected_generation:
        raise PreflightError("manifest generation mismatch")

    collections = payload.get("after_collections")
    if not isinstance(collections, list):
        raise PreflightError("artifact evidence lacks after_collections")
    matches = [
        item
        for item in collections
        if isinstance(item, dict) and item.get("name") == expected_candidate
    ]
    if len(matches) != 1:
        raise PreflightError("expected candidate must appear exactly once")
    candidate = matches[0]
    if candidate.get("count") != expected_count:
        raise PreflightError("candidate count mismatch")
    if candidate.get("dimension") != expected_dimension:
        raise PreflightError("candidate dimension mismatch")

    if payload.get("known_query") != DEFAULT_KNOWN_QUERY:
        raise PreflightError("known-query evidence mismatch")
    doc_ids = payload.get("known_query_doc_ids")
    if not isinstance(doc_ids, list) or DEFAULT_REQUIRED_DOC_ID not in doc_ids:
        raise PreflightError("known-query evidence lacks required document")
    source_documents = payload.get("source_documents")
    if not isinstance(source_documents, list) or set(source_documents) != DEFAULT_SOURCE_DOCUMENTS:
        raise PreflightError("source document set mismatch")
    return candidate


def build_activation_plan(
    *,
    source_dir: Path,
    target_dir: Path,
    snapshot_dir: Path,
    evidence_path: Path,
    expected_evidence_sha256: str,
    expected_source_sha256: str,
    expected_candidate: str = DEFAULT_CANDIDATE,
    expected_count: int = 3,
    expected_dimension: int = 1024,
    expected_previous_collection: str = DEFAULT_PREVIOUS_COLLECTION,
    expected_generation: int = 3,
    available_free_bytes: int | None = None,
) -> dict[str, Any]:
    """Return an activation plan after read-only validation of all inputs."""
    source, target, snapshot, snapshot_parent = _validate_paths(
        Path(source_dir),
        Path(target_dir),
        Path(snapshot_dir),
    )
    evidence, evidence_sha256 = _load_evidence(
        Path(evidence_path),
        expected_evidence_sha256,
    )
    candidate = _validate_evidence(
        evidence,
        expected_candidate=expected_candidate,
        expected_count=expected_count,
        expected_dimension=expected_dimension,
        expected_previous_collection=expected_previous_collection,
        expected_generation=expected_generation,
    )
    source_fingerprint = fingerprint_tree(source)
    target_fingerprint = fingerprint_tree(target)
    expected_source = expected_source_sha256.strip().lower()
    if len(expected_source) != 64 or any(
        char not in "0123456789abcdef" for char in expected_source
    ):
        raise PreflightError(
            "expected source SHA-256 must be 64 hexadecimal characters"
        )
    if source_fingerprint.sha256 != expected_source:
        raise PreflightError("source tree SHA-256 mismatch")

    required_free_bytes = max(target_fingerprint.size_bytes * 2, 1)
    free_bytes = (
        shutil.disk_usage(snapshot_parent).free
        if available_free_bytes is None
        else int(available_free_bytes)
    )
    if free_bytes < required_free_bytes:
        raise PreflightError(
            "insufficient free space for a recoverable target snapshot: "
            f"need {required_free_bytes}, have {free_bytes} bytes"
        )

    return {
        "schema_version": 1,
        "ready": True,
        "mutation_performed": False,
        "source": {"path": str(source), **asdict(source_fingerprint)},
        "target": {"path": str(target), **asdict(target_fingerprint)},
        "snapshot": {
            "path": str(snapshot),
            "exists": False,
            "required_free_bytes": required_free_bytes,
            "available_free_bytes": free_bytes,
        },
        "evidence": {
            "path": str(Path(evidence_path).resolve(strict=True)),
            "sha256": evidence_sha256,
            "status": evidence["status"],
        },
        "candidate": {
            "name": candidate["name"],
            "count": candidate["count"],
            "dimension": candidate["dimension"],
        },
        "rollback": {
            "previous_collection": expected_previous_collection,
            "pre_activation_target_sha256": target_fingerprint.sha256,
        },
        "smoke": {
            "known_query": DEFAULT_KNOWN_QUERY,
            "required_doc_id": DEFAULT_REQUIRED_DOC_ID,
        },
        "next_steps": [
            "create and verify the target snapshot",
            "copy the staged artifact without deleting the snapshot",
            "run dimension, content, and known-query smoke checks",
            "restore the snapshot on any failed acceptance check",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-evidence-sha256", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-candidate", default=DEFAULT_CANDIDATE)
    parser.add_argument("--expected-count", type=int, default=3)
    parser.add_argument("--expected-dimension", type=int, default=1024)
    parser.add_argument("--expected-previous", default=DEFAULT_PREVIOUS_COLLECTION)
    parser.add_argument("--expected-generation", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        plan = build_activation_plan(
            source_dir=args.source,
            target_dir=args.target,
            snapshot_dir=args.snapshot,
            evidence_path=args.evidence,
            expected_evidence_sha256=args.expected_evidence_sha256,
            expected_source_sha256=args.expected_source_sha256,
            expected_candidate=args.expected_candidate,
            expected_count=args.expected_count,
            expected_dimension=args.expected_dimension,
            expected_previous_collection=args.expected_previous,
            expected_generation=args.expected_generation,
        )
    except PreflightError as exc:
        sys.stderr.write(f"activation preflight failed: {exc}\n")
        return 1
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

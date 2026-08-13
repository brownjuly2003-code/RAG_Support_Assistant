from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import index_activation_preflight as preflight  # noqa: E402

CANDIDATE = "rag_docs-v-default-3f2b79fbe1246ab3"


def _write_chroma(path: Path, marker: bytes) -> None:
    path.mkdir(parents=True)
    (path / "chroma.sqlite3").write_bytes(marker)
    segment = path / "segment-a"
    segment.mkdir()
    (segment / "data.bin").write_bytes(marker[::-1])


def _evidence() -> dict[str, object]:
    return {
        "after_collections": [
            {"count": 3, "dimension": 1024, "name": CANDIDATE},
            {"count": 6, "dimension": 3, "name": "rag_docs_default"},
        ],
        "collection_deletions": [],
        "final_manifest": {
            "active_collection": CANDIDATE,
            "generation": 3,
            "previous_collection": "rag_docs_default",
            "schema_version": 1,
        },
        "known_query": "Что означает ошибка E20?",
        "known_query_doc_ids": ["errors_e10_e30.md", "warranty.md"],
        "source_documents": [
            "errors_e10_e30.md",
            "returns_policy.md",
            "warranty.md",
        ],
        "status": "passed",
        "tenant_id": "default",
    }


def _write_evidence(path: Path, payload: dict[str, object] | None = None) -> str:
    path.write_text(
        json.dumps(payload or _evidence(), ensure_ascii=False),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "staging" / "chroma"
    target = tmp_path / "working" / "chroma"
    snapshot = tmp_path / "snapshots" / "before-activation"
    evidence = tmp_path / "result.json"
    _write_chroma(source, b"source-candidate")
    _write_chroma(target, b"working-legacy")
    snapshot.parent.mkdir(parents=True)
    return source, target, snapshot, evidence


def test_build_plan_validates_artifact_without_mutating_paths(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    evidence_sha = _write_evidence(evidence)
    source_before = preflight.fingerprint_tree(source)
    target_before = preflight.fingerprint_tree(target)

    plan = preflight.build_activation_plan(
        source_dir=source,
        target_dir=target,
        snapshot_dir=snapshot,
        evidence_path=evidence,
        expected_evidence_sha256=evidence_sha,
        expected_source_sha256=source_before.sha256,
        expected_candidate=CANDIDATE,
        expected_count=3,
        expected_dimension=1024,
        available_free_bytes=10_000_000,
    )

    assert plan["ready"] is True
    assert plan["mutation_performed"] is False
    assert plan["candidate"] == {
        "name": CANDIDATE,
        "count": 3,
        "dimension": 1024,
    }
    assert plan["rollback"]["previous_collection"] == "rag_docs_default"
    assert plan["smoke"]["required_doc_id"] == "errors_e10_e30.md"
    assert plan["source"]["sha256"] == source_before.sha256
    assert plan["target"]["sha256"] == target_before.sha256
    assert preflight.fingerprint_tree(source) == source_before
    assert preflight.fingerprint_tree(target) == target_before
    assert not snapshot.exists()


def test_wrong_evidence_hash_fails_closed(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    _write_evidence(evidence)

    with pytest.raises(preflight.PreflightError, match="evidence SHA-256 mismatch"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256="0" * 64,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("count", 2, "candidate count mismatch"),
        ("dimension", 3, "candidate dimension mismatch"),
    ],
)
def test_candidate_shape_mismatch_fails_closed(
    tmp_path: Path,
    field: str,
    value: int,
    message: str,
) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    payload = _evidence()
    candidate = payload["after_collections"][0]  # type: ignore[index]
    candidate[field] = value  # type: ignore[index]
    evidence_sha = _write_evidence(evidence, payload)

    with pytest.raises(preflight.PreflightError, match=message):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )


def test_deletion_evidence_fails_closed(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    payload = _evidence()
    payload["collection_deletions"] = ["rag_docs_default"]
    evidence_sha = _write_evidence(evidence, payload)

    with pytest.raises(preflight.PreflightError, match="collection deletions"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )


def test_unknown_manifest_schema_fails_closed(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    payload = _evidence()
    manifest = payload["final_manifest"]
    manifest["schema_version"] = 2  # type: ignore[index]
    evidence_sha = _write_evidence(evidence, payload)

    with pytest.raises(preflight.PreflightError, match="manifest schema"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )


@pytest.mark.parametrize("snapshot_mode", ["inside-target", "already-exists"])
def test_unsafe_snapshot_path_fails_closed(tmp_path: Path, snapshot_mode: str) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    evidence_sha = _write_evidence(evidence)
    if snapshot_mode == "inside-target":
        snapshot = target / "snapshot"
    else:
        snapshot.mkdir()

    with pytest.raises(preflight.PreflightError, match="snapshot"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )


def test_insufficient_snapshot_capacity_fails_closed(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    evidence_sha = _write_evidence(evidence)

    with pytest.raises(preflight.PreflightError, match="insufficient free space"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256=preflight.fingerprint_tree(source).sha256,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=1,
        )


def test_source_tree_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    source, target, snapshot, evidence = _paths(tmp_path)
    evidence_sha = _write_evidence(evidence)

    with pytest.raises(preflight.PreflightError, match="source tree SHA-256 mismatch"):
        preflight.build_activation_plan(
            source_dir=source,
            target_dir=target,
            snapshot_dir=snapshot,
            evidence_path=evidence,
            expected_evidence_sha256=evidence_sha,
            expected_source_sha256="0" * 64,
            expected_candidate=CANDIDATE,
            expected_count=3,
            expected_dimension=1024,
            available_free_bytes=10_000_000,
        )

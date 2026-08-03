from __future__ import annotations

import importlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _manifest_module() -> ModuleType:
    return importlib.import_module("vectordb.index_manifest")


@contextmanager
def _held_tenant_lock(
    monkeypatch: pytest.MonkeyPatch,
    tenant_id: str,
) -> Iterator[Any]:
    from vectordb import tenant_lock

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    with tenant_lock.tenant_index_lock(tenant_id) as lock_token:
        yield lock_token


def test_missing_manifest_resolves_legacy_collection(tmp_path: Path) -> None:
    manifest = _manifest_module()
    from vectordb.manager import _collection_name

    chroma_directory = tmp_path / "vectordb" / "chroma"

    assert manifest.resolve_active_collection(
        "a/b",
        chroma_directory=chroma_directory,
    ) == _collection_name("a/b")
    assert not manifest.index_manifest_path(
        "a/b",
        chroma_directory=chroma_directory,
    ).exists()


def test_manifest_paths_are_tenant_safe_and_stay_in_the_registry(
    tmp_path: Path,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    expected_root = chroma_directory.parent / "index-manifests"

    slash = manifest.index_manifest_path(
        "a/b",
        chroma_directory=chroma_directory,
    )
    question = manifest.index_manifest_path(
        "a?b",
        chroma_directory=chroma_directory,
    )

    assert slash != question
    assert slash.parent == expected_root
    assert question.parent == expected_root
    assert re.fullmatch(r"a_b--[0-9a-f]{16}\.json", slash.name)
    assert re.fullmatch(r"a_b--[0-9a-f]{16}\.json", question.name)
    assert slash.resolve().is_relative_to(expected_root.resolve())
    assert question.resolve().is_relative_to(expected_root.resolve())


def test_malformed_manifest_fails_closed_instead_of_using_a_collection(
    tmp_path: Path,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 1, "active_collection": ', encoding="utf-8")

    with pytest.raises(manifest.IndexManifestCorrupt, match="manifest"):
        manifest.resolve_active_collection(
            "acme",
            chroma_directory=chroma_directory,
        )

    path.write_text(
        json.dumps(
            {
                "schema_version": 1.0,
                "active_collection": "rag_docs_acme_v1",
                "previous_collection": None,
                "generation": 1,
                "updated_at": "2026-08-03T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(manifest.IndexManifestCorrupt, match="manifest"):
        manifest.resolve_active_collection(
            "acme",
            chroma_directory=chroma_directory,
        )


def test_atomic_publish_preserves_previous_collection_and_increments_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        first = manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        second = manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v2",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    assert first.active_collection == "rag_docs_acme_v1"
    assert first.previous_collection is None
    assert first.generation == 1
    assert second.active_collection == "rag_docs_acme_v2"
    assert second.previous_collection == "rag_docs_acme_v1"
    assert second.generation == 2
    assert datetime.fromisoformat(second.updated_at).tzinfo is not None

    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "active_collection",
        "previous_collection",
        "generation",
        "updated_at",
    }
    assert payload == {
        "schema_version": 1,
        "active_collection": "rag_docs_acme_v2",
        "previous_collection": "rag_docs_acme_v1",
        "generation": 2,
        "updated_at": second.updated_at,
    }


def test_atomic_rollback_swaps_active_and_previous_and_increments_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v2",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        rolled_back = manifest.rollback_active_collection(
            "acme",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )

    assert rolled_back.active_collection == "rag_docs_acme_v1"
    assert rolled_back.previous_collection == "rag_docs_acme_v2"
    assert rolled_back.generation == 3

    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "active_collection": "rag_docs_acme_v1",
        "previous_collection": "rag_docs_acme_v2",
        "generation": 3,
        "updated_at": rolled_back.updated_at,
    }


def test_rollback_without_previous_fails_closed_and_preserves_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(manifest.IndexManifestRollbackUnavailable, match="previous"):
            manifest.rollback_active_collection(
                "acme",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )
        assert not path.exists()

        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        before = path.read_bytes()
        with pytest.raises(manifest.IndexManifestRollbackUnavailable, match="previous"):
            manifest.rollback_active_collection(
                "acme",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert path.read_bytes() == before


def test_rollback_requires_a_current_matching_tenant_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    from vectordb import tenant_lock

    chroma_directory = tmp_path / "vectordb" / "chroma"
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v2",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
            manifest.rollback_active_collection(
                "acme",
                lock_token=None,
                chroma_directory=chroma_directory,
            )
        with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="tenant"):
            manifest.rollback_active_collection(
                "beta",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        manifest.rollback_active_collection(
            "acme",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


def test_rollback_replace_failure_preserves_manifest_byte_for_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v2",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        before = path.read_bytes()

        def _fail_replace(source: str | Path, destination: str | Path) -> None:
            _ = source, destination
            raise OSError("rollback replace failed")

        monkeypatch.setattr(manifest.os, "replace", _fail_replace)
        with pytest.raises(OSError, match="rollback replace failed"):
            manifest.rollback_active_collection(
                "acme",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert path.read_bytes() == before


def test_replace_failure_leaves_existing_manifest_byte_for_byte_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"
    path = manifest.index_manifest_path("acme", chroma_directory=chroma_directory)

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
    before = path.read_bytes()

    def _fail_replace(source: str | Path, destination: str | Path) -> None:
        _ = source, destination
        raise OSError("replace failed")

    monkeypatch.setattr(manifest.os, "replace", _fail_replace)
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(OSError, match="replace failed"):
            manifest.publish_active_collection(
                "acme",
                "rag_docs_acme_v2",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_manifest_writer_requires_a_current_matching_tenant_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    from vectordb import tenant_lock

    chroma_directory = tmp_path / "vectordb" / "chroma"
    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=None,
            chroma_directory=chroma_directory,
        )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="tenant"):
            manifest.publish_active_collection(
                "beta",
                "rag_docs_beta_v1",
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        manifest.publish_active_collection(
            "acme",
            "rag_docs_acme_v1",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )


def test_manifest_rejects_collection_names_over_chroma_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    chroma_directory = tmp_path / "vectordb" / "chroma"

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(manifest.IndexManifestValidationError, match="63"):
            manifest.publish_active_collection(
                "acme",
                "x" * 64,
                lock_token=lock_token,
                chroma_directory=chroma_directory,
            )

    assert not manifest.index_manifest_path(
        "acme",
        chroma_directory=chroma_directory,
    ).exists()

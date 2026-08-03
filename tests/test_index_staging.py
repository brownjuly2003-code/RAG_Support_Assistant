from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_CANDIDATE_ID = "0123456789abcdef"


def _staging_module() -> ModuleType:
    return importlib.import_module("vectordb.index_staging")


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


class _FakeChromaState:
    def __init__(self) -> None:
        self.count_override: int | None = None
        self.required_dimension = 3
        self.fail_build = False
        self.fail_delete = False
        self.built_names: list[str] = []
        self.opened_names: list[str] = []
        self.persisted_names: list[str] = []
        self.deleted_names: list[str] = []
        self.query_dimensions: list[int] = []
        self.counts: dict[str, int] = {}


def _fake_chroma(state: _FakeChromaState) -> type[Any]:
    class _Collection:
        def __init__(self, collection_name: str) -> None:
            self._collection_name = collection_name

        def count(self) -> int:
            if state.count_override is not None:
                return state.count_override
            return state.counts[self._collection_name]

        def query(
            self,
            *,
            query_embeddings: list[list[float]],
            n_results: int,
        ) -> dict[str, list[list[str]]]:
            assert n_results == 1
            dimension = len(query_embeddings[0])
            state.query_dimensions.append(dimension)
            if dimension != state.required_dimension:
                raise ValueError(
                    f"Collection expects dimension {state.required_dimension}, got {dimension}"
                )
            return {"ids": [["candidate-chunk"]]}

    class _FakeChroma:
        def __init__(
            self,
            *,
            persist_directory: str,
            embedding_function: Any,
            collection_name: str,
        ) -> None:
            _ = persist_directory, embedding_function
            self.collection_name = collection_name
            self._collection = _Collection(collection_name)
            state.opened_names.append(collection_name)

        @classmethod
        def from_documents(
            cls,
            *,
            documents: list[Any],
            embedding: Any,
            persist_directory: str,
            collection_name: str,
        ) -> Any:
            state.built_names.append(collection_name)
            state.counts[collection_name] = len(documents)
            if state.fail_build:
                raise RuntimeError("candidate build failed")
            return cls(
                persist_directory=persist_directory,
                embedding_function=embedding,
                collection_name=collection_name,
            )

        def persist(self) -> None:
            state.persisted_names.append(self.collection_name)

        def delete_collection(self) -> None:
            if state.fail_delete:
                raise RuntimeError("candidate delete failed")
            state.deleted_names.append(self.collection_name)

    return _FakeChroma


class _Embeddings:
    def __init__(self, dimension: int = 3) -> None:
        self._dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        assert text
        return [0.0] * self._dimension


def test_staged_collection_names_are_versioned_collision_resistant_and_bounded() -> None:
    staging = _staging_module()
    from vectordb.manager import _collection_name

    slash = staging.staged_collection_name("a/b", candidate_id=_CANDIDATE_ID)
    question = staging.staged_collection_name("a?b", candidate_id=_CANDIDATE_ID)
    long_a = staging.staged_collection_name("x" * 100 + "a", candidate_id=_CANDIDATE_ID)
    long_b = staging.staged_collection_name("x" * 100 + "b", candidate_id=_CANDIDATE_ID)

    assert slash != question
    assert long_a != long_b
    assert all(len(name) <= 63 for name in (slash, question, long_a, long_b))
    assert all(name.startswith("rag_docs-v-") for name in (slash, question))
    assert all(name.endswith(f"-{_CANDIDATE_ID}") for name in (slash, question))
    assert slash != _collection_name(f"v-a_b-{_CANDIDATE_ID}")
    for invalid_candidate_id in ("", "../not-safe"):
        with pytest.raises(staging.IndexStagingValidationError, match="candidate"):
            staging.staged_collection_name(
                "acme",
                candidate_id=invalid_candidate_id,
            )


def test_staging_build_validates_count_and_dimension_without_switching_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = _staging_module()
    from vectordb.index_manifest import index_manifest_path, publish_active_collection

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    chroma_cls = _fake_chroma(state)

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        publish_active_collection(
            "acme",
            "rag_docs_acme",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        manifest_path = index_manifest_path(
            "acme",
            chroma_directory=chroma_directory,
        )
        manifest_before = manifest_path.read_bytes()
        candidate = staging.build_staged_collection(
            [object(), object()],
            _Embeddings(),
            tenant_id="acme",
            lock_token=lock_token,
            chroma_cls=chroma_cls,
            chroma_directory=chroma_directory,
            candidate_id=_CANDIDATE_ID,
        )

    assert candidate.collection_name != "rag_docs_acme"
    assert candidate.chunk_count == 2
    assert candidate.embedding_dimension == 3
    assert state.built_names == [candidate.collection_name]
    assert state.persisted_names == [candidate.collection_name]
    assert state.query_dimensions == [3]
    assert state.deleted_names == []
    assert "rag_docs_acme" not in state.opened_names
    assert manifest_path.read_bytes() == manifest_before


def test_count_mismatch_deletes_only_the_unpublished_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = _staging_module()
    from vectordb.index_manifest import index_manifest_path, publish_active_collection

    chroma_directory = tmp_path / "vectordb" / "chroma"
    state = _FakeChromaState()
    state.count_override = 1
    candidate_name = staging.staged_collection_name(
        "acme",
        candidate_id=_CANDIDATE_ID,
    )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        publish_active_collection(
            "acme",
            "rag_docs_acme",
            lock_token=lock_token,
            chroma_directory=chroma_directory,
        )
        manifest_path = index_manifest_path("acme", chroma_directory=chroma_directory)
        manifest_before = manifest_path.read_bytes()
        with pytest.raises(staging.IndexStagingValidationError, match="count"):
            staging.build_staged_collection(
                [object(), object()],
                _Embeddings(),
                tenant_id="acme",
                lock_token=lock_token,
                chroma_cls=_fake_chroma(state),
                chroma_directory=chroma_directory,
                candidate_id=_CANDIDATE_ID,
            )

    assert state.deleted_names == [candidate_name]
    assert "rag_docs_acme" not in state.deleted_names
    assert manifest_path.read_bytes() == manifest_before


def test_dimension_mismatch_deletes_only_the_unpublished_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = _staging_module()
    state = _FakeChromaState()
    state.required_dimension = 4
    candidate_name = staging.staged_collection_name(
        "acme",
        candidate_id=_CANDIDATE_ID,
    )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(staging.IndexStagingValidationError, match="dimension"):
            staging.build_staged_collection(
                [object()],
                _Embeddings(dimension=3),
                tenant_id="acme",
                lock_token=lock_token,
                chroma_cls=_fake_chroma(state),
                chroma_directory=tmp_path / "vectordb" / "chroma",
                candidate_id=_CANDIDATE_ID,
            )

    assert state.deleted_names == [candidate_name]
    assert "rag_docs_acme" not in state.deleted_names


def test_partial_build_failure_cleans_up_only_its_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = _staging_module()
    state = _FakeChromaState()
    state.fail_build = True
    candidate_name = staging.staged_collection_name(
        "acme",
        candidate_id=_CANDIDATE_ID,
    )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(staging.IndexStagingBuildError, match="build"):
            staging.build_staged_collection(
                [object()],
                _Embeddings(),
                tenant_id="acme",
                lock_token=lock_token,
                chroma_cls=_fake_chroma(state),
                chroma_directory=tmp_path / "vectordb" / "chroma",
                candidate_id=_CANDIDATE_ID,
            )

    assert state.deleted_names == [candidate_name]
    assert state.opened_names == [candidate_name]
    assert "rag_docs_acme" not in state.deleted_names

    state.fail_delete = True
    second_candidate_id = "fedcba9876543210"
    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(staging.IndexStagingCleanupError) as exc_info:
            staging.build_staged_collection(
                [object()],
                _Embeddings(),
                tenant_id="acme",
                lock_token=lock_token,
                chroma_cls=_fake_chroma(state),
                chroma_directory=tmp_path / "vectordb" / "chroma",
                candidate_id=second_candidate_id,
            )
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "candidate delete failed"


def test_staging_requires_a_lock_and_nonempty_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = _staging_module()
    from vectordb import tenant_lock

    state = _FakeChromaState()
    kwargs = {
        "tenant_id": "acme",
        "chroma_cls": _fake_chroma(state),
        "chroma_directory": tmp_path / "vectordb" / "chroma",
        "candidate_id": _CANDIDATE_ID,
    }
    with pytest.raises(tenant_lock.TenantIndexLockUnavailable, match="held"):
        staging.build_staged_collection(
            [object()],
            _Embeddings(),
            lock_token=None,
            **kwargs,
        )

    with _held_tenant_lock(monkeypatch, "acme") as lock_token:
        with pytest.raises(staging.IndexStagingValidationError, match="empty"):
            staging.build_staged_collection(
                [],
                _Embeddings(),
                lock_token=lock_token,
                **kwargs,
            )

    assert state.built_names == []
    assert state.deleted_names == []

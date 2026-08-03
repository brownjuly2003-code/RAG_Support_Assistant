from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        return self._value


class _AdvisoryLockRegistry:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._owners: dict[int, int] = {}
        self._next_owner = 0

    def connect(self) -> _FakeConnection:
        with self._guard:
            self._next_owner += 1
            owner = self._next_owner
        return _FakeConnection(self, owner)

    def execute(self, owner: int, statement: Any, params: dict[str, int]) -> _ScalarResult:
        sql = str(statement)
        key = params["lock_key"]
        with self._guard:
            if "pg_try_advisory_lock" in sql:
                if key in self._owners:
                    return _ScalarResult(False)
                self._owners[key] = owner
                return _ScalarResult(True)
            if "pg_advisory_unlock" in sql:
                if self._owners.get(key) != owner:
                    return _ScalarResult(False)
                self._owners.pop(key, None)
                return _ScalarResult(True)
        raise AssertionError(f"Unexpected advisory-lock statement: {sql}")

    def close(self, owner: int) -> None:
        with self._guard:
            for key, current_owner in list(self._owners.items()):
                if current_owner == owner:
                    self._owners.pop(key, None)


class _FakeConnection:
    def __init__(self, registry: _AdvisoryLockRegistry, owner: int) -> None:
        self._registry = registry
        self._owner = owner

    def execute(self, statement: Any, params: dict[str, int]) -> _ScalarResult:
        return self._registry.execute(self._owner, statement, params)

    def close(self) -> None:
        self._registry.close(self._owner)


def test_same_tenant_rebuilds_are_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    from vectordb import tenant_lock

    registry = _AdvisoryLockRegistry()
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 1.0)

    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    failures: list[BaseException] = []

    def _first() -> None:
        try:
            with tenant_lock.tenant_index_lock("acme"):
                first_entered.set()
                assert release_first.wait(timeout=2)
        except BaseException as exc:  # pragma: no cover - relayed to main thread
            failures.append(exc)

    def _second() -> None:
        try:
            assert first_entered.wait(timeout=2)
            with tenant_lock.tenant_index_lock("acme"):
                second_entered.set()
        except BaseException as exc:  # pragma: no cover - relayed to main thread
            failures.append(exc)

    first = threading.Thread(target=_first)
    second = threading.Thread(target=_second)
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()

    assert not second_entered.wait(timeout=0.05)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert second_entered.is_set()


def test_different_tenants_use_independent_lock_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from vectordb import tenant_lock

    registry = _AdvisoryLockRegistry()
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)

    with tenant_lock.tenant_index_lock("acme"):
        with tenant_lock.tenant_index_lock("beta"):
            pass

    assert tenant_lock._lock_key("acme") == tenant_lock._lock_key("acme")
    assert tenant_lock._lock_key("acme") != tenant_lock._lock_key("beta")


def test_lock_timeout_fails_closed_and_does_not_steal_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb import tenant_lock

    registry = _AdvisoryLockRegistry()
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.01)

    with tenant_lock.tenant_index_lock("acme"):
        with pytest.raises(tenant_lock.TenantIndexLockTimeout, match="already in progress"):
            with tenant_lock.tenant_index_lock("acme"):
                raise AssertionError("contender must not enter the protected rebuild")


def test_lock_is_released_when_rebuild_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from vectordb import tenant_lock

    registry = _AdvisoryLockRegistry()
    monkeypatch.setattr(tenant_lock, "_open_lock_connection", registry.connect)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)

    with pytest.raises(RuntimeError, match="embed failed"):
        with tenant_lock.tenant_index_lock("acme"):
            raise RuntimeError("embed failed")

    with tenant_lock.tenant_index_lock("acme"):
        pass


def test_lock_connection_failure_is_fail_closed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb import tenant_lock

    def _fail_connect() -> Any:
        raise RuntimeError("postgresql://rag:super-secret@db/rag")

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _fail_connect)

    with pytest.raises(tenant_lock.TenantIndexLockUnavailable) as exc_info:
        with tenant_lock.tenant_index_lock("acme"):
            pass

    assert "super-secret" not in str(exc_info.value)
    assert "unavailable" in str(exc_info.value).lower()


def test_main_and_factcard_rebuilds_hold_the_tenant_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vectordb import manager, tenant_lock

    events: list[str] = []
    lock_held = False

    class _Connection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(tenant_lock, "_open_lock_connection", _Connection)
    monkeypatch.setattr(tenant_lock, "_wait_timeout_sec", lambda: 0.0)
    monkeypatch.setattr(tenant_lock, "_acquire", lambda *args: None)
    monkeypatch.setattr(tenant_lock, "_release", lambda *args: None)

    @contextmanager
    def _lock(tenant_id: str):
        nonlocal lock_held
        events.append(f"enter:{tenant_id}")
        with tenant_lock.tenant_index_lock(tenant_id) as lock_token:
            lock_held = True
            try:
                yield lock_token
            finally:
                lock_held = False
                events.append(f"exit:{tenant_id}")

    class _Embeddings:
        def embed_query(self, text: str) -> list[float]:
            assert text
            return [0.0, 0.0, 0.0]

    class _Store:
        def __init__(self, documents: list[Any]) -> None:
            self.documents = list(documents)
            self._collection = self

        def persist(self) -> None:
            assert lock_held
            events.append("persist")

        def count(self) -> int:
            assert lock_held
            return len(self.documents)

        def query(self, **kwargs: Any) -> dict[str, list[list[str]]]:
            _ = kwargs
            assert lock_held
            events.append("dimension")
            return {"ids": [["chunk"]]}

        def similarity_search(self, query: str, *, k: int) -> list[Any]:
            _ = query
            assert lock_held
            events.append("known-query")
            return self.documents[:k]

        def delete_collection(self) -> None:
            assert lock_held
            events.append("delete")

    class _Chroma:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

        def delete_collection(self) -> None:
            assert lock_held
            events.append("delete")

        @classmethod
        def from_documents(cls, **kwargs: Any) -> _Store:
            assert lock_held
            events.append("build")
            return _Store(list(kwargs["documents"]))

    def _publish(
        tenant_id: str,
        active_collection: str,
        *,
        lock_token: Any,
        chroma_directory: Any,
    ) -> Any:
        _ = chroma_directory
        tenant_lock.require_tenant_index_lock(lock_token, tenant_id)
        assert lock_held
        events.append("publish")
        return SimpleNamespace(
            active_collection=active_collection,
            generation=1,
        )

    chroma_directory = tmp_path / "vectordb" / "chroma"
    settings = SimpleNamespace(
        vector_backend="chroma",
        vectordb_chroma_dir=chroma_directory,
        vectordb_collection_prefix="rag_docs",
        chunk_size=100,
        chunk_overlap=0,
        contextual_headers=False,
        rag_device="cpu",
        vectordb_retention_max_versions=2,
    )
    docs = [manager.Document(page_content="document", metadata={"source": "doc.md"})]

    monkeypatch.setattr(manager, "tenant_index_lock", _lock)
    monkeypatch.setattr(manager, "get_settings", lambda: settings)
    monkeypatch.setattr(manager, "_get_chroma", lambda: _Chroma)
    monkeypatch.setattr(manager, "publish_active_collection", _publish)
    monkeypatch.setattr(manager._base_manager, "select_chunks", lambda *args, **kwargs: docs)

    manager.build_vector_store(
        docs,
        {"chunk_size": 100, "chunk_overlap": 0},
        embeddings=_Embeddings(),
        tenant_id="acme",
    )
    assert events == [
        "enter:acme",
        "build",
        "persist",
        "dimension",
        "known-query",
        "publish",
        "exit:acme",
    ]

    events.clear()
    manager.build_factcard_store(docs, embeddings=object(), tenant_id="acme")
    assert events == ["enter:acme", "delete", "build", "persist", "exit:acme"]


def test_lock_wait_setting_rejects_non_finite_or_negative_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vectordb import tenant_lock

    for invalid in (-1.0, float("nan"), float("inf")):
        monkeypatch.setattr(
            tenant_lock,
            "get_settings",
            lambda value=invalid: SimpleNamespace(
                ingestion_tenant_lock_wait_sec=value
            ),
        )
        with pytest.raises(RuntimeError, match="INGESTION_TENANT_LOCK_WAIT_SEC"):
            tenant_lock._wait_timeout_sec()


def test_lock_wait_setting_defaults_validates_and_is_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.delenv("INGESTION_TENANT_LOCK_WAIT_SEC", raising=False)
    settings = Settings()
    assert settings.ingestion_tenant_lock_wait_sec == 30.0

    settings.ingestion_tenant_lock_wait_sec = -1.0
    with pytest.raises(RuntimeError, match="INGESTION_TENANT_LOCK_WAIT_SEC"):
        settings.validate()

    project_root = Path(__file__).resolve().parents[1]
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")
    config_docs = (project_root / "docs" / "CONFIGURATION.md").read_text(
        encoding="utf-8"
    )
    deployment_docs = (project_root / "docs" / "DEPLOYMENT.md").read_text(
        encoding="utf-8"
    )
    assert "INGESTION_TENANT_LOCK_WAIT_SEC" in env_example
    assert "INGESTION_TENANT_LOCK_WAIT_SEC" in config_docs
    assert "pg_try_advisory_lock" in deployment_docs

"""Plan step 4.4 core: upload idempotency + bounded broker publish retry.

Covers tenant-scoped HTTP Idempotency-Key, reserved Celery task identity,
source_ready_at ordering, and publish-only retry. Does not claim worker
autoretry, post-mutation requeue, queue-age alerts, or atomic index publish.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import io
import logging
import re
import sys
import threading
import types
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.jwt_handler import create_access_token
from db.models import IngestionJob

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = PROJECT_ROOT / "alembic" / "versions" / "021_ingestion_job_idempotency.py"

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
    "_DocumentLoader": None,
    "_build_vector_store": None,
}

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:~-]{16,128}$")
_VALID_KEY = "idem-key-abcdefgh"  # 18 chars, valid charset
_VALID_KEY_B = "idem-key-ijklmnop"
_INTERNAL_FIELDS = (
    "idempotency_key_hash",
    "payload_fingerprint",
    "source_ready_at",
)


def _headers(tenant: str = "default", role: str = "admin", **extra: str) -> dict[str, str]:
    token = create_access_token(f"user-{tenant}", role, tenant)
    out = {"Authorization": f"Bearer {token}"}
    out.update(extra)
    return out


def _api_key(**extra: str) -> dict[str, str]:
    out = {"X-API-Key": "secret123"}
    out.update(extra)
    return out


def _sha256_hex(data: bytes | str) -> str:
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _expected_key_hash(raw_key: str) -> str:
    return _sha256_hex(raw_key)


def _expected_fingerprint(safe_name: str, content: bytes) -> str:
    # Must bind normalized safe filename + exact uploaded bytes.
    h = hashlib.sha256()
    h.update(safe_name.encode("utf-8"))
    h.update(b"\0")
    h.update(content)
    return h.hexdigest()


def _load_migration() -> ModuleType:
    assert MIGRATION_PATH.is_file(), f"missing migration: {MIGRATION_PATH}"
    spec = importlib.util.spec_from_file_location(
        "migration_021_ingestion_job_idempotency",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _fetch_job(session_factory, job_id: str | uuid.UUID) -> IngestionJob | None:
    jid = job_id if isinstance(job_id, uuid.UUID) else uuid.UUID(str(job_id))
    async with session_factory() as session:
        result = await session.execute(select(IngestionJob).where(IngestionJob.id == jid))
        return result.scalar_one_or_none()


async def _count_jobs(session_factory) -> int:
    async with session_factory() as session:
        result = await session.execute(select(IngestionJob))
        return len(list(result.scalars().all()))


def _patch_apply_async(
    monkeypatch: pytest.MonkeyPatch,
    *,
    side_effect: Exception | None = None,
    capture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    captured = capture if capture is not None else {}

    def _apply_async(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured["calls"] = captured.get("calls", 0) + 1
        captured["args"] = kwargs.get("args")
        captured["task_id"] = kwargs.get("task_id")
        captured["retry"] = kwargs.get("retry")
        captured["retry_policy"] = kwargs.get("retry_policy")
        captured["kwargs"] = dict(kwargs)
        if side_effect is not None:
            raise side_effect
        task_id = kwargs.get("task_id") or "generated-task"
        return SimpleNamespace(id=task_id)

    fake_module = types.ModuleType("tasks.ingest_task")
    # Explicitly no delay / no autoretry attributes on the task surface.
    fake_module.ingest_document = SimpleNamespace(
        apply_async=_apply_async,
        autoretry_for=(),
        max_retries=0,
        name="tasks.ingest_document",
    )
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)
    return captured


def _silence_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.app as api_app

    async def _fake_log_audit(**kwargs: Any) -> None:
        return None

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)


# ---------------------------------------------------------------------------
# 15. Migration / ORM / non-exposure
# ---------------------------------------------------------------------------


def test_orm_has_idempotency_fields_and_partial_unique_index() -> None:
    table = IngestionJob.__table__
    cols = table.c
    assert "idempotency_key_hash" in cols
    assert cols.idempotency_key_hash.nullable is True
    assert cols.idempotency_key_hash.type.length == 64

    assert "payload_fingerprint" in cols
    assert cols.payload_fingerprint.nullable is True
    assert cols.payload_fingerprint.type.length == 64

    assert "source_ready_at" in cols
    assert cols.source_ready_at.nullable is True

    partial = None
    for idx in table.indexes:
        col_names = list(idx.columns.keys())
        if col_names == ["tenant_id", "idempotency_key_hash"] and idx.unique:
            partial = idx
            break
    assert partial is not None, "missing partial unique index on (tenant_id, idempotency_key_hash)"
    dialect_opts = getattr(partial, "dialect_options", {}) or {}
    pg = dialect_opts.get("postgresql", {}) or {}
    sqlite = dialect_opts.get("sqlite", {}) or {}
    pg_where_obj = pg.get("where")
    sqlite_where_obj = sqlite.get("where")
    pg_where = str(pg_where_obj) if pg_where_obj is not None else ""
    sqlite_where = str(sqlite_where_obj) if sqlite_where_obj is not None else ""
    assert "idempotency_key_hash" in pg_where
    assert "IS NOT NULL" in pg_where.upper() or "not null" in pg_where.lower()
    assert "idempotency_key_hash" in sqlite_where


def test_migration_021_revises_020_and_adds_partial_unique() -> None:
    module = _load_migration()
    assert module.revision == "021"
    assert module.down_revision == "020"

    upgrade_src = inspect.getsource(module.upgrade)
    downgrade_src = inspect.getsource(module.downgrade)
    assert "idempotency_key_hash" in upgrade_src
    assert "payload_fingerprint" in upgrade_src
    assert "source_ready_at" in upgrade_src
    assert "unique" in upgrade_src.lower() or "unique=True" in upgrade_src
    assert "postgresql_where" in upgrade_src
    assert "sqlite_where" in upgrade_src
    assert "idempotency_key_hash" in downgrade_src


def test_job_public_dict_omits_internal_idempotency_fields() -> None:
    from ingestion.jobs import job_public_dict

    job = IngestionJob(
        id=uuid.uuid4(),
        tenant_id="default",
        filename="a.txt",
        source_path="data/uploads/a.txt",
        status="queued",
        idempotency_key_hash="a" * 64,
        payload_fingerprint="b" * 64,
    )
    # source_ready_at may be set on the instance even if helper ignores it.
    job.source_ready_at = None
    public = job_public_dict(job)
    for field in _INTERNAL_FIELDS:
        assert field not in public
        assert field not in str(public)


# ---------------------------------------------------------------------------
# 1. Compatibility: no key twice -> distinct jobs
# ---------------------------------------------------------------------------


def test_no_key_twice_creates_distinct_jobs(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    body_bytes = b"same-body-no-key"
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("n1.txt", io.BytesIO(body_bytes), "text/plain")},
        headers=_api_key(),
    )
    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("n1.txt", io.BytesIO(body_bytes), "text/plain")},
        headers=_api_key(),
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["job_id"] != r2.json()["job_id"]
    assert r1.json().get("idempotency_replayed") is False
    assert r2.json().get("idempotency_replayed") is False
    assert captured.get("calls", 0) == 2


# ---------------------------------------------------------------------------
# 2. Same key/body -> same job/task + replay marker
# ---------------------------------------------------------------------------


def test_same_key_same_body_replays_identity_without_second_write(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    content = b"idempotent-payload-v1"
    headers = _api_key(**{"Idempotency-Key": _VALID_KEY})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("doc.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1.get("idempotency_replayed") is False
    job_id = body1["job_id"]
    task_id = body1["task_id"]
    assert task_id == f"ingest-{job_id}"

    path = tmp_path / "data" / "uploads" / "doc.txt"
    assert path.read_bytes() == content
    mtime1 = path.stat().st_mtime_ns

    # Terminal state: completed. Replay must not re-publish / re-write.
    import asyncio as _asyncio

    async def _complete() -> None:
        from ingestion.jobs import mark_job_completed

        await mark_job_completed(uuid.UUID(job_id), "default", {"status": "ok"})

    _asyncio.run(_complete())

    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("doc.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["job_id"] == job_id
    assert body2["task_id"] == task_id
    assert body2.get("idempotency_replayed") is True
    assert body2["status"] == "ok"
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == mtime1
    # First create published once; terminal replay must not publish again.
    assert captured.get("calls", 0) == 1

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1


# ---------------------------------------------------------------------------
# 3. Same key / different bytes or filename -> 409
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("doc.txt", b"different-bytes"),
        ("other.txt", b"idempotent-payload-v1"),
    ],
)
def test_same_key_different_fingerprint_conflicts(
    filename: str,
    content: bytes,
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    _silence_audit(monkeypatch)
    _patch_apply_async(monkeypatch)

    original = b"idempotent-payload-v1"
    headers = _api_key(**{"Idempotency-Key": _VALID_KEY})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("doc.txt", io.BytesIO(original), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    path = tmp_path / "data" / "uploads" / "doc.txt"
    assert path.read_bytes() == original

    r2 = client_with_key.post(
        "/api/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 409
    detail = str(r2.json().get("detail", ""))
    assert "conflict" in detail.lower() or "idempotency" in detail.lower()
    assert _VALID_KEY not in detail
    assert path.read_bytes() == original
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1
    # Conflict must not create the alternate filename.
    if filename != "doc.txt":
        assert not (tmp_path / "data" / "uploads" / filename).exists()


# ---------------------------------------------------------------------------
# 4. Same key across tenants -> independent
# ---------------------------------------------------------------------------


def test_same_key_across_tenants_is_independent(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    async def _fake_log_audit(**kwargs: Any) -> None:
        return None

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "t.txt"})]

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    _patch_apply_async(monkeypatch)

    content = b"cross-tenant-body"
    key_headers = {"Idempotency-Key": _VALID_KEY}
    r_a = client_with_key.post(
        "/api/upload",
        files={"file": ("t.txt", io.BytesIO(content), "text/plain")},
        headers=_headers("tenant-a", **key_headers),
    )
    r_b = client_with_key.post(
        "/api/upload",
        files={"file": ("t.txt", io.BytesIO(content), "text/plain")},
        headers=_headers("tenant-b", **key_headers),
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json()["job_id"] != r_b.json()["job_id"]
    assert r_a.json()["tenant_id"] == "tenant-a"
    assert r_b.json()["tenant_id"] == "tenant-b"

    # Cross-tenant poll isolation.
    leak = client_with_key.get(
        f"/api/jobs/{r_a.json()['job_id']}",
        headers=_headers("tenant-b"),
    )
    assert leak.status_code == 404


# ---------------------------------------------------------------------------
# 5. X-Request-Id alone is not idempotency
# ---------------------------------------------------------------------------


def test_repeated_x_request_id_alone_is_not_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    _silence_audit(monkeypatch)
    _patch_apply_async(monkeypatch)

    headers = _api_key(**{"X-Request-Id": "req-aaaaaaaaaaaa"})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("x.txt", io.BytesIO(b"a"), "text/plain")},
        headers=headers,
    )
    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("x.txt", io.BytesIO(b"a"), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["job_id"] != r2.json()["job_id"]


# ---------------------------------------------------------------------------
# 6. Invalid keys -> 400 before mutation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "short",  # too short
        "a" * 15,
        "a" * 129,  # too long
        "has spaces in key!!",  # whitespace / invalid charset
        "bad key with space16",
        "invalid@charset!!!!",  # @ not in allowed set
        "semi;colon-not-allowed",
    ],
)
def test_invalid_idempotency_key_rejected_before_mutation(
    bad_key: str,
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("bad.txt", io.BytesIO(b"payload"), "text/plain")},
            headers=_api_key(**{"Idempotency-Key": bad_key}),
        )

    assert resp.status_code == 400
    detail = str(resp.json().get("detail", ""))
    assert detail == "Invalid Idempotency-Key"
    assert bad_key not in detail
    assert bad_key not in caplog.text
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 0
    assert not (tmp_path / "data" / "uploads" / "bad.txt").exists()
    assert captured.get("calls", 0) == 0


# ---------------------------------------------------------------------------
# 7. DB stores hash/fingerprint; public surfaces never leak raw key/internal
# ---------------------------------------------------------------------------


def test_db_stores_hash_not_raw_key_and_public_surfaces_clean(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _silence_audit(monkeypatch)
    _patch_apply_async(monkeypatch)

    raw_key = "secret-idem-key-01"
    content = b"hash-store-check"
    with caplog.at_level(logging.DEBUG):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("h.txt", io.BytesIO(content), "text/plain")},
            headers=_api_key(**{"Idempotency-Key": raw_key}),
        )
    assert resp.status_code == 200
    body = resp.json()
    job_id = body["job_id"]

    for field in _INTERNAL_FIELDS:
        assert field not in body
    assert raw_key not in str(body)
    assert raw_key not in caplog.text

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert job.idempotency_key_hash == _expected_key_hash(raw_key)
    assert job.payload_fingerprint == _expected_fingerprint("h.txt", content)
    assert raw_key not in (job.idempotency_key_hash or "")
    assert job.source_ready_at is not None

    poll = client_with_key.get(f"/api/jobs/{job_id}", headers=_api_key())
    assert poll.status_code == 200
    poll_body = poll.json()
    for field in _INTERNAL_FIELDS:
        assert field not in poll_body
    assert raw_key not in str(poll_body)


# ---------------------------------------------------------------------------
# 8. Concurrent create race
# ---------------------------------------------------------------------------


def test_concurrent_create_race_one_row_same_fingerprint_reuses(
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod
    from ingestion.jobs import IdempotencyConflictError

    tenant = "race-tenant"
    key_hash = _expected_key_hash(_VALID_KEY)
    fp = _expected_fingerprint("race.txt", b"race-bytes")
    source = "data/uploads/race.txt"

    async def _create_once(job_id: uuid.UUID | None = None):
        return await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id=tenant,
            filename="race.txt",
            source_path=source,
            job_id=job_id or uuid.uuid4(),
            celery_task_id=None,
            idempotency_key_hash=key_hash,
            payload_fingerprint=fp,
        )

    async def _race() -> list[Any]:
        return await asyncio.gather(_create_once(), _create_once())

    outcomes = asyncio.run(_race())
    created = [o for o in outcomes if o.created]
    replayed = [o for o in outcomes if not o.created]
    assert len(created) == 1
    assert len(replayed) == 1
    assert created[0].job.id == replayed[0].job.id
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1

    # Different fingerprint conflicts; no second row.
    async def _conflict() -> None:
        with pytest.raises(IdempotencyConflictError):
            await jobs_mod.create_or_reuse_ingestion_job(
                tenant_id=tenant,
                filename="race.txt",
                source_path=source,
                job_id=uuid.uuid4(),
                celery_task_id=None,
                idempotency_key_hash=key_hash,
                payload_fingerprint=_expected_fingerprint("race.txt", b"other"),
            )

    asyncio.run(_conflict())
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1


def test_only_creator_outcome_allows_write_semantics(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Replay path must not rewrite canonical file; creator wrote once."""
    _silence_audit(monkeypatch)
    _patch_apply_async(monkeypatch)

    content = b"creator-only-write"
    headers = _api_key(**{"Idempotency-Key": _VALID_KEY_B})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("c.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    path = tmp_path / "data" / "uploads" / "c.txt"
    mtime = path.stat().st_mtime_ns
    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("c.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["idempotency_replayed"] is True
    assert path.stat().st_mtime_ns == mtime


# ---------------------------------------------------------------------------
# 9. Deterministic task id reserved before apply_async
# ---------------------------------------------------------------------------


def test_deterministic_task_id_reserved_before_apply_async(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    _silence_audit(monkeypatch)
    order: list[str] = []

    original_create = None

    import ingestion.jobs as jobs_mod

    async def _wrapped_create(**kwargs: Any):
        outcome = await original_create(**kwargs)
        order.append("db_create")
        if outcome.job.celery_task_id:
            order.append(f"task:{outcome.job.celery_task_id}")
        return outcome

    original_create = jobs_mod.create_or_reuse_ingestion_job
    monkeypatch.setattr(jobs_mod, "create_or_reuse_ingestion_job", _wrapped_create)

    def _apply_async(*args: Any, **kwargs: Any) -> SimpleNamespace:
        order.append("apply_async")
        order.append(f"publish:{kwargs.get('task_id')}")
        return SimpleNamespace(id=kwargs["task_id"])

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(
        apply_async=_apply_async,
        autoretry_for=(),
    )
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("ord.txt", io.BytesIO(b"ord"), "text/plain")},
        headers=_api_key(),
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    task_id = resp.json()["task_id"]
    assert task_id == f"ingest-{job_id}"
    assert "db_create" in order
    assert f"task:{task_id}" in order
    assert order.index("db_create") < order.index("apply_async")
    assert order.index(f"task:{task_id}") < order.index("apply_async")

    # Resolvable via jobs and tasks routes.
    by_job = client_with_key.get(f"/api/jobs/{job_id}", headers=_api_key())
    by_task = client_with_key.get(f"/api/tasks/{task_id}", headers=_api_key())
    assert by_job.status_code == 200
    assert by_task.status_code == 200
    assert by_job.json()["job_id"] == job_id
    assert by_task.json()["job_id"] == job_id
    assert by_task.json()["task_id"] == task_id


# ---------------------------------------------------------------------------
# 10. Bounded publish retry policy from settings; no worker autoretry
# ---------------------------------------------------------------------------


def test_apply_async_receives_bounded_retry_policy_from_settings(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    settings = api_app.get_settings()
    monkeypatch.setattr(settings, "ingestion_publish_max_retries", 3, raising=False)
    monkeypatch.setattr(settings, "ingestion_publish_retry_delay_sec", 0.5, raising=False)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("pol.txt", io.BytesIO(b"p"), "text/plain")},
        headers=_api_key(),
    )
    assert resp.status_code == 200
    assert captured.get("retry") is True
    policy = captured.get("retry_policy") or {}
    assert policy.get("max_retries") == 3
    assert policy.get("interval_start") == 0.5
    # No unbounded / missing max.
    assert policy.get("max_retries") is not None
    assert int(policy["max_retries"]) >= 0

    # Task surface must not enable worker-phase autoretry.
    import tasks.ingest_task as real_task_mod

    task = real_task_mod.ingest_document
    assert not getattr(task, "autoretry_for", None)
    assert "autoretry_for" not in (
        inspect.signature(task.run).parameters if hasattr(task, "run") else {}
    )


def test_publish_settings_validate_non_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    import config.settings as settings_module

    monkeypatch.setenv("INGESTION_PUBLISH_MAX_RETRIES", "2")
    monkeypatch.setenv("INGESTION_PUBLISH_RETRY_DELAY_SEC", "0.2")
    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    s = settings_module.get_settings()
    assert s.ingestion_publish_max_retries == 2
    assert s.ingestion_publish_retry_delay_sec == 0.2
    s.validate()

    monkeypatch.setenv("INGESTION_PUBLISH_MAX_RETRIES", "-1")
    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    with pytest.raises(RuntimeError) as ei:
        settings_module.get_settings().validate()
    assert "INGESTION_PUBLISH_MAX_RETRIES" in str(ei.value)

    monkeypatch.setenv("INGESTION_PUBLISH_MAX_RETRIES", "0")
    monkeypatch.setenv("INGESTION_PUBLISH_RETRY_DELAY_SEC", "nan")
    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    with pytest.raises(RuntimeError) as ei2:
        settings_module.get_settings().validate()
    assert "INGESTION_PUBLISH_RETRY_DELAY_SEC" in str(ei2.value)


def test_docs_and_env_example_document_publish_settings() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    config_md = (PROJECT_ROOT / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    assert "INGESTION_PUBLISH_MAX_RETRIES" in env_example
    assert "INGESTION_PUBLISH_RETRY_DELAY_SEC" in env_example
    assert "INGESTION_PUBLISH_MAX_RETRIES" in config_md
    assert "INGESTION_PUBLISH_RETRY_DELAY_SEC" in config_md


# ---------------------------------------------------------------------------
# 11. Publish failure -> 503 + header; same-key retry republishes
# ---------------------------------------------------------------------------


def test_publish_failure_returns_503_with_job_header_and_replay_republishes(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _silence_audit(monkeypatch)
    fail = RuntimeError("broker down")
    _patch_apply_async(monkeypatch, side_effect=fail)

    raw_key = "publish-fail-key-01"
    content = b"publish-fail-body"
    headers = _api_key(**{"Idempotency-Key": raw_key})

    with caplog.at_level(logging.INFO):
        r1 = client_with_key.post(
            "/api/upload",
            files={"file": ("pf.txt", io.BytesIO(content), "text/plain")},
            headers=headers,
        )

    assert r1.status_code == 503
    job_id = r1.headers.get("X-Ingestion-Job-Id")
    assert job_id
    uuid.UUID(job_id)
    detail = str(r1.json().get("detail", ""))
    assert "broker down" not in detail.lower()
    assert raw_key not in detail
    assert raw_key not in caplog.text
    # Logs may include phase + exception type only.
    assert "RuntimeError" in caplog.text or "publish" in caplog.text.lower()

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert job.status == "queued"
    assert job.source_ready_at is not None
    assert job.celery_task_id == f"ingest-{job_id}"
    assert (tmp_path / "data" / "uploads" / "pf.txt").read_bytes() == content

    # Clear side effect: same-key retry republishes same identity.
    captured2 = _patch_apply_async(monkeypatch)
    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("pf.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["job_id"] == job_id
    assert body2["task_id"] == f"ingest-{job_id}"
    assert body2.get("idempotency_replayed") is True
    assert body2["status"] == "accepted"
    assert captured2.get("calls", 0) == 1
    assert captured2.get("task_id") == f"ingest-{job_id}"
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1


# ---------------------------------------------------------------------------
# 12. Replay before source_ready_at does not publish
# ---------------------------------------------------------------------------


def test_replay_before_source_ready_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    key_hash = _expected_key_hash("early-replay-key01")
    fp = _expected_fingerprint("early.txt", b"early")
    job_id = uuid.uuid4()
    reserved = f"ingest-{job_id}"

    async def _seed() -> None:
        outcome = await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id="default",
            filename="early.txt",
            source_path="data/uploads/early.txt",
            job_id=job_id,
            celery_task_id=reserved,
            idempotency_key_hash=key_hash,
            payload_fingerprint=fp,
        )
        assert outcome.created
        assert outcome.job.source_ready_at is None

    asyncio.run(_seed())

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("early.txt", io.BytesIO(b"early"), "text/plain")},
        headers=_api_key(**{"Idempotency-Key": "early-replay-key01"}),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["task_id"] == reserved
    assert body.get("idempotency_replayed") is True
    assert body["status"] == "accepted"
    assert captured.get("calls", 0) == 0


# ---------------------------------------------------------------------------
# 14. Write failure terminal-fails row and never publishes
# ---------------------------------------------------------------------------


def test_write_failure_marks_job_failed_and_never_publishes(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    def _boom_write(path: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(upload_mod, "_write_bytes_exclusive", _boom_write)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("wf.txt", io.BytesIO(b"will-fail"), "text/plain")},
        headers=_api_key(**{"Idempotency-Key": "write-fail-key-001"}),
    )
    assert resp.status_code == 500
    detail = str(resp.json().get("detail", ""))
    assert "disk full" not in detail.lower()
    assert captured.get("calls", 0) == 0
    # Failed immutable create must not refresh the flat current corpus view.
    assert not (tmp_path / "data" / "uploads" / "wf.txt").exists()

    # Created row must be terminal failed.
    async def _all() -> list[IngestionJob]:
        async with ingestion_jobs_db["async_session"]() as session:
            result = await session.execute(select(IngestionJob))
            return list(result.scalars().all())

    rows = asyncio.run(_all())
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].finished_at is not None
    assert rows[0].source_ready_at is None


# ---------------------------------------------------------------------------
# 13. Race-safe source_ready transition (queued-only CAS)
# ---------------------------------------------------------------------------


def test_mark_source_ready_rejects_terminal_statuses(
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    """Terminal failed/completed rows must not become source-ready."""
    from ingestion import jobs as jobs_mod

    async def _run() -> None:
        failed = await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id="default",
            filename="term-fail.txt",
            source_path="data/uploads/term-fail.txt",
            job_id=uuid.uuid4(),
            celery_task_id=None,
        )
        assert failed.created
        await jobs_mod.mark_job_failed(failed.job.id, "default", "reaped")
        assert await jobs_mod.mark_source_ready(failed.job.id, "default") is None

        completed = await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id="default",
            filename="term-ok.txt",
            source_path="data/uploads/term-ok.txt",
            job_id=uuid.uuid4(),
            celery_task_id=None,
        )
        assert completed.created
        await jobs_mod.mark_job_completed(completed.job.id, "default", {"ok": True})
        assert await jobs_mod.mark_source_ready(completed.job.id, "default") is None

        # Confirm terminal rows stayed terminal and never ready.
        f_row = await _fetch_job(ingestion_jobs_db["async_session"], failed.job.id)
        c_row = await _fetch_job(ingestion_jobs_db["async_session"], completed.job.id)
        assert f_row is not None and f_row.status == "failed"
        assert f_row.source_ready_at is None
        assert c_row is not None and c_row.status == "completed"
        assert c_row.source_ready_at is None

    asyncio.run(_run())


def test_mark_source_ready_idempotent_for_already_ready_queued(
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    """Re-calling helper on queued+ready is an idempotent success."""
    from ingestion import jobs as jobs_mod

    async def _run() -> None:
        outcome = await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id="default",
            filename="ready-twice.txt",
            source_path="data/uploads/ready-twice.txt",
            job_id=uuid.uuid4(),
            celery_task_id="ingest-ready-twice",
        )
        first = await jobs_mod.mark_source_ready(outcome.job.id, "default")
        assert first is not None
        assert first.status == "queued"
        assert first.source_ready_at is not None
        ready_at = first.source_ready_at

        second = await jobs_mod.mark_source_ready(outcome.job.id, "default")
        assert second is not None
        assert second.status == "queued"
        assert second.source_ready_at == ready_at

    asyncio.run(_run())


def test_terminal_win_before_source_ready_fails_closed_no_publish(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """If reaper/terminal wins while write is in flight, fail closed — no publish."""
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)
    original_exclusive = upload_mod._write_bytes_exclusive

    def _write_then_reap(path: Path, data: bytes) -> None:
        original_exclusive(path, data)

        async def _terminal() -> None:
            from ingestion.jobs import mark_job_failed

            async with ingestion_jobs_db["async_session"]() as session:
                result = await session.execute(select(IngestionJob))
                rows = list(result.scalars().all())
            for row in rows:
                if row.status == "queued":
                    await mark_job_failed(row.id, row.tenant_id, "stale reaped")

        asyncio.run(_terminal())

    monkeypatch.setattr(upload_mod, "_write_bytes_exclusive", _write_then_reap)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("race.txt", io.BytesIO(b"race-body"), "text/plain")},
        headers=_api_key(**{"Idempotency-Key": "source-ready-race-01"}),
    )
    # Durable transition error — never 200/accepted, never broker publish.
    assert resp.status_code == 500
    detail = str(resp.json().get("detail", ""))
    assert "Failed to update ingestion job state" in detail
    assert captured.get("calls", 0) == 0

    async def _all() -> list[IngestionJob]:
        async with ingestion_jobs_db["async_session"]() as session:
            result = await session.execute(select(IngestionJob))
            return list(result.scalars().all())

    rows = asyncio.run(_all())
    assert len(rows) == 1
    assert rows[0].status == "failed"
    # Terminal won: helper must not stamp source_ready on a failed row.
    assert rows[0].source_ready_at is None


# ---------------------------------------------------------------------------
# 17. Broker publish must not block the async event-loop thread
# ---------------------------------------------------------------------------


def test_publish_apply_async_runs_off_request_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    """Synchronous Celery apply_async must not run on the request/event-loop thread."""
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)
    captured: dict[str, Any] = {}

    def _apply_async(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured["apply_thread"] = threading.get_ident()
        captured["calls"] = captured.get("calls", 0) + 1
        captured["task_id"] = kwargs.get("task_id")
        captured["retry"] = kwargs.get("retry")
        captured["retry_policy"] = kwargs.get("retry_policy")
        return SimpleNamespace(id=kwargs.get("task_id") or "generated-task")

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(
        apply_async=_apply_async,
        autoretry_for=(),
        max_retries=0,
        name="tasks.ingest_document",
    )
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)

    original_mark = upload_mod._mark_source_ready_or_fail

    async def _track_loop_thread(job_id: uuid.UUID, tenant_id: str) -> None:
        captured["loop_thread"] = threading.get_ident()
        await original_mark(job_id, tenant_id)

    monkeypatch.setattr(upload_mod, "_mark_source_ready_or_fail", _track_loop_thread)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("offload.txt", io.BytesIO(b"offload-body"), "text/plain")},
        headers=_api_key(),
    )
    assert resp.status_code == 200
    assert captured.get("calls", 0) == 1
    assert "loop_thread" in captured
    assert "apply_thread" in captured
    assert captured["apply_thread"] != captured["loop_thread"], (
        "apply_async ran on the request/event-loop thread; must be offloaded"
    )
    # Preserve deterministic task id + bounded retry policy through offload.
    job_id = resp.json()["job_id"]
    assert captured.get("task_id") == f"ingest-{job_id}"
    assert captured.get("retry") is True
    policy = captured.get("retry_policy") or {}
    assert policy.get("max_retries") is not None
    assert int(policy["max_retries"]) >= 0


def test_replay_publish_also_runs_off_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Replay republish path must also offload apply_async off the event loop."""
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)

    # First create succeeds with offloaded publish (production will offload;
    # this red phase only asserts the second/replay path once source-ready).
    _patch_apply_async(monkeypatch)
    content = b"replay-offload-body"
    headers = _api_key(**{"Idempotency-Key": "replay-offload-key1"})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("ro.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    job_id = r1.json()["job_id"]

    captured: dict[str, Any] = {}

    def _apply_async(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured["apply_thread"] = threading.get_ident()
        captured["calls"] = captured.get("calls", 0) + 1
        captured["task_id"] = kwargs.get("task_id")
        return SimpleNamespace(id=kwargs.get("task_id") or "generated-task")

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(
        apply_async=_apply_async,
        autoretry_for=(),
        max_retries=0,
    )
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)

    # Capture the request/event-loop thread via the replay response builder path.
    original_from_job = upload_mod._upload_response_from_job

    def _track_loop(*args: Any, **kwargs: Any):
        captured["loop_thread"] = threading.get_ident()
        return original_from_job(*args, **kwargs)

    monkeypatch.setattr(upload_mod, "_upload_response_from_job", _track_loop)

    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("ro.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["idempotency_replayed"] is True
    assert r2.json()["job_id"] == job_id
    assert captured.get("calls", 0) == 1
    assert "loop_thread" in captured
    assert "apply_thread" in captured
    assert captured["apply_thread"] != captured["loop_thread"]
    assert captured.get("task_id") == f"ingest-{job_id}"


# ---------------------------------------------------------------------------
# 16. CORS: allow Idempotency-Key request header; expose job id on 503
# ---------------------------------------------------------------------------


def test_cors_allows_idempotency_key_header(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from starlette.middleware.cors import CORSMiddleware

    import api.app as app_module

    app_module = importlib.reload(app_module)
    cors_middleware = None
    for middleware in app_module.app.user_middleware:
        if middleware.cls is CORSMiddleware:
            cors_middleware = middleware
            break
    assert cors_middleware is not None
    kwargs = getattr(cors_middleware, "kwargs", None) or getattr(cors_middleware, "options", {})
    allow_headers = kwargs.get("allow_headers") or []
    normalized = {h.lower() for h in allow_headers}
    assert "idempotency-key" in normalized


def test_cors_exposes_ingestion_job_id_not_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser JS must read X-Ingestion-Job-Id on 503; never expose raw key."""
    import importlib

    from starlette.middleware.cors import CORSMiddleware

    import api.app as app_module

    app_module = importlib.reload(app_module)
    cors_middleware = None
    for middleware in app_module.app.user_middleware:
        if middleware.cls is CORSMiddleware:
            cors_middleware = middleware
            break
    assert cors_middleware is not None
    kwargs = getattr(cors_middleware, "kwargs", None) or getattr(cors_middleware, "options", {})
    expose_headers = kwargs.get("expose_headers") or []
    exposed = {h.lower() for h in expose_headers}
    assert "x-ingestion-job-id" in exposed
    # Request-only secret identity must not be browser-readable as a response header.
    assert "idempotency-key" not in exposed


# ---------------------------------------------------------------------------
# Helpers / create_ingestion_job compatibility
# ---------------------------------------------------------------------------


def test_create_ingestion_job_compatibility_preserved(
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from ingestion.jobs import create_ingestion_job

    async def _run() -> IngestionJob:
        return await create_ingestion_job(
            tenant_id="compat",
            filename="c.txt",
            source_path="data/uploads/c.txt",
        )

    job = asyncio.run(_run())
    assert job.id is not None
    assert job.status == "queued"
    assert job.celery_task_id is None
    assert job.idempotency_key_hash is None


# ---------------------------------------------------------------------------
# 2.4a: job-scoped immutable originals + flat current corpus view
# ---------------------------------------------------------------------------


def _immutable_object_path(tmp_path: Path, job_id: str, safe_name: str) -> Path:
    """Expected on-disk layout under the tenant upload root (default tenant)."""
    return tmp_path / "data" / "uploads" / "job-objects" / job_id / safe_name


def test_sequential_same_filename_keeps_distinct_immutable_objects(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Two no-key uploads with the same safe_name must not share mutable bytes."""
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    first_bytes = b"original-payload-v1"
    second_bytes = b"replacement-payload-v2"
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("shared.txt", io.BytesIO(first_bytes), "text/plain")},
        headers=_api_key(),
    )
    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("shared.txt", io.BytesIO(second_bytes), "text/plain")},
        headers=_api_key(),
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    job_id_1 = r1.json()["job_id"]
    job_id_2 = r2.json()["job_id"]
    assert job_id_1 != job_id_2
    assert captured.get("calls", 0) == 2

    job1 = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id_1))
    job2 = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id_2))
    assert job1 is not None and job2 is not None
    assert job1.source_path != job2.source_path
    assert job_id_1 in job1.source_path
    assert job_id_2 in job2.source_path
    assert job1.source_path.endswith("shared.txt")
    assert job2.source_path.endswith("shared.txt")
    assert not Path(job1.source_path).is_absolute()
    assert not Path(job2.source_path).is_absolute()
    # Flat current corpus view stays the canonical safe_name (not job-scoped).
    assert job1.source_path != "data/uploads/shared.txt"
    assert job2.source_path != "data/uploads/shared.txt"

    imm1 = _immutable_object_path(tmp_path, job_id_1, "shared.txt")
    imm2 = _immutable_object_path(tmp_path, job_id_2, "shared.txt")
    assert imm1.is_file()
    assert imm2.is_file()
    assert imm1.read_bytes() == first_bytes
    assert imm2.read_bytes() == second_bytes
    # First immutable object must remain byte-for-byte unchanged after second upload.
    assert imm1.read_bytes() == first_bytes

    current = tmp_path / "data" / "uploads" / "shared.txt"
    assert current.is_file()
    assert current.read_bytes() == second_bytes

    # Publish still targets the flat current view for recursive=False loaders.
    published_path = Path(captured["args"][0])
    assert published_path.name == "shared.txt"
    assert published_path.parent == (tmp_path / "data" / "uploads")


def test_idempotent_replay_preserves_immutable_source_and_skips_rewrites(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Same-key/same-payload replay must not rewrite immutable object or flat view."""
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    content = b"immutable-replay-payload"
    headers = _api_key(**{"Idempotency-Key": "imm-replay-key-001"})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("imm.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    job_id = r1.json()["job_id"]
    assert r1.json().get("idempotency_replayed") is False

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    source_path = job.source_path
    assert job_id in source_path
    assert source_path.endswith("imm.txt")
    assert source_path != "data/uploads/imm.txt"

    imm = _immutable_object_path(tmp_path, job_id, "imm.txt")
    current = tmp_path / "data" / "uploads" / "imm.txt"
    assert imm.read_bytes() == content
    assert current.read_bytes() == content
    imm_mtime = imm.stat().st_mtime_ns
    current_mtime = current.stat().st_mtime_ns

    # Terminal completed: replay must not re-publish or rewrite files.
    async def _complete() -> None:
        from ingestion.jobs import mark_job_completed

        await mark_job_completed(uuid.UUID(job_id), "default", {"status": "ok"})

    asyncio.run(_complete())

    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("imm.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["job_id"] == job_id
    assert body2.get("idempotency_replayed") is True
    assert body2["status"] == "ok"
    assert captured.get("calls", 0) == 1

    job_after = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job_after is not None
    assert job_after.source_path == source_path
    assert imm.read_bytes() == content
    assert current.read_bytes() == content
    assert imm.stat().st_mtime_ns == imm_mtime
    assert current.stat().st_mtime_ns == current_mtime
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1


def test_same_key_conflict_before_any_file_mutation(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Fingerprint conflict must 409 without rewriting immutable or flat files."""
    _silence_audit(monkeypatch)
    _patch_apply_async(monkeypatch)

    original = b"conflict-original-bytes"
    headers = _api_key(**{"Idempotency-Key": "imm-conflict-key01"})
    r1 = client_with_key.post(
        "/api/upload",
        files={"file": ("cf.txt", io.BytesIO(original), "text/plain")},
        headers=headers,
    )
    assert r1.status_code == 200
    job_id = r1.json()["job_id"]
    imm = _immutable_object_path(tmp_path, job_id, "cf.txt")
    current = tmp_path / "data" / "uploads" / "cf.txt"
    imm_mtime = imm.stat().st_mtime_ns
    current_mtime = current.stat().st_mtime_ns

    r2 = client_with_key.post(
        "/api/upload",
        files={"file": ("cf.txt", io.BytesIO(b"different-conflict-bytes"), "text/plain")},
        headers=headers,
    )
    assert r2.status_code == 409
    detail = str(r2.json().get("detail", ""))
    assert "conflict" in detail.lower() or "idempotency" in detail.lower()

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert imm.read_bytes() == original
    assert current.read_bytes() == original
    assert imm.stat().st_mtime_ns == imm_mtime
    assert current.stat().st_mtime_ns == current_mtime
    assert asyncio.run(_count_jobs(ingestion_jobs_db["async_session"])) == 1


def test_immutable_write_failure_marks_failed_without_flat_refresh(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Failed immutable create must not refresh flat current view or publish."""
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    def _boom_exclusive(path: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(upload_mod, "_write_bytes_exclusive", _boom_exclusive)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("imm-fail.txt", io.BytesIO(b"will-fail"), "text/plain")},
        headers=_api_key(**{"Idempotency-Key": "imm-write-fail-key1"}),
    )
    assert resp.status_code == 500
    detail = str(resp.json().get("detail", ""))
    assert "disk full" not in detail.lower()
    assert captured.get("calls", 0) == 0

    # Flat current corpus view must remain absent / unrefreshed.
    assert not (tmp_path / "data" / "uploads" / "imm-fail.txt").exists()

    async def _all() -> list[IngestionJob]:
        async with ingestion_jobs_db["async_session"]() as session:
            result = await session.execute(select(IngestionJob))
            return list(result.scalars().all())

    rows = asyncio.run(_all())
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].finished_at is not None
    assert rows[0].source_ready_at is None
    # Job points at the intended immutable path, but the object was not written.
    assert str(rows[0].id) in rows[0].source_path
    assert not _immutable_object_path(tmp_path, str(rows[0].id), "imm-fail.txt").exists()


# ---------------------------------------------------------------------------
# 2.4a QA: legacy flat previous-original preservation on first post-2.4a upload
# ---------------------------------------------------------------------------


def _legacy_previous_recovery_path(
    tmp_path: Path, prior_bytes: bytes, safe_name: str
) -> Path:
    """Content-addressed recovery object nested under tenant job-objects."""
    digest = hashlib.sha256(prior_bytes).hexdigest()
    return (
        tmp_path
        / "data"
        / "uploads"
        / "job-objects"
        / "legacy-previous"
        / digest
        / safe_name
    )


def test_legacy_flat_prior_bytes_preserved_on_first_post_24a_upload(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """Pre-2.4a flat corpus must remain recoverable after first post-2.4a replace."""
    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    safe_name = "legacy.txt"
    legacy_bytes = b"pre-24a-legacy-original-bytes"
    new_bytes = b"post-24a-replacement-payload"
    upload_dir = tmp_path / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    current = upload_dir / safe_name
    # Seed a legacy flat-only original (no job-objects copy exists).
    current.write_bytes(legacy_bytes)
    assert current.is_file()
    assert not (upload_dir / "job-objects").exists()

    resp = client_with_key.post(
        "/api/upload",
        files={"file": (safe_name, io.BytesIO(new_bytes), "text/plain")},
        headers=_api_key(),
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert captured.get("calls", 0) == 1

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    # New job owns the new immutable original, not the flat path.
    assert str(job_id) in job.source_path
    assert job.source_path.endswith(safe_name)
    assert job.source_path != f"data/uploads/{safe_name}"

    imm = _immutable_object_path(tmp_path, job_id, safe_name)
    assert imm.is_file()
    assert imm.read_bytes() == new_bytes
    assert current.is_file()
    assert current.read_bytes() == new_bytes

    recovery = _legacy_previous_recovery_path(tmp_path, legacy_bytes, safe_name)
    assert recovery.is_file()
    assert recovery.read_bytes() == legacy_bytes
    # Tenant-contained: recovery must stay under the tenant upload root.
    tenant_root = upload_dir.resolve()
    assert recovery.resolve().is_relative_to(tenant_root)
    # Nested under job-objects so recursive=False corpus loaders never scan it.
    assert "job-objects" in recovery.parts
    assert recovery.parent != upload_dir
    flat_only = [p for p in upload_dir.iterdir() if p.is_file()]
    assert flat_only == [current]
    assert recovery not in flat_only

    # Default worker still receives the flat current-view path.
    published_path = Path(captured["args"][0])
    assert published_path == current
    assert published_path.read_bytes() == new_bytes


def test_legacy_preserve_failure_leaves_flat_unchanged_and_fails_job(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    """If prior-legacy preservation fails, do not replace flat or publish."""
    import api.routers.upload as upload_mod

    _silence_audit(monkeypatch)
    captured = _patch_apply_async(monkeypatch)

    safe_name = "legacy-fail.txt"
    legacy_bytes = b"must-remain-flat-if-preserve-fails"
    new_bytes = b"must-not-publish-or-replace"
    upload_dir = tmp_path / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    current = upload_dir / safe_name
    current.write_bytes(legacy_bytes)
    legacy_mtime = current.stat().st_mtime_ns

    def _boom_preserve(*args: Any, **kwargs: Any) -> None:
        raise OSError("preserve disk full")

    monkeypatch.setattr(upload_mod, "_preserve_prior_flat_bytes", _boom_preserve)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": (safe_name, io.BytesIO(new_bytes), "text/plain")},
        headers=_api_key(**{"Idempotency-Key": "legacy-preserve-fail01"}),
    )
    assert resp.status_code == 500
    detail = str(resp.json().get("detail", ""))
    assert "preserve disk full" not in detail.lower()
    assert captured.get("calls", 0) == 0

    # Flat current view must remain the legacy original.
    assert current.is_file()
    assert current.read_bytes() == legacy_bytes
    assert current.stat().st_mtime_ns == legacy_mtime
    # No recovery object and no flat replace of new bytes.
    assert not _legacy_previous_recovery_path(tmp_path, legacy_bytes, safe_name).exists()

    async def _all() -> list[IngestionJob]:
        async with ingestion_jobs_db["async_session"]() as session:
            result = await session.execute(select(IngestionJob))
            return list(result.scalars().all())

    rows = asyncio.run(_all())
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].finished_at is not None
    assert rows[0].source_ready_at is None

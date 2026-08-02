"""ING-01 / plan step 4.1: durable tenant-aware ingestion job contract.

Covers ORM + migration 019, upload job identity, poll routes, and worker
bridge. Does not claim worker topology, reaper, retry/idempotency, or
atomic collection publish (ING-02).
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import logging
import sys
import types
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from auth.jwt_handler import create_access_token
from db.models import IngestionJob

# Markers used to prove boundary logs/responses never serialize raw secrets/PII/paths.
_SECRET_BLOB = (
    "boom for support@example.com with MISTRAL_API_KEY=sk-secret-value "
    "and postgresql://user:db-password@host/db path=D:\\host\\secret\\path.txt"
)
_SECRET_MARKERS = (
    "support@example.com",
    "sk-secret-value",
    "db-password",
    r"D:\host\secret\path.txt",
)


def _assert_no_secret_leak(text: str) -> None:
    for marker in _SECRET_MARKERS:
        assert marker not in text, f"secret/path leaked in logs/response: {marker!r}"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = PROJECT_ROOT / "alembic" / "versions" / "019_ingestion_jobs.py"

CLIENT_WITH_KEY_SETTINGS_OVERRIDES = {
    "project_root": "__tmp_path__",
}
CLIENT_WITH_KEY_PATCHES = {
    "PROJECT_ROOT": "__tmp_path__",
}


def _load_migration() -> ModuleType:
    assert MIGRATION_PATH.is_file(), f"missing migration: {MIGRATION_PATH}"
    spec = importlib.util.spec_from_file_location(
        "migration_019_ingestion_jobs",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _headers(tenant: str, role: str = "admin") -> dict[str, str]:
    token = create_access_token(f"user-{tenant}", role, tenant)
    return {"Authorization": f"Bearer {token}"}


async def _fetch_job(session_factory, job_id: str):
    from sqlalchemy import select

    async with session_factory() as session:
        result = await session.execute(
            select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id))
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# 1. ORM metadata + migration 019
# ---------------------------------------------------------------------------


def test_ingestion_job_orm_metadata_contract() -> None:
    table = IngestionJob.__table__
    cols = table.c

    assert cols.id.primary_key is True
    assert isinstance(cols.id.type, PG_UUID)
    assert cols.id.nullable is False
    # Application-generated UUID: no server default that requires an extension.
    assert cols.id.server_default is None

    assert cols.tenant_id.nullable is False
    assert cols.tenant_id.server_default is None

    assert cols.filename.nullable is False
    assert cols.source_path.nullable is False

    assert cols.status.nullable is False
    status_default = cols.status.default.arg if cols.status.default is not None else None
    server_status = (
        str(cols.status.server_default.arg)
        if cols.status.server_default is not None
        else None
    )
    assert status_default == "queued" or (server_status is not None and "queued" in server_status)

    assert cols.error.nullable is True
    assert cols.result.nullable is True
    assert cols.celery_task_id.nullable is True
    assert cols.created_at.nullable is False
    assert cols.started_at.nullable is True
    assert cols.finished_at.nullable is True

    check_constraints = [
        c for c in table.constraints if isinstance(c, CheckConstraint)
    ]
    assert check_constraints, "status must be constrained via CheckConstraint"
    check_sql = " ".join(str(c.sqltext) for c in check_constraints).lower()
    for status in ("queued", "running", "completed", "failed"):
        assert status in check_sql
    for banned in ("pending", "success", "error", "partial"):
        assert banned not in check_sql

    index_cols = {
        tuple(idx.columns.keys()): idx.name
        for idx in table.indexes
    }
    assert any(set(cols) >= {"tenant_id", "created_at"} for cols in index_cols), (
        f"missing tenant+created_at index, got {index_cols}"
    )
    assert any("status" in cols for cols in index_cols), index_cols
    assert any("celery_task_id" in cols for cols in index_cols), index_cols


def test_migration_019_revision_chain_and_schema() -> None:
    module = _load_migration()
    assert module.revision == "019"
    assert module.down_revision == "018"

    upgrade_src = inspect.getsource(module.upgrade)
    downgrade_src = inspect.getsource(module.downgrade)

    assert "ingestion_jobs" in upgrade_src
    assert "create_table" in upgrade_src
    assert "drop_table" in downgrade_src
    assert "gen_random_uuid" not in upgrade_src
    assert "uuid_generate" not in upgrade_src
    assert "create_extension" not in upgrade_src

    for status in ("queued", "running", "completed", "failed"):
        assert status in upgrade_src
    assert "tenant_id" in upgrade_src
    assert "source_path" in upgrade_src
    assert "celery_task_id" in upgrade_src
    assert "CheckConstraint" in upgrade_src or "checkconstraint" in upgrade_src.lower() or "ck_ingestion" in upgrade_src

    # Dependency-safe downgrade: drop indexes then table (or drop table only).
    assert "ingestion_jobs" in downgrade_src

    calls: list[tuple[Any, ...]] = []

    class _FakeOp:
        def create_table(self, table_name: str, *columns: Any, **kwargs: Any) -> None:
            col_names = []
            for col in columns:
                name = getattr(col, "name", None)
                if name is not None:
                    col_names.append(name)
            calls.append(("create_table", table_name, col_names, kwargs))

        def create_index(
            self, index_name: str, table_name: str, columns: list[str], **kwargs: Any
        ) -> None:
            calls.append(("create_index", index_name, table_name, list(columns)))

        def drop_index(self, index_name: str, table_name: str | None = None, **kwargs: Any) -> None:
            calls.append(("drop_index", index_name, table_name))

        def drop_table(self, table_name: str, **kwargs: Any) -> None:
            calls.append(("drop_table", table_name))

    original_op = module.op
    module.op = _FakeOp()  # type: ignore[assignment]
    try:
        module.upgrade()
        upgrade_calls = list(calls)
        calls.clear()
        module.downgrade()
        downgrade_calls = list(calls)
    finally:
        module.op = original_op

    assert upgrade_calls[0][0] == "create_table"
    assert upgrade_calls[0][1] == "ingestion_jobs"
    created_cols = set(upgrade_calls[0][2])
    for required in (
        "id",
        "tenant_id",
        "filename",
        "source_path",
        "status",
        "error",
        "result",
        "celery_task_id",
        "created_at",
        "started_at",
        "finished_at",
    ):
        assert required in created_cols

    index_calls = [c for c in upgrade_calls if c[0] == "create_index"]
    index_col_sets = [set(c[3]) for c in index_calls]
    assert any({"tenant_id", "created_at"} <= s for s in index_col_sets)
    assert any("status" in s for s in index_col_sets)
    assert any("celery_task_id" in s for s in index_col_sets)

    assert any(c[0] == "drop_table" and c[1] == "ingestion_jobs" for c in downgrade_calls)


# ---------------------------------------------------------------------------
# 2–4. Upload contract (async default + sync fallback + failure states)
# ---------------------------------------------------------------------------


def test_default_tenant_upload_creates_queued_job_and_enqueues_identity(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    captured: dict[str, Any] = {}

    def _delay(file_path: str, job_id: str, tenant_id: str):
        captured["args"] = (file_path, job_id, tenant_id)
        return SimpleNamespace(id="celery-task-abc")

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(delay=_delay)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("manual.txt", io.BytesIO(b"hello durable"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["filename"] == "manual.txt"
    assert body["tenant_id"] == "default"
    job_id = body["job_id"]
    uuid.UUID(job_id)
    assert body.get("task_id") == "celery-task-abc"
    assert "task_id=celery-task-abc" in body["message"] or body.get("task_id") == "celery-task-abc"

    file_path, enqueued_job_id, enqueued_tenant = captured["args"]
    assert enqueued_job_id == job_id
    assert enqueued_tenant == "default"
    assert Path(file_path).name == "manual.txt"
    # Absolute host path is fine for the worker payload; public response must not expose it.
    assert ":" not in body["job_id"]
    assert body.get("source_path") is None

    import asyncio

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert job.tenant_id == "default"
    assert job.status == "queued"
    assert job.filename == "manual.txt"
    assert job.celery_task_id == "celery-task-abc"
    assert not Path(job.source_path).is_absolute()
    assert "manual.txt" in job.source_path


def test_non_default_upload_reuses_job_and_completes_durably(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            self.recursive = recursive

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="doc", metadata={"source": "guide.txt"})]

    def _fake_rebuild(docs, tenant_id: str = "default") -> bool:
        assert tenant_id == "acme-corp"
        return True

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _fake_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("guide.txt", io.BytesIO(b"content"), "text/plain")},
        headers=_headers("acme-corp"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tenant_id"] == "acme-corp"
    assert body["tenant_id"] != "default"
    job_id = body["job_id"]
    uuid.UUID(job_id)

    import asyncio

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert job.tenant_id == "acme-corp"
    assert job.status == "completed"
    assert job.finished_at is not None
    assert job.error is None
    assert isinstance(job.result, dict)
    assert job.started_at is not None


@pytest.mark.parametrize(
    ("scenario", "expected_fragment"),
    [
        ("false_rebuild", "index"),
        ("exception", "ingest"),
        ("no_content", "content"),
    ],
)
def test_sync_failure_paths_produce_durable_failed_state(
    scenario: str,
    expected_fragment: str,
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            if scenario == "no_content":
                return []
            return [SimpleNamespace(page_content="x", metadata={"source": "a.txt"})]

    def _fake_rebuild(docs, tenant_id: str = "default") -> bool:
        if scenario == "false_rebuild":
            return False
        if scenario == "exception":
            raise RuntimeError("boom indexing")
        return True

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _fake_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("a.txt", io.BytesIO(b"payload"), "text/plain")},
        headers=_headers("tenant-fail"),
    )

    assert resp.status_code == 200
    body = resp.json()
    job_id = body["job_id"]
    assert body["tenant_id"] == "tenant-fail"
    # Public response must not leak raw exception details.
    assert "boom" not in body.get("message", "").lower()

    import asyncio

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], job_id))
    assert job is not None
    assert job.status == "failed"
    assert job.finished_at is not None
    assert job.error is not None
    assert expected_fragment.lower() in job.error.lower()
    assert "boom" not in job.error.lower()
    # Pollable safe terminal error via canonical route.
    poll = client_with_key.get(
        f"/api/jobs/{job_id}",
        headers=_headers("tenant-fail"),
    )
    assert poll.status_code == 200
    poll_body = poll.json()
    assert poll_body["status"] == "failed"
    assert poll_body["error"] is not None
    assert expected_fragment.lower() in poll_body["error"].lower()
    assert "boom" not in poll_body["error"].lower()
    assert poll_body["job_id"] == job_id
    assert poll_body["tenant_id"] == "tenant-fail"


def test_upload_response_tenant_id_is_never_model_default_for_non_default_caller(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app
    import api.routers.upload as upload_mod

    # Model must not silently rebind ownership via default="default".
    fields = upload_mod.UploadResponse.model_fields
    assert "job_id" in fields
    assert fields["job_id"].is_required()
    assert "tenant_id" in fields
    # Either required, or no default that can mask a non-default tenant.
    tenant_field = fields["tenant_id"]
    assert tenant_field.is_required() or tenant_field.default is None

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "b.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("b.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("not-default"),
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "not-default"


# ---------------------------------------------------------------------------
# 5–6. Poll routes: tenant isolation + DB-only (Celery unusable)
# ---------------------------------------------------------------------------


def test_tenant_isolation_on_job_poll(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "c.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    upload = client_with_key.post(
        "/api/upload",
        files={"file": ("c.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("tenant-a"),
    )
    assert upload.status_code == 200
    job_id = upload.json()["job_id"]

    own = client_with_key.get(f"/api/jobs/{job_id}", headers=_headers("tenant-a"))
    assert own.status_code == 200
    assert own.json()["job_id"] == job_id
    assert own.json()["tenant_id"] == "tenant-a"

    foreign = client_with_key.get(f"/api/jobs/{job_id}", headers=_headers("tenant-b"))
    assert foreign.status_code == 404

    unknown = client_with_key.get(
        f"/api/jobs/{uuid.uuid4()}",
        headers=_headers("tenant-a"),
    )
    assert unknown.status_code == 404

    # Compatibility alias must also scope by tenant.
    foreign_tasks = client_with_key.get(
        f"/api/tasks/{job_id}",
        headers=_headers("tenant-b"),
    )
    assert foreign_tasks.status_code == 404


def test_jobs_and_tasks_routes_read_db_when_celery_unusable(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app
    from tasks.celery_app import celery_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "d.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    def _broken_async_result(task_id: str):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(celery_app, "AsyncResult", _broken_async_result)

    upload = client_with_key.post(
        "/api/upload",
        files={"file": ("d.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("poll-tenant"),
    )
    assert upload.status_code == 200
    job_id = upload.json()["job_id"]

    jobs_resp = client_with_key.get(
        f"/api/jobs/{job_id}",
        headers=_headers("poll-tenant"),
    )
    tasks_resp = client_with_key.get(
        f"/api/tasks/{job_id}",
        headers=_headers("poll-tenant"),
    )

    assert jobs_resp.status_code == 200
    assert tasks_resp.status_code == 200
    for body in (jobs_resp.json(), tasks_resp.json()):
        assert body["job_id"] == job_id
        assert body["tenant_id"] == "poll-tenant"
        assert body["status"] == "completed"
        assert body["result"] is not None
        assert "created_at" in body
        assert body.get("error") in (None, "")


def test_tasks_route_resolves_secondary_celery_task_id(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    def _delay(file_path: str, job_id: str, tenant_id: str):
        return SimpleNamespace(id="secondary-celery-id")

    async def _fake_log_audit(**kwargs) -> None:
        return None

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(delay=_delay)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)

    upload = client_with_key.post(
        "/api/upload",
        files={"file": ("e.txt", io.BytesIO(b"x"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )
    assert upload.status_code == 200
    job_id = upload.json()["job_id"]

    by_task = client_with_key.get(
        "/api/tasks/secondary-celery-id",
        headers={"X-API-Key": "secret123"},
    )
    assert by_task.status_code == 200
    assert by_task.json()["job_id"] == job_id
    assert by_task.json()["task_id"] == "secondary-celery-id"
    assert by_task.json()["status"] == "queued"


# ---------------------------------------------------------------------------
# 7–8. Worker task bridge
# ---------------------------------------------------------------------------


def test_worker_propagates_tenant_and_records_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod
    from tasks import ingest_task

    job_id = uuid.uuid4()
    upload = tmp_path / "worker.txt"
    upload.write_text("hello", encoding="utf-8")

    # Seed durable row via sync path used by the worker.
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=job_id,
                tenant_id="worker-tenant",
                filename="worker.txt",
                source_path="data/uploads/worker.txt",
                status="queued",
            )
        )
        session.commit()

    calls: dict[str, Any] = {}
    docs = [SimpleNamespace(page_content="hello")]

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            assert recursive is False

        def load_documents(self, path: str):
            return docs

    def fake_build(loaded_docs, chunk_config, embeddings=None, tenant_id: str = "default", **kwargs):
        calls["docs"] = loaded_docs
        calls["tenant_id"] = tenant_id
        calls["chunk_config"] = chunk_config
        return MagicMock(), list(loaded_docs)

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr("vectordb.manager.build_vector_store", fake_build)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=100, chunk_overlap=10),
    )

    states: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: states.append((kwargs["state"], kwargs.get("meta") or {})),
    )

    result = ingest_task.ingest_document.run(
        str(upload),
        str(job_id),
        "worker-tenant",
    )

    assert result["status"] == "ok"
    assert calls["tenant_id"] == "worker-tenant"
    assert calls["docs"] == docs

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None
        assert row.started_at is not None

    assert ("PROCESSING", {"step": "loading"}) in states or any(
        s[0] == "PROCESSING" for s in states
    )


def test_worker_records_failed_and_raises_on_loader_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod
    from tasks import ingest_task

    job_id = uuid.uuid4()
    upload = tmp_path / "bad.txt"
    upload.write_text("x", encoding="utf-8")

    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=job_id,
                tenant_id="fail-tenant",
                filename="bad.txt",
                source_path="data/uploads/bad.txt",
                status="queued",
            )
        )
        session.commit()

    class BrokenLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            raise RuntimeError("parse failed")

    monkeypatch.setattr("ingestion.loader.DocumentLoader", BrokenLoader)
    build_calls: list[Any] = []
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda *a, **k: build_calls.append((a, k)),
    )
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with pytest.raises(Exception) as exc_info:
        ingest_task.ingest_document.run(str(upload), str(job_id), "fail-tenant")

    raised = str(exc_info.value).lower()
    assert "document loading failed" in raised or "loading failed" in raised
    assert "parse failed" not in raised
    assert build_calls == []

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.finished_at is not None
        assert row.error is not None
        assert "parse failed" not in row.error.lower()


def test_worker_unknown_or_mismatched_job_prevents_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from ingestion import jobs as jobs_mod
    from tasks import ingest_task

    job_id = uuid.uuid4()
    upload = tmp_path / "x.txt"
    upload.write_text("x", encoding="utf-8")

    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=job_id,
                tenant_id="owner",
                filename="x.txt",
                source_path="data/uploads/x.txt",
                status="queued",
            )
        )
        session.commit()

    build_calls: list[Any] = []

    def _build(*args, **kwargs):
        build_calls.append((args, kwargs))
        return MagicMock(), []

    monkeypatch.setattr("vectordb.manager.build_vector_store", _build)
    monkeypatch.setattr(
        "ingestion.loader.DocumentLoader",
        lambda recursive=False: SimpleNamespace(
            load_documents=lambda path: [SimpleNamespace(page_content="x")]
        ),
    )

    # Wrong tenant
    with pytest.raises(Exception):
        ingest_task.ingest_document.run(str(upload), str(job_id), "other-tenant")
    assert build_calls == []

    # Unknown job
    with pytest.raises(Exception):
        ingest_task.ingest_document.run(str(upload), str(uuid.uuid4()), "owner")
    assert build_calls == []

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "queued"  # must not mutate foreign/unknown path incorrectly


# ---------------------------------------------------------------------------
# QA follow-up: durable truthfulness + safe public errors
# ---------------------------------------------------------------------------


def test_mark_running_failure_prevents_rebuild_and_returns_5xx(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    """Fail-closed: no vector rebuild and no success claim if durable running fails."""
    import api.app as api_app
    import api.routers.upload as upload_mod

    rebuild_calls: list[Any] = []

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "r.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_running(job_id, tenant_id, error=None, result=None):
        raise RuntimeError("db write failed for running")

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": rebuild_calls.append(tenant_id) or True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(upload_mod, "mark_job_running", _boom_running, raising=False)
    monkeypatch.setattr(
        "ingestion.jobs.mark_job_running",
        _boom_running,
    )

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("r.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("truth-running"),
    )

    assert resp.status_code >= 500
    body = resp.json()
    detail = str(body.get("detail", body))
    assert "db write failed" not in detail.lower()
    assert rebuild_calls == []

    # Authoritative row must not be completed/ok-looking after transition failure.
    import asyncio

    from sqlalchemy import select

    async def _latest():
        async with ingestion_jobs_db["async_session"]() as session:
            result = await session.execute(
                select(IngestionJob).where(IngestionJob.tenant_id == "truth-running")
            )
            return result.scalars().all()

    rows = asyncio.run(_latest())
    assert rows
    assert all(r.status in ("queued", "failed") for r in rows)
    assert all(r.status != "completed" for r in rows)


def test_mark_completed_failure_never_returns_ok(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "c.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_completed(job_id, tenant_id, result=None):
        raise RuntimeError("completed transition lost")

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr("ingestion.jobs.mark_job_completed", _boom_completed)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("c.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("truth-completed"),
    )

    assert resp.status_code >= 500
    body = resp.json()
    # Must not claim terminal success when durable completed write failed.
    if isinstance(body, dict) and "status" in body:
        assert body["status"] != "ok"
    detail = str(body.get("detail", body))
    assert "completed transition lost" not in detail.lower()


def test_mark_completed_missing_row_never_returns_ok(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "m.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _missing_completed(job_id, tenant_id, result=None):
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": True,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr("ingestion.jobs.mark_job_completed", _missing_completed)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("m.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("truth-missing-completed"),
    )

    assert resp.status_code >= 500
    body = resp.json()
    if isinstance(body, dict) and "status" in body:
        assert body["status"] != "ok"


def test_mark_failed_failure_never_returns_partial_terminal(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "f.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_failed(job_id, tenant_id, error: str):
        raise RuntimeError("failed transition lost")

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": False,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr("ingestion.jobs.mark_job_failed", _boom_failed)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("f.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("truth-failed"),
    )

    assert resp.status_code >= 500
    body = resp.json()
    if isinstance(body, dict) and "status" in body:
        assert body["status"] not in ("partial", "ok", "completed", "failed")
    detail = str(body.get("detail", body))
    assert "failed transition lost" not in detail.lower()


def test_set_celery_task_id_failure_returns_5xx_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    def _delay(file_path: str, job_id: str, tenant_id: str):
        return SimpleNamespace(id="orphan-celery-task")

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_set_task(job_id, tenant_id, celery_task_id: str):
        raise RuntimeError("cannot store celery_task_id")

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(delay=_delay)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)
    monkeypatch.setattr("ingestion.jobs.set_celery_task_id", _boom_set_task)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("async.txt", io.BytesIO(b"x"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code >= 500
    body = resp.json()
    if isinstance(body, dict) and "status" in body:
        assert body["status"] != "accepted"
    detail = str(body.get("detail", body))
    assert "cannot store celery_task_id" not in detail.lower()
    assert "orphan-celery-task" not in detail


def test_set_celery_task_id_none_returns_5xx_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    def _delay(file_path: str, job_id: str, tenant_id: str):
        return SimpleNamespace(id="unlinked-celery-task")

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _none_set_task(job_id, tenant_id, celery_task_id: str):
        return None

    fake_module = types.ModuleType("tasks.ingest_task")
    fake_module.ingest_document = SimpleNamespace(delay=_delay)
    monkeypatch.setitem(sys.modules, "tasks.ingest_task", fake_module)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)
    monkeypatch.setattr("ingestion.jobs.set_celery_task_id", _none_set_task)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("async2.txt", io.BytesIO(b"x"), "text/plain")},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code >= 500
    body = resp.json()
    if isinstance(body, dict) and "status" in body:
        assert body["status"] != "accepted"


def test_safe_error_message_redacts_secrets_and_pii() -> None:
    from ingestion.jobs import safe_error_message

    email_msg = safe_error_message("contact support@example.com about the job")
    assert "support@example.com" not in email_msg
    assert "@" in email_msg or "***" in email_msg

    key_msg = safe_error_message("provider failed MISTRAL_API_KEY=sk-secret-value")
    assert "sk-secret-value" not in key_msg
    assert "MISTRAL_API_KEY" in key_msg

    dsn_msg = safe_error_message(
        "connect error postgresql://user:db-password@host/db while indexing"
    )
    assert "db-password" not in dsn_msg
    assert "user:db-password" not in dsn_msg
    assert "postgresql://" in dsn_msg or "host" in dsn_msg


def test_sync_upload_exception_response_is_generic_and_safe(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
) -> None:
    import api.app as api_app

    secret_blob = (
        "boom for support@example.com with MISTRAL_API_KEY=sk-secret-value "
        "and postgresql://user:db-password@host/db"
    )

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "s.txt"})]

    def _raise_rebuild(docs, tenant_id: str = "default") -> bool:
        raise RuntimeError(secret_blob)

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _raise_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    resp = client_with_key.post(
        "/api/upload",
        files={"file": ("s.txt", io.BytesIO(b"x"), "text/plain")},
        headers=_headers("safe-sync"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert body["tenant_id"] == "safe-sync"
    message = body["message"]
    assert "sk-secret-value" not in message
    assert "db-password" not in message
    assert "support@example.com" not in message
    assert secret_blob not in message

    import asyncio

    job = asyncio.run(_fetch_job(ingestion_jobs_db["async_session"], body["job_id"]))
    assert job is not None
    assert job.status == "failed"
    assert job.error is not None
    assert "sk-secret-value" not in job.error
    assert "db-password" not in job.error
    assert "support@example.com" not in job.error


# ---------------------------------------------------------------------------
# Boundary log / file-save secret redaction (step-4.1 residual QA)
# ---------------------------------------------------------------------------


def test_sync_ingest_boundary_logs_omit_secret_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Handled sync ingest boundary must not log raw exception message/traceback."""
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "log.txt"})]

    def _raise_rebuild(docs, tenant_id: str = "default") -> bool:
        raise RuntimeError(_SECRET_BLOB)

    async def _fake_log_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_rebuild_vector_store_from_docs", _raise_rebuild)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    with caplog.at_level(logging.ERROR, logger="api.routers.upload"):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("log.txt", io.BytesIO(b"x"), "text/plain")},
            headers=_headers("log-safe-sync"),
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "partial"
    _assert_no_secret_leak(caplog.text)
    _assert_no_secret_leak(resp.json().get("message", ""))


def test_create_job_boundary_logs_omit_secret_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import api.app as api_app

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_create(**kwargs):
        raise RuntimeError(_SECRET_BLOB)

    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(api_app, "_DocumentLoader", None)
    monkeypatch.setattr(api_app, "_build_vector_store", None)
    monkeypatch.setattr("ingestion.jobs.create_ingestion_job", _boom_create)

    with caplog.at_level(logging.ERROR, logger="api.routers.upload"):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("create.txt", io.BytesIO(b"x"), "text/plain")},
            headers=_headers("log-safe-create"),
        )

    assert resp.status_code >= 500
    detail = str(resp.json().get("detail", resp.json()))
    _assert_no_secret_leak(detail)
    _assert_no_secret_leak(caplog.text)


def test_durable_transition_boundary_logs_omit_secret_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "t.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    async def _boom_failed(job_id, tenant_id, error: str):
        raise RuntimeError(_SECRET_BLOB)

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(
        api_app,
        "_rebuild_vector_store_from_docs",
        lambda docs, tenant_id="default": False,
    )
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr("ingestion.jobs.mark_job_failed", _boom_failed)

    with caplog.at_level(logging.ERROR, logger="api.routers.upload"):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("t.txt", io.BytesIO(b"x"), "text/plain")},
            headers=_headers("log-safe-transition"),
        )

    assert resp.status_code >= 500
    detail = str(resp.json().get("detail", resp.json()))
    _assert_no_secret_leak(detail)
    _assert_no_secret_leak(caplog.text)


def test_category_preprocess_boundary_logs_omit_secret_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import api.app as api_app

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="x", metadata={"source": "cat.txt"})]

    async def _fake_log_audit(**kwargs) -> None:
        return None

    def _boom_annotate(docs, tenant_id: str = "default"):
        raise RuntimeError(_SECRET_BLOB)

    monkeypatch.setattr(api_app, "_DocumentLoader", FakeLoader)
    monkeypatch.setattr(api_app, "_build_vector_store", None)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)
    monkeypatch.setattr(
        "ingestion.categorizer.annotate_documents_with_categories",
        _boom_annotate,
    )

    with caplog.at_level(logging.WARNING, logger="api.routers.upload"):
        resp = client_with_key.post(
            "/api/upload",
            files={"file": ("cat.txt", io.BytesIO(b"x"), "text/plain")},
            headers=_headers("log-safe-category"),
        )

    # Category failure is non-fatal; upload continues with partial/ok depending on stack.
    assert resp.status_code == 200
    _assert_no_secret_leak(caplog.text)


def test_worker_load_and_index_boundary_logs_omit_secret_exception_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ingestion import jobs as jobs_mod
    from tasks import ingest_task

    # --- loading phase ---
    load_job_id = uuid.uuid4()
    load_upload = tmp_path / "load-secret.txt"
    load_upload.write_text("x", encoding="utf-8")
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=load_job_id,
                tenant_id="log-worker-load",
                filename="load-secret.txt",
                source_path="data/uploads/load-secret.txt",
                status="queued",
            )
        )
        session.commit()

    class BrokenLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            raise RuntimeError(_SECRET_BLOB)

    monkeypatch.setattr("ingestion.loader.DocumentLoader", BrokenLoader)
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with caplog.at_level(logging.ERROR, logger="tasks.ingest_task"):
        with pytest.raises(RuntimeError):
            ingest_task.ingest_document.run(
                str(load_upload),
                str(load_job_id),
                "log-worker-load",
            )

    _assert_no_secret_leak(caplog.text)

    # --- indexing phase ---
    caplog.clear()
    index_job_id = uuid.uuid4()
    index_upload = tmp_path / "index-secret.txt"
    index_upload.write_text("hello", encoding="utf-8")
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=index_job_id,
                tenant_id="log-worker-index",
                filename="index-secret.txt",
                source_path="data/uploads/index-secret.txt",
                status="queued",
            )
        )
        session.commit()

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda docs, chunk_config, embeddings=None, tenant_id="default", **kwargs: (
            _ for _ in ()
        ).throw(RuntimeError(_SECRET_BLOB)),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=10, chunk_overlap=1),
    )

    with caplog.at_level(logging.ERROR, logger="tasks.ingest_task"):
        with pytest.raises(RuntimeError):
            ingest_task.ingest_document.run(
                str(index_upload),
                str(index_job_id),
                "log-worker-index",
            )

    _assert_no_secret_leak(caplog.text)

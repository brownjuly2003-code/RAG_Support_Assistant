from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from db.models import IngestionJob
from ingestion import jobs as jobs_mod
from tasks import ingest_task


@pytest.fixture(autouse=True)
def _capture_task_state(monkeypatch):
    states: list[tuple[str, dict]] = []

    def fake_update_state(*, state: str, meta: dict) -> None:
        states.append((state, meta))

    monkeypatch.setattr(ingest_task.ingest_document, "update_state", fake_update_state)
    return states


def _seed_job(job_id: uuid.UUID, tenant_id: str, filename: str = "doc.txt") -> None:
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=job_id,
                tenant_id=tenant_id,
                filename=filename,
                source_path=f"data/uploads/{filename}",
                status="queued",
            )
        )
        session.commit()


def test_ingest_document_raises_for_missing_file(
    tmp_path,
    _capture_task_state,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    _seed_job(job_id, "default", "missing.txt")

    with pytest.raises(FileNotFoundError):
        ingest_task.ingest_document.run(
            str(tmp_path / "missing.txt"),
            str(job_id),
            "default",
        )

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error is not None
        assert "File not found" in row.error
    assert any(state == "PROCESSING" for state, _ in _capture_task_state)


def test_ingest_document_raises_when_loading_fails(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed_job(job_id, "default")

    class BrokenLoader:
        def __init__(self, recursive: bool) -> None:
            assert recursive is False

        def load_documents(self, path: str):
            raise RuntimeError("parse failed")

    monkeypatch.setattr("ingestion.loader.DocumentLoader", BrokenLoader)

    with pytest.raises(RuntimeError, match="Document loading failed|Loading failed"):
        ingest_task.ingest_document.run(str(upload), str(job_id), "default")

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error is not None
        assert "parse failed" not in row.error.lower()


def test_ingest_document_raises_when_loader_has_no_docs(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "empty.txt"
    upload.write_text("", encoding="utf-8")
    _seed_job(job_id, "default", "empty.txt")

    class EmptyLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            return []

    monkeypatch.setattr("ingestion.loader.DocumentLoader", EmptyLoader)

    with pytest.raises(RuntimeError, match="No text content"):
        ingest_task.ingest_document.run(str(upload), str(job_id), "default")

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"


def test_ingest_document_indexes_loaded_docs(
    tmp_path,
    monkeypatch,
    _capture_task_state,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed_job(job_id, "acme", "doc.txt")
    calls: dict[str, object] = {}
    docs = [SimpleNamespace(page_content="hello")]

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            assert recursive is False

        def load_documents(self, path: str):
            calls["load_path"] = path
            return docs

    def fake_build_vector_store(loaded_docs, chunk_config, embeddings=None, tenant_id: str = "default", **kwargs):
        calls["docs"] = loaded_docs
        calls["chunk_config"] = chunk_config
        calls["embeddings"] = embeddings
        calls["tenant_id"] = tenant_id

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr("vectordb.manager.build_vector_store", fake_build_vector_store)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=123, chunk_overlap=45),
    )

    result = ingest_task.ingest_document.run(str(upload), str(job_id), "acme")

    assert result["status"] == "ok"
    assert result["docs_count"] == 1
    assert calls["tenant_id"] == "acme"
    assert calls["docs"] == docs
    assert calls["chunk_config"] == {"chunk_size": 123, "chunk_overlap": 45}
    assert calls["embeddings"] == "embeddings"
    assert any(state == "PROCESSING" for state, _ in _capture_task_state)

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None


def test_ingest_document_raises_when_indexing_fails(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed_job(job_id, "default")

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda docs, chunk_config, embeddings=None, tenant_id="default", **kwargs: (
            _ for _ in ()
        ).throw(RuntimeError("index failed")),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=123, chunk_overlap=45),
    )

    with pytest.raises(RuntimeError, match="Vector indexing failed|Indexing failed"):
        ingest_task.ingest_document.run(str(upload), str(job_id), "default")

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error is not None
        assert "index failed" not in row.error.lower() or "vector indexing failed" in row.error.lower()


def test_progress_update_failure_does_not_block_durable_completion(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    """Celery result-backend failure must not preempt durable running/completed."""
    job_id = uuid.uuid4()
    upload = tmp_path / "progress.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed_job(job_id, "progress-tenant", "progress.txt")

    order: list[str] = []

    def _boom_update_state(*, state: str, meta: dict) -> None:
        order.append(f"progress:{meta.get('step', state)}")
        raise RuntimeError("redis result backend unavailable")

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            order.append("load")
            return [SimpleNamespace(page_content="hello")]

    def fake_build(loaded_docs, chunk_config, embeddings=None, tenant_id: str = "default", **kwargs):
        order.append("build")
        return None

    real_claim = jobs_mod.sync_claim_running

    def _claim_running(job_uuid, tenant_id):
        order.append("running")
        return real_claim(job_uuid, tenant_id)

    monkeypatch.setattr(ingest_task.ingest_document, "update_state", _boom_update_state)
    monkeypatch.setattr(jobs_mod, "sync_claim_running", _claim_running)
    monkeypatch.setattr("ingestion.jobs.sync_claim_running", _claim_running)
    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr("vectordb.manager.build_vector_store", fake_build)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=10, chunk_overlap=1),
    )

    result = ingest_task.ingest_document.run(
        str(upload),
        str(job_id),
        "progress-tenant",
    )

    assert result["status"] == "ok"
    assert "running" in order
    # Durable running must be recorded before the first progress update attempt.
    assert order.index("running") < order.index("progress:loading")
    assert "build" in order

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None


def test_progress_update_failure_still_records_durable_failed_on_loader_error(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "bad-progress.txt"
    upload.write_text("x", encoding="utf-8")
    _seed_job(job_id, "progress-fail", "bad-progress.txt")

    def _boom_update_state(*, state: str, meta: dict) -> None:
        raise RuntimeError("redis result backend unavailable")

    class BrokenLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            raise RuntimeError("parse failed with support@example.com")

    build_calls: list[object] = []
    monkeypatch.setattr(ingest_task.ingest_document, "update_state", _boom_update_state)
    monkeypatch.setattr("ingestion.loader.DocumentLoader", BrokenLoader)
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda *a, **k: build_calls.append(1),
    )

    with pytest.raises(RuntimeError) as exc_info:
        ingest_task.ingest_document.run(str(upload), str(job_id), "progress-fail")

    # Phase-level public/worker message; raw loader detail must not leak.
    raised = str(exc_info.value).lower()
    assert "document loading failed" in raised or "loading failed" in raised
    assert "support@example.com" not in raised
    assert "parse failed" not in raised
    assert build_calls == []

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.finished_at is not None
        assert row.error is not None
        assert "support@example.com" not in row.error
        assert "parse failed" not in row.error


def test_worker_missing_file_error_omits_absolute_path(
    tmp_path,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    missing = tmp_path / "subdir" / "secret-name.txt"
    _seed_job(job_id, "path-tenant", "secret-name.txt")

    with pytest.raises(FileNotFoundError) as exc_info:
        ingest_task.ingest_document.run(str(missing), str(job_id), "path-tenant")

    raised = str(exc_info.value)
    assert str(missing) not in raised
    # Absolute host path must not appear in public/durable error.
    assert ":\\" not in raised
    assert not raised.startswith("/")

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error is not None
        assert str(missing) not in row.error
        assert "File not found" in row.error or "not found" in row.error.lower()


def test_worker_phase_messages_redact_secret_bearing_exceptions(
    tmp_path,
    monkeypatch,
    ingestion_jobs_db,
) -> None:
    job_id = uuid.uuid4()
    upload = tmp_path / "secret-index.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed_job(job_id, "secret-tenant", "secret-index.txt")

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda docs, chunk_config, embeddings=None, tenant_id="default", **kwargs: (
            _ for _ in ()
        ).throw(
            RuntimeError(
                "index failed MISTRAL_API_KEY=sk-secret-value "
                "postgresql://user:db-password@host/db"
            )
        ),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=10, chunk_overlap=1),
    )

    with pytest.raises(RuntimeError) as exc_info:
        ingest_task.ingest_document.run(str(upload), str(job_id), "secret-tenant")

    raised = str(exc_info.value)
    assert "sk-secret-value" not in raised
    assert "db-password" not in raised
    assert "vector indexing failed" in raised.lower() or "indexing failed" in raised.lower()

    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error is not None
        assert "sk-secret-value" not in row.error
        assert "db-password" not in row.error

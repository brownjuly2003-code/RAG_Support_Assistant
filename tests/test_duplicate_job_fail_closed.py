"""2.6f — duplicate job fail-closed (no double index publish).

Proves worker/job identity handling when the same durable job is delivered
twice or contended by two claimants:

1. Terminal completed/failed jobs cannot be reclaimed; the worker never loads
   documents or builds/publishes an index.
2. Concurrent claims on one queued job yield exactly one winner; the loser
   fails closed before any index mutation.

Complements upload-level Idempotency-Key replay (step 4.4) with the worker-side
duplicate-delivery contract from plan §2 fault injection.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from db.models import IngestionJob
from ingestion import jobs as jobs_mod


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _seed(
    *,
    status: str,
    tenant_id: str = "dup",
    job_id: uuid.UUID | None = None,
    filename: str = "doc.txt",
    celery_task_id: str | None = "celery-dup",
    lease_token: str | None = None,
    result: dict[str, Any] | None = None,
) -> uuid.UUID:
    jid = job_id or uuid.uuid4()
    now = _utc()
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=jid,
                tenant_id=tenant_id,
                filename=filename,
                source_path=f"data/uploads/{filename}",
                status=status,
                celery_task_id=celery_task_id,
                created_at=now,
                started_at=now if status in {"running", "completed", "failed"} else None,
                finished_at=now if status in {"completed", "failed"} else None,
                lease_token=lease_token,
                result=result,
                error="prior failure" if status == "failed" else None,
            )
        )
        session.commit()
    return jid


def _get(job_id: uuid.UUID) -> IngestionJob:
    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, job_id)
        assert row is not None
        session.expunge(row)
        return row


def test_claim_refuses_completed_and_failed_terminal_rows(
    ingestion_jobs_db,
) -> None:
    completed_id = _seed(status="completed", result={"status": "ok"})
    failed_id = _seed(status="failed", filename="fail.txt")

    with pytest.raises(jobs_mod.JobOwnershipError, match="Failed to claim"):
        jobs_mod.sync_claim_running(completed_id, "dup")
    with pytest.raises(jobs_mod.JobOwnershipError, match="Failed to claim"):
        jobs_mod.sync_claim_running(failed_id, "dup")

    assert _get(completed_id).status == "completed"
    assert _get(failed_id).status == "failed"


def test_worker_redelivery_of_completed_job_never_builds_or_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from tasks import ingest_task

    job_id = _seed(
        status="completed",
        result={
            "status": "ok",
            "index_publication": {
                "active_collection": "rag_docs-v-dup-aaaaaaaaaaaaaaaa",
                "manifest_generation": 1,
            },
        },
    )
    upload = tmp_path / "doc.txt"
    upload.write_text("hello-completed", encoding="utf-8")

    load_calls: list[str] = []
    build_calls: list[Any] = []

    class TrackingLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            load_calls.append(path)
            return [SimpleNamespace(page_content="hello-completed")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", TrackingLoader)
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store_with_publication",
        lambda *a, **k: build_calls.append(("build", a, k)) or SimpleNamespace(
            store=object(),
            chunks=[],
            publication=None,
        ),
    )
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with pytest.raises(jobs_mod.JobOwnershipError):
        ingest_task.ingest_document.run(str(upload), str(job_id), "dup")

    assert load_calls == []
    assert build_calls == []
    row = _get(job_id)
    assert row.status == "completed"
    # Prior publication receipt remains; no second bind/publish side effect.
    assert row.result is not None
    assert row.result.get("index_publication", {}).get("manifest_generation") == 1


def test_worker_redelivery_of_failed_job_never_builds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from tasks import ingest_task

    job_id = _seed(status="failed")
    upload = tmp_path / "doc.txt"
    upload.write_text("hello-failed", encoding="utf-8")

    load_calls: list[str] = []
    build_calls: list[str] = []

    class TrackingLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            load_calls.append(path)
            return [SimpleNamespace(page_content="hello-failed")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", TrackingLoader)
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store_with_publication",
        lambda *a, **k: build_calls.append("build"),
    )
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with pytest.raises(jobs_mod.JobOwnershipError):
        ingest_task.ingest_document.run(str(upload), str(job_id), "dup")

    assert load_calls == []
    assert build_calls == []
    assert _get(job_id).status == "failed"


def test_concurrent_claim_exactly_one_winner(
    ingestion_jobs_db,
) -> None:
    """Two workers racing the same queued job: one claim wins, one fails closed."""
    job_id = _seed(status="queued")
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, str]] = []
    lock = threading.Lock()

    def _worker() -> None:
        try:
            barrier.wait(timeout=5)
            token = jobs_mod.sync_claim_running(job_id, "dup")
            with lock:
                outcomes.append(("won", token))
        except jobs_mod.JobOwnershipError:
            with lock:
                outcomes.append(("lost", "JobOwnershipError"))
        except BaseException as exc:  # pragma: no cover
            with lock:
                outcomes.append(("err", type(exc).__name__))

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not t1.is_alive()
    assert not t2.is_alive()

    kinds = [k for k, _ in outcomes]
    assert kinds.count("won") == 1, outcomes
    assert kinds.count("lost") == 1, outcomes
    assert _get(job_id).status == "running"


def test_idempotent_create_reuse_does_not_create_second_job_row(
    ingestion_jobs_db,
) -> None:
    """Duplicate same-key/same-fingerprint create is a replay, not a second job."""
    import asyncio

    key_hash = "a" * 64
    fingerprint = "b" * 64

    async def _once(job_id: uuid.UUID | None = None):
        return await jobs_mod.create_or_reuse_ingestion_job(
            tenant_id="dup",
            filename="doc.txt",
            source_path="data/uploads/doc.txt",
            job_id=job_id or uuid.uuid4(),
            celery_task_id=None,
            idempotency_key_hash=key_hash,
            payload_fingerprint=fingerprint,
        )

    first = asyncio.run(_once())
    second = asyncio.run(_once())
    assert first.created is True
    assert second.created is False
    assert first.job.id == second.job.id

    with jobs_mod.sync_session() as session:
        from sqlalchemy import func, select

        count = session.execute(select(func.count()).select_from(IngestionJob)).scalar_one()
    assert int(count) == 1

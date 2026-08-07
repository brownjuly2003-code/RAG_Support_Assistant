"""2.6g — worker outage/recovery fail-closed (no double-complete / silent publish).

Proves stale lease / reaper / lost-ownership paths stay fail-closed:

1. After reaper (or mid-flight lease loss) a zombie worker cannot complete the
   job or bind an index publication receipt.
2. When ownership is already gone before indexing, the worker never calls
   ``build_vector_store_with_publication`` (no silent publish window from a
   lagging background heartbeat).
3. Terminal reaper failures cannot be reclaimed or overwritten by late CAS.

Complements 2.6f (duplicate delivery) with the outage/recovery residual of
plan §2 fault injection. Local only — no live Celery/Redis multi-service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from db.models import IngestionJob
from ingestion import jobs as jobs_mod
from ingestion import liveness as live_mod


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _seed(
    *,
    status: str = "queued",
    tenant_id: str = "outage",
    job_id: uuid.UUID | None = None,
    filename: str = "doc.txt",
    celery_task_id: str | None = "celery-outage",
    lease_token: str | None = None,
    heartbeat_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
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
                created_at=now - timedelta(seconds=300),
                started_at=started_at
                if started_at is not None
                else (now if status in {"running", "completed", "failed"} else None),
                finished_at=finished_at
                if finished_at is not None
                else (now if status in {"completed", "failed"} else None),
                lease_token=lease_token,
                heartbeat_at=heartbeat_at,
                lease_expires_at=lease_expires_at,
                result=result,
                error=error
                if error is not None
                else ("prior failure" if status == "failed" else None),
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


def _patch_worker_safe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    load_calls: list[str] | None = None,
    build_calls: list[Any] | None = None,
    publication: Any | None = None,
) -> None:
    """Stub loader/build/settings so tests never hit real embeddings/Chroma."""
    from tasks import ingest_task

    loads = load_calls if load_calls is not None else []
    builds = build_calls if build_calls is not None else []

    class TrackingLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            loads.append(path)
            return [SimpleNamespace(page_content="hello-outage")]

    def _build(*a: Any, **k: Any) -> SimpleNamespace:
        builds.append(("build", a, k))
        return SimpleNamespace(
            store=object(),
            chunks=[],
            publication=publication,
        )

    monkeypatch.setattr("ingestion.loader.DocumentLoader", TrackingLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store_with_publication",
        _build,
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            chunk_size=10,
            chunk_overlap=1,
            ingestion_job_lease_sec=120,
            ingestion_job_heartbeat_interval_sec=30,
        ),
    )
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )


def test_reaper_expired_lease_blocks_late_complete_and_publication_bind(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After reaper, late complete CAS fails and index bind columns stay empty."""
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "600")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")

    now = _utc()
    token = "zombie-worker-token"
    jid = _seed(
        status="running",
        tenant_id="outage",
        celery_task_id="c-reap-complete",
        started_at=now - timedelta(seconds=400),
        lease_token=token,
        heartbeat_at=now - timedelta(seconds=300),
        lease_expires_at=now - timedelta(seconds=30),
        finished_at=None,
        result=None,
        error=None,
    )

    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["lease_expired"] >= 1
    reaped = _get(jid)
    assert reaped.status == "failed"
    assert reaped.lease_token is None
    reaper_error = reaped.error
    assert reaper_error

    late_result = {
        "status": "ok",
        "docs_count": 1,
        "index_publication": {
            "tenant_id": "outage",
            "active_collection": "rag_docs-outage-v-silent",
            "previous_collection": None,
            "manifest_generation": 99,
        },
    }
    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_mark_completed(jid, "outage", token, result=late_result)

    final = _get(jid)
    assert final.status == "failed"
    assert final.error == reaper_error
    assert final.result is None
    assert final.index_active_collection is None
    assert final.index_previous_collection is None
    assert final.index_manifest_generation is None


def test_reaper_expired_lease_blocks_late_mark_failed_overwrite(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zombie fail path must not overwrite reaper terminal error."""
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "600")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")

    now = _utc()
    token = "zombie-fail-token"
    jid = _seed(
        status="running",
        tenant_id="outage",
        celery_task_id="c-reap-fail",
        started_at=now - timedelta(seconds=400),
        lease_token=token,
        heartbeat_at=now - timedelta(seconds=300),
        lease_expires_at=now - timedelta(seconds=30),
        finished_at=None,
        result=None,
        error=None,
    )
    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["lease_expired"] >= 1
    reaper_error = _get(jid).error

    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_mark_failed(jid, "outage", token, "Vector indexing failed")

    final = _get(jid)
    assert final.status == "failed"
    assert final.error == reaper_error
    assert final.error != "Vector indexing failed"


def test_reaped_job_cannot_be_reclaimed(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery is fail-closed: reaper terminal rows stay non-queued (no auto reclaim)."""
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "600")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")

    now = _utc()
    jid = _seed(
        status="running",
        tenant_id="outage",
        celery_task_id="c-reclaim",
        started_at=now - timedelta(seconds=400),
        lease_token="old-tok",
        heartbeat_at=now - timedelta(seconds=300),
        lease_expires_at=now - timedelta(seconds=10),
        finished_at=None,
        result=None,
        error=None,
    )
    assert live_mod.reap_stale_jobs(now=now)["lease_expired"] >= 1
    assert _get(jid).status == "failed"

    with pytest.raises(jobs_mod.JobOwnershipError, match="Failed to claim"):
        jobs_mod.sync_claim_running(jid, "outage")
    assert _get(jid).status == "failed"
    assert _get(jid).lease_token is None


def test_worker_reaper_before_load_never_builds_or_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    """If reaper clears ownership after claim, worker aborts before load/index."""
    from tasks import ingest_task

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello-outage", encoding="utf-8")
    _seed(
        job_id=job_id,
        status="queued",
        tenant_id="outage",
        celery_task_id="c-pre-load",
        finished_at=None,
        result=None,
        error=None,
    )

    real_claim = jobs_mod.sync_claim_running

    def _claim_then_reap(jid: uuid.UUID, tenant: str) -> str:
        token = real_claim(jid, tenant)
        with jobs_mod.sync_session() as session:
            row = session.get(IngestionJob, jid)
            assert row is not None
            row.status = "failed"
            row.error = "Ingestion job lease expired"
            row.finished_at = _utc()
            row.lease_token = None
            row.lease_expires_at = None
            # Keep last heartbeat for observability (matches reaper contract).
            session.commit()
        return token

    load_calls: list[str] = []
    build_calls: list[Any] = []
    monkeypatch.setattr(jobs_mod, "sync_claim_running", _claim_then_reap)
    monkeypatch.setattr("ingestion.jobs.sync_claim_running", _claim_then_reap)
    _patch_worker_safe(
        monkeypatch,
        load_calls=load_calls,
        build_calls=build_calls,
        publication=SimpleNamespace(
            tenant_id="outage",
            active_collection="should-not-publish",
            previous_collection=None,
            manifest_generation=1,
        ),
    )

    with pytest.raises(jobs_mod.JobOwnershipError):
        ingest_task.ingest_document.run(str(upload), str(job_id), "outage")

    assert load_calls == []
    assert build_calls == []
    row = _get(job_id)
    assert row.status == "failed"
    assert row.error == "Ingestion job lease expired"
    assert row.result is None
    assert row.index_active_collection is None
    assert row.index_manifest_generation is None


def test_worker_reaper_before_index_never_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    """Ownership lost after load still blocks index publish (pre_index probe)."""
    from tasks import ingest_task

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello-outage", encoding="utf-8")
    _seed(
        job_id=job_id,
        status="queued",
        tenant_id="outage",
        celery_task_id="c-pre-index",
        finished_at=None,
        result=None,
        error=None,
    )

    load_calls: list[str] = []
    build_calls: list[Any] = []
    reaped_after_load = {"done": False}

    real_extend = jobs_mod.sync_extend_lease
    extend_calls = {"n": 0}

    def _extend_reap_after_first(
        jid: uuid.UUID, tenant: str, token: str
    ) -> bool:
        # First phase probe (pre_load) succeeds; then simulate outage/reaper
        # before pre_index so publish must not start.
        extend_calls["n"] += 1
        if extend_calls["n"] == 1:
            return real_extend(jid, tenant, token)
        if not reaped_after_load["done"]:
            with jobs_mod.sync_session() as session:
                row = session.get(IngestionJob, jid)
                assert row is not None
                row.status = "failed"
                row.error = "Ingestion job lease expired"
                row.finished_at = _utc()
                row.lease_token = None
                row.lease_expires_at = None
                session.commit()
            reaped_after_load["done"] = True
        return False

    monkeypatch.setattr(jobs_mod, "sync_extend_lease", _extend_reap_after_first)
    monkeypatch.setattr("ingestion.jobs.sync_extend_lease", _extend_reap_after_first)
    _patch_worker_safe(
        monkeypatch,
        load_calls=load_calls,
        build_calls=build_calls,
        publication=SimpleNamespace(
            tenant_id="outage",
            active_collection="should-not-publish",
            previous_collection=None,
            manifest_generation=7,
        ),
    )

    with pytest.raises(jobs_mod.JobOwnershipError):
        ingest_task.ingest_document.run(str(upload), str(job_id), "outage")

    assert load_calls, "load should succeed before pre_index ownership loss"
    assert build_calls == [], "must not publish after ownership loss"
    row = _get(job_id)
    assert row.status == "failed"
    assert row.error == "Ingestion job lease expired"
    assert row.result is None
    assert row.index_active_collection is None
    assert row.index_manifest_generation is None


def test_worker_happy_path_still_completes_with_live_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    """Phase probes must not break a healthy worker that keeps ownership."""
    from tasks import ingest_task

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello-ok", encoding="utf-8")
    _seed(
        job_id=job_id,
        status="queued",
        tenant_id="outage",
        celery_task_id="c-ok",
        finished_at=None,
        result=None,
        error=None,
    )

    pub = SimpleNamespace(
        tenant_id="outage",
        active_collection="rag_docs-outage-v-ok",
        previous_collection=None,
        manifest_generation=3,
    )
    load_calls: list[str] = []
    build_calls: list[Any] = []
    _patch_worker_safe(
        monkeypatch,
        load_calls=load_calls,
        build_calls=build_calls,
        publication=pub,
    )

    result = ingest_task.ingest_document.run(str(upload), str(job_id), "outage")
    assert result["status"] == "ok"
    assert load_calls
    assert build_calls
    row = _get(job_id)
    assert row.status == "completed"
    assert row.error is None
    assert row.result is not None
    assert row.result.get("index_publication", {}).get("manifest_generation") == 3
    assert row.index_active_collection == "rag_docs-outage-v-ok"
    assert row.index_manifest_generation == 3

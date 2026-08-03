"""Plan step 4.3: durable ingestion job lease, heartbeat, and stale reaper.

Does not claim retry/idempotency, queue-age metrics/alerts, ING-02 atomic
publish, or TEN-03 collision resistance.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from db.models import IngestionJob
from ingestion import jobs as jobs_mod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_020_PATH = PROJECT_ROOT / "alembic" / "versions" / "020_ingestion_job_leases.py"

_LEASE_SECRET_MARKERS = (
    "lease-secret-token-value",
    "sk-secret-value",
    "db-password",
    "support@example.com",
)


def _assert_no_secret_leak(text: str) -> None:
    for marker in _LEASE_SECRET_MARKERS:
        assert marker not in text, f"secret leaked: {marker!r} in {text!r}"


def _utc(dt: datetime | None = None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_migration_020() -> ModuleType:
    assert MIGRATION_020_PATH.is_file(), f"missing migration: {MIGRATION_020_PATH}"
    spec = importlib.util.spec_from_file_location(
        "migration_020_ingestion_job_leases",
        MIGRATION_020_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(
    *,
    status: str = "queued",
    tenant_id: str = "t1",
    celery_task_id: str | None = "celery-1",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    lease_token: str | None = None,
    heartbeat_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
    job_id: uuid.UUID | None = None,
    filename: str = "doc.txt",
    error: str | None = None,
) -> uuid.UUID:
    jid = job_id or uuid.uuid4()
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=jid,
                tenant_id=tenant_id,
                filename=filename,
                source_path=f"data/uploads/{filename}",
                status=status,
                celery_task_id=celery_task_id,
                created_at=created_at or _utc(),
                started_at=started_at,
                finished_at=finished_at,
                lease_token=lease_token,
                heartbeat_at=heartbeat_at,
                lease_expires_at=lease_expires_at,
                error=error,
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


# ---------------------------------------------------------------------------
# Schema / migration / public serialization
# ---------------------------------------------------------------------------


def test_orm_has_lease_fields_and_stale_scan_index() -> None:
    table = IngestionJob.__table__
    cols = table.c

    assert "lease_token" in cols
    assert cols.lease_token.nullable is True
    assert "heartbeat_at" in cols
    assert cols.heartbeat_at.nullable is True
    assert "lease_expires_at" in cols
    assert cols.lease_expires_at.nullable is True

    # Timestamps timezone-aware like other job timestamps.
    assert bool(getattr(cols.heartbeat_at.type, "timezone", False)) is True
    assert bool(getattr(cols.lease_expires_at.type, "timezone", False)) is True

    index_cols = {tuple(idx.columns.keys()): idx.name for idx in table.indexes}
    assert any(
        "status" in cols_ and "lease_expires_at" in cols_ for cols_ in index_cols
    ), f"missing status+lease_expires_at index, got {index_cols}"


def test_migration_020_revision_chain_and_schema() -> None:
    module = _load_migration_020()
    assert module.revision == "020"
    assert module.down_revision == "019"

    upgrade_src = inspect.getsource(module.upgrade)
    downgrade_src = inspect.getsource(module.downgrade)

    for col in ("lease_token", "heartbeat_at", "lease_expires_at"):
        assert col in upgrade_src
        assert col in downgrade_src

    assert "lease_expires_at" in upgrade_src
    assert "drop_column" in downgrade_src or "drop_index" in downgrade_src

    calls: list[tuple[Any, ...]] = []

    class _FakeOp:
        def add_column(self, table_name: str, column: Any, **kwargs: Any) -> None:
            calls.append(("add_column", table_name, getattr(column, "name", None)))

        def create_index(
            self, index_name: str, table_name: str, columns: list[str], **kwargs: Any
        ) -> None:
            calls.append(("create_index", index_name, table_name, list(columns)))

        def drop_index(self, index_name: str, table_name: str | None = None, **kwargs: Any) -> None:
            calls.append(("drop_index", index_name, table_name))

        def drop_column(self, table_name: str, column_name: str, **kwargs: Any) -> None:
            calls.append(("drop_column", table_name, column_name))

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

    added = {c[2] for c in upgrade_calls if c[0] == "add_column"}
    assert {"lease_token", "heartbeat_at", "lease_expires_at"} <= added

    index_calls = [c for c in upgrade_calls if c[0] == "create_index"]
    assert any(
        "status" in c[3] and "lease_expires_at" in c[3] for c in index_calls
    ), index_calls

    dropped_cols = {c[2] for c in downgrade_calls if c[0] == "drop_column"}
    assert {"lease_token", "heartbeat_at", "lease_expires_at"} <= dropped_cols


def test_job_public_dict_exposes_timestamps_not_lease_token(
    ingestion_jobs_db,
) -> None:
    now = _utc()
    secret = "lease-secret-token-value"
    jid = _seed(
        status="running",
        lease_token=secret,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=120),
        started_at=now,
    )
    row = _get(jid)
    public = jobs_mod.job_public_dict(row)

    assert "lease_token" not in public
    assert "lease_token" not in str(public)
    assert secret not in str(public)
    assert public["heartbeat_at"] is not None
    assert public["lease_expires_at"] is not None
    # ISO shape with timezone offset or Z
    assert re.search(r"\d{4}-\d{2}-\d{2}T", public["heartbeat_at"])
    assert "+" in public["heartbeat_at"] or public["heartbeat_at"].endswith("Z")
    assert re.search(r"\d{4}-\d{2}-\d{2}T", public["lease_expires_at"])


def test_job_public_dict_handles_naive_timestamps_as_utc(
    ingestion_jobs_db,
) -> None:
    naive = datetime(2026, 8, 2, 12, 0, 0)  # no tzinfo
    jid = _seed(
        status="running",
        lease_token="tok",
        heartbeat_at=naive,
        lease_expires_at=naive + timedelta(seconds=60),
        started_at=naive,
    )
    row = _get(jid)
    # Force naive on the in-memory object (SQLite may already do this).
    row.heartbeat_at = naive
    row.lease_expires_at = naive + timedelta(seconds=60)
    public = jobs_mod.job_public_dict(row)
    assert public["heartbeat_at"] is not None
    assert "+00:00" in public["heartbeat_at"] or public["heartbeat_at"].endswith("Z")


# ---------------------------------------------------------------------------
# Atomic claim / heartbeat / terminal CAS
# ---------------------------------------------------------------------------


def test_claim_running_is_tenant_scoped_single_winner(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")

    jid = _seed(status="queued", tenant_id="owner", celery_task_id="c-1")

    token = jobs_mod.sync_claim_running(jid, "owner")
    assert isinstance(token, str)
    assert len(token) >= 16

    row = _get(jid)
    assert row.status == "running"
    assert row.lease_token == token
    assert row.heartbeat_at is not None
    assert row.lease_expires_at is not None
    assert row.started_at is not None
    # Lease horizon roughly lease_sec from heartbeat
    hb = _utc(row.heartbeat_at)
    exp = _utc(row.lease_expires_at)
    assert 100 <= (exp - hb).total_seconds() <= 140

    # Duplicate claim fails closed
    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_claim_running(jid, "owner")

    # Wrong tenant fails closed without mutating
    jid2 = _seed(status="queued", tenant_id="owner2", celery_task_id="c-2")
    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_claim_running(jid2, "intruder")
    assert _get(jid2).status == "queued"
    assert _get(jid2).lease_token is None

    # Missing row
    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_claim_running(uuid.uuid4(), "owner")

    # Terminal row
    jid3 = _seed(status="completed", tenant_id="owner", celery_task_id="c-3")
    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_claim_running(jid3, "owner")


def test_heartbeat_and_terminal_require_exact_lease_token(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    jid = _seed(status="queued", tenant_id="hb-tenant", celery_task_id="c-hb")
    token = jobs_mod.sync_claim_running(jid, "hb-tenant")
    before = _get(jid)

    ok = jobs_mod.sync_extend_lease(jid, "hb-tenant", token)
    assert ok is True
    after = _get(jid)
    assert after.lease_token == token
    assert _utc(after.heartbeat_at) >= _utc(before.heartbeat_at)
    assert _utc(after.lease_expires_at) >= _utc(before.lease_expires_at)

    # Wrong token
    assert jobs_mod.sync_extend_lease(jid, "hb-tenant", "wrong-token") is False
    # Wrong tenant
    assert jobs_mod.sync_extend_lease(jid, "other", token) is False

    # Terminal CAS success clears active lease ownership (token + expiry).
    last_hb = _utc(after.heartbeat_at)
    jobs_mod.sync_mark_completed(
        jid,
        "hb-tenant",
        token,
        result={"status": "ok"},
    )
    done = _get(jid)
    assert done.status == "completed"
    assert done.lease_token is None
    assert done.lease_expires_at is None
    assert done.finished_at is not None
    # Last successful heartbeat remains observable after terminal transition.
    assert done.heartbeat_at is not None
    assert _utc(done.heartbeat_at) == last_hb

    # Late terminal after ownership lost fails closed
    jid2 = _seed(status="queued", tenant_id="late", celery_task_id="c-late")
    token2 = jobs_mod.sync_claim_running(jid2, "late")
    # Simulate reaper clearing ownership
    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, jid2)
        assert row is not None
        row.status = "failed"
        row.error = "Ingestion job lease expired"
        row.finished_at = _utc()
        row.lease_token = None
        row.lease_expires_at = None
        row.heartbeat_at = None
        session.commit()

    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_mark_completed(jid2, "late", token2, result={"status": "ok"})
    assert _get(jid2).status == "failed"
    assert _get(jid2).error == "Ingestion job lease expired"

    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_mark_failed(jid2, "late", token2, "worker late fail")
    assert _get(jid2).status == "failed"
    assert _get(jid2).error == "Ingestion job lease expired"


def test_reaper_vs_late_completion_race(ingestion_jobs_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from ingestion import liveness as live_mod

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "600")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")

    now = _utc()
    jid = _seed(
        status="running",
        tenant_id="race",
        celery_task_id="c-race",
        started_at=now - timedelta(seconds=200),
        lease_token="worker-token",
        heartbeat_at=now - timedelta(seconds=200),
        lease_expires_at=now - timedelta(seconds=10),  # expired
    )

    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["lease_expired"] >= 1
    row = _get(jid)
    assert row.status == "failed"
    assert row.lease_token is None
    assert row.finished_at is not None
    reaper_error = row.error

    with pytest.raises(jobs_mod.JobOwnershipError):
        jobs_mod.sync_mark_completed(
            jid,
            "race",
            "worker-token",
            result={"status": "ok", "docs_count": 1},
        )
    final = _get(jid)
    assert final.status == "failed"
    assert final.error == reaper_error
    assert final.result is None


# ---------------------------------------------------------------------------
# Late dependency resolution (import-order / fixture isolation)
# ---------------------------------------------------------------------------


def test_liveness_resolves_sync_session_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reaper must not pin sync_session from an earlier import/fixture DB.

    Regression for order-dependent failures: earlier tests import liveness,
    then ingestion_jobs_db rotates jobs.sync_session; reaper must follow.
    """
    from ingestion import liveness as live_mod

    calls: list[str] = []

    @contextmanager
    def _tracked_session():
        calls.append("session")
        session = MagicMock()
        session.scalar.return_value = None
        result = MagicMock()
        result.rowcount = 0
        session.execute.return_value = result
        yield session

    monkeypatch.setattr(jobs_mod, "sync_session", _tracked_session)
    counts = live_mod.reap_stale_jobs(now=_utc())
    assert calls, "liveness must resolve ingestion.jobs.sync_session dynamically"
    assert counts == {"queued_stale": 0, "lease_expired": 0, "legacy_running": 0}


def test_heartbeat_resolves_extend_lease_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default heartbeat extend path must not bind sync_extend_lease at import."""
    from ingestion.liveness import JobLeaseHeartbeat

    calls: list[tuple[Any, ...]] = []

    def _tracked_extend(job_id, tenant_id, lease_token):  # noqa: ANN001
        calls.append((job_id, tenant_id, lease_token))
        return True

    monkeypatch.setattr(jobs_mod, "sync_extend_lease", _tracked_extend)
    jid = uuid.uuid4()
    hb = JobLeaseHeartbeat(
        job_id=jid,
        tenant_id="late-ext",
        lease_token="tok-late",
        interval_sec=30,
    )
    assert hb.tick_once() is True
    assert calls == [(jid, "late-ext", "tok-late")]


# ---------------------------------------------------------------------------
# Reaper selection matrix + idempotence + secret-free logs
# ---------------------------------------------------------------------------


def test_reaper_selection_matrix(ingestion_jobs_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from ingestion import liveness as live_mod

    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "300")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "900")
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")

    now = _utc()

    stale_queued = _seed(
        status="queued",
        celery_task_id="c-stale-q",
        created_at=now - timedelta(seconds=400),
        tenant_id="m",
    )
    fresh_queued = _seed(
        status="queued",
        celery_task_id="c-fresh-q",
        created_at=now - timedelta(seconds=10),
        tenant_id="m",
    )
    active_lease = _seed(
        status="running",
        celery_task_id="c-active",
        started_at=now - timedelta(seconds=20),
        lease_token="active-tok",
        heartbeat_at=now - timedelta(seconds=10),
        lease_expires_at=now + timedelta(seconds=100),
        tenant_id="m",
    )
    expired_lease = _seed(
        status="running",
        celery_task_id="c-expired",
        started_at=now - timedelta(seconds=200),
        lease_token="expired-tok",
        heartbeat_at=now - timedelta(seconds=200),
        lease_expires_at=now - timedelta(seconds=5),
        tenant_id="m",
    )
    terminal_completed = _seed(
        status="completed",
        celery_task_id="c-done",
        started_at=now - timedelta(seconds=500),
        finished_at=now - timedelta(seconds=400),
        tenant_id="m",
    )
    terminal_failed = _seed(
        status="failed",
        celery_task_id="c-fail",
        started_at=now - timedelta(seconds=500),
        finished_at=now - timedelta(seconds=400),
        error="prior",
        tenant_id="m",
    )
    # Synchronous upload: no celery_task_id — never reaped even if old.
    sync_running = _seed(
        status="running",
        celery_task_id=None,
        started_at=now - timedelta(seconds=10_000),
        lease_token=None,
        tenant_id="m",
    )
    sync_queued = _seed(
        status="queued",
        celery_task_id=None,
        created_at=now - timedelta(seconds=10_000),
        tenant_id="m",
    )
    legacy_stale = _seed(
        status="running",
        celery_task_id="c-legacy",
        started_at=now - timedelta(seconds=1200),
        lease_token=None,
        lease_expires_at=None,
        heartbeat_at=None,
        tenant_id="m",
    )
    legacy_fresh = _seed(
        status="running",
        celery_task_id="c-legacy-fresh",
        started_at=now - timedelta(seconds=60),
        lease_token=None,
        tenant_id="m",
    )

    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["queued_stale"] >= 1
    assert counts["lease_expired"] >= 1
    assert counts["legacy_running"] >= 1

    assert _get(stale_queued).status == "failed"
    assert _get(fresh_queued).status == "queued"
    assert _get(active_lease).status == "running"
    assert _get(active_lease).lease_token == "active-tok"
    assert _get(expired_lease).status == "failed"
    assert _get(expired_lease).lease_token is None
    assert _get(terminal_completed).status == "completed"
    assert _get(terminal_failed).status == "failed"
    assert _get(terminal_failed).error == "prior"
    assert _get(sync_running).status == "running"
    assert _get(sync_queued).status == "queued"
    assert _get(legacy_stale).status == "failed"
    assert _get(legacy_fresh).status == "running"

    # Phase-level errors only
    for jid in (stale_queued, expired_lease, legacy_stale):
        err = _get(jid).error or ""
        assert err
        assert "traceback" not in err.lower()
        assert "postgresql" not in err.lower()

    # Reaper clears token/expiry but preserves last successful heartbeat.
    expired_row = _get(expired_lease)
    assert expired_row.lease_token is None
    assert expired_row.lease_expires_at is None
    assert expired_row.heartbeat_at is not None


def test_reaper_boundary_inclusive_at_exact_cutoff(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Jobs exactly at the stale/expiry cutoff must be reaped (``<=``)."""
    from ingestion import liveness as live_mod

    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "300")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "900")

    now = _utc()
    queued_exact = _seed(
        status="queued",
        celery_task_id="c-q-exact",
        created_at=now - timedelta(seconds=300),
        tenant_id="boundary",
    )
    lease_exact = _seed(
        status="running",
        celery_task_id="c-e-exact",
        started_at=now - timedelta(seconds=200),
        lease_token="boundary-tok",
        heartbeat_at=now - timedelta(seconds=120),
        lease_expires_at=now,
        tenant_id="boundary",
    )
    legacy_exact = _seed(
        status="running",
        celery_task_id="c-l-exact",
        started_at=now - timedelta(seconds=900),
        lease_token=None,
        tenant_id="boundary",
    )

    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["queued_stale"] >= 1
    assert counts["lease_expired"] >= 1
    assert counts["legacy_running"] >= 1
    assert _get(queued_exact).status == "failed"
    assert _get(lease_exact).status == "failed"
    assert _get(legacy_exact).status == "failed"
    # Observability: last heartbeat kept; active ownership cleared.
    assert _get(lease_exact).heartbeat_at is not None
    assert _get(lease_exact).lease_token is None
    assert _get(lease_exact).lease_expires_at is None


def test_reaper_idempotent_and_logs_aggregates_only(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ingestion import liveness as live_mod

    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "60")
    now = _utc()
    jid = _seed(
        status="queued",
        celery_task_id="c-idem",
        created_at=now - timedelta(seconds=120),
        tenant_id="secret-tenant",
        filename="secret-file.txt",
    )
    # Plant a token that must never appear in reaper logs
    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, jid)
        assert row is not None
        row.lease_token = "lease-secret-token-value"
        session.commit()

    with caplog.at_level(logging.INFO, logger="ingestion.liveness"):
        c1 = live_mod.reap_stale_jobs(now=now)
        c2 = live_mod.reap_stale_jobs(now=now)

    assert c1["queued_stale"] >= 1
    assert c2["queued_stale"] == 0
    assert _get(jid).status == "failed"

    joined = " ".join(r.getMessage() for r in caplog.records)
    for banned in (
        "secret-tenant",
        "secret-file.txt",
        "lease-secret-token-value",
        "data/uploads",
    ):
        assert banned not in joined


# ---------------------------------------------------------------------------
# Background heartbeat without real sleeps
# ---------------------------------------------------------------------------


def test_background_heartbeat_success_and_loss_without_sleep(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ingestion.liveness import JobLeaseHeartbeat

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    jid = _seed(status="queued", tenant_id="hb", celery_task_id="c-hb2")
    token = jobs_mod.sync_claim_running(jid, "hb")

    sleeps: list[float] = []

    def _fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        # Deterministic seam: record requested interval, no real wait/busy loop.

    hb = JobLeaseHeartbeat(
        job_id=jid,
        tenant_id="hb",
        lease_token=token,
        interval_sec=30,
        sleeper=_fake_sleep,
    )
    # Direct tick path — no thread sleep required.
    assert hb.tick_once() is True
    assert hb.ownership_lost is False
    mid = _get(jid)
    assert mid.lease_token == token

    # Lose ownership
    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, jid)
        assert row is not None
        row.lease_token = "other"
        session.commit()

    assert hb.tick_once() is False
    assert hb.ownership_lost is True


def test_heartbeat_stop_leaves_no_live_thread() -> None:
    """stop() must interrupt the wait and join the daemon promptly."""
    from ingestion.liveness import JobLeaseHeartbeat

    extensions = {"n": 0}

    def _extend(*_a, **_k) -> bool:
        extensions["n"] += 1
        return True

    hb = JobLeaseHeartbeat(
        job_id=uuid.uuid4(),
        tenant_id="stop-t",
        lease_token="stop-tok",
        interval_sec=30.0,
        extend_fn=_extend,
    )
    hb.start()
    thread = hb._thread
    assert thread is not None
    assert thread.is_alive()
    # Give the loop a moment to enter Event.wait.
    threading.Event().wait(0.05)
    hb.stop()
    assert not thread.is_alive(), "heartbeat daemon must not survive stop()"
    assert hb._thread is None


def test_heartbeat_failure_logs_redacted_phase_only(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ingestion.liveness import JobLeaseHeartbeat

    jid = uuid.uuid4()

    def _boom_extend(*_a, **_k):
        raise RuntimeError(
            "db fail postgresql://user:db-password@host/db "
            "token=lease-secret-token-value support@example.com"
        )

    hb = JobLeaseHeartbeat(
        job_id=jid,
        tenant_id="t",
        lease_token="lease-secret-token-value",
        interval_sec=30,
        extend_fn=_boom_extend,
    )
    with caplog.at_level(logging.WARNING, logger="ingestion.liveness"):
        assert hb.tick_once() is False
        assert hb.ownership_lost is True

    joined = " ".join(r.getMessage() for r in caplog.records)
    _assert_no_secret_leak(joined)
    assert "traceback" not in joined.lower()
    # Type-only / phase-level signal
    assert "heartbeat" in joined.lower() or "lease" in joined.lower()


# ---------------------------------------------------------------------------
# Worker refuses duplicate / lost lease before unsafe work
# ---------------------------------------------------------------------------


def test_worker_refuses_duplicate_claim_before_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from tasks import ingest_task

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed(job_id=job_id, status="queued", tenant_id="w", celery_task_id="c-w")

    # Pre-claim as another worker
    jobs_mod.sync_claim_running(job_id, "w")

    load_calls: list[str] = []
    build_calls: list[Any] = []

    class TrackingLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            load_calls.append(path)
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", TrackingLoader)
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda *a, **k: build_calls.append(1),
    )
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with pytest.raises(Exception):
        ingest_task.ingest_document.run(str(upload), str(job_id), "w")

    assert load_calls == []
    assert build_calls == []
    assert _get(job_id).status == "running"  # first claim still owns


def test_worker_lost_lease_cannot_overwrite_reaper_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingestion_jobs_db,
) -> None:
    from tasks import ingest_task

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    _seed(job_id=job_id, status="queued", tenant_id="lost", celery_task_id="c-lost")

    real_claim = jobs_mod.sync_claim_running

    def _claim_then_reap(jid, tenant):
        token = real_claim(jid, tenant)
        # Reaper takes over after claim, before/during work
        with jobs_mod.sync_session() as session:
            row = session.get(IngestionJob, jid)
            assert row is not None
            row.status = "failed"
            row.error = "Ingestion job lease expired"
            row.finished_at = _utc()
            row.lease_token = None
            row.lease_expires_at = None
            row.heartbeat_at = None
            session.commit()
        return token

    class FakeLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr(jobs_mod, "sync_claim_running", _claim_then_reap)
    # Worker imports from ingestion.jobs inside the task — patch module path used
    monkeypatch.setattr("ingestion.jobs.sync_claim_running", _claim_then_reap)
    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda *a, **k: None,
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

    with pytest.raises(Exception):
        ingest_task.ingest_document.run(str(upload), str(job_id), "lost")

    row = _get(job_id)
    assert row.status == "failed"
    assert row.error == "Ingestion job lease expired"
    assert row.result is None


# ---------------------------------------------------------------------------
# Periodic app reaper loop
# ---------------------------------------------------------------------------


def test_reaper_loop_initial_sweep_survives_db_error_repeats_and_cancels(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ingestion import liveness as live_mod

    calls: list[str] = []
    sleeps: list[float] = []
    stop = asyncio.Event()

    def _reaper():
        calls.append("reap")
        if len(calls) == 1:
            raise RuntimeError(
                "connection failed postgresql://user:db-password@host/db "
                "token=lease-secret-token-value"
            )
        if len(calls) >= 3:
            stop.set()
        return {"queued_stale": 0, "lease_expired": 1, "legacy_running": 0}

    async def _sleeper(sec: float) -> None:
        sleeps.append(sec)
        if stop.is_set():
            raise asyncio.CancelledError
        # Second sleep: cancel after allowing another iteration setup
        if len(sleeps) >= 2:
            stop.set()
            raise asyncio.CancelledError

    with caplog.at_level(logging.WARNING, logger="ingestion.liveness"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(
                live_mod.ingestion_reaper_loop(
                    interval_sec=5,
                    reaper_fn=_reaper,
                    sleeper=_sleeper,
                )
            )

    # Initial sweep ran immediately (before first sleep)
    assert len(calls) >= 2
    assert sleeps  # waited between sweeps
    joined = " ".join(r.getMessage() for r in caplog.records)
    _assert_no_secret_leak(joined)
    assert "db-password" not in joined
    assert "RuntimeError" in joined or "error_type" in joined or "failed" in joined.lower()


def test_reaper_loop_runs_sync_work_off_event_loop_thread() -> None:
    """Synchronous reaper body must not run on the FastAPI event-loop thread."""
    from ingestion import liveness as live_mod

    loop_tid: dict[str, int] = {}
    reaper_tids: list[int] = []

    def _reaper() -> dict[str, int]:
        reaper_tids.append(threading.get_ident())
        return {"queued_stale": 0, "lease_expired": 0, "legacy_running": 0}

    async def _sleeper(_sec: float) -> None:
        raise asyncio.CancelledError

    async def _run() -> None:
        loop_tid["id"] = threading.get_ident()
        with pytest.raises(asyncio.CancelledError):
            await live_mod.ingestion_reaper_loop(
                interval_sec=1,
                reaper_fn=_reaper,
                sleeper=_sleeper,
            )

    asyncio.run(_run())
    assert reaper_tids, "reaper must run at least once"
    assert loop_tid["id"] not in reaper_tids


def test_reaper_loop_supports_async_injected_callable() -> None:
    from ingestion import liveness as live_mod

    calls: list[str] = []

    async def _async_reaper() -> dict[str, int]:
        calls.append("async")
        return {"queued_stale": 0, "lease_expired": 0, "legacy_running": 0}

    async def _sleeper(_sec: float) -> None:
        raise asyncio.CancelledError

    async def _run() -> None:
        with pytest.raises(asyncio.CancelledError):
            await live_mod.ingestion_reaper_loop(
                interval_sec=1,
                reaper_fn=_async_reaper,
                sleeper=_sleeper,
            )

    asyncio.run(_run())
    assert calls == ["async"]


def test_app_lifespan_wires_ingestion_reaper() -> None:
    src = (PROJECT_ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "ingestion_reaper_loop" in src
    assert "create_task" in src
    # Shutdown must cancel and await the reaper task (no pending-task warning).
    assert "ingestion_reaper_task.cancel()" in src
    assert "await ingestion_reaper_task" in src
    # Fail-closed: lifespan must not silently clamp reaper interval with max(1, ...).
    reaper_block = src[src.index("_reap_stale_ingestion_jobs_periodically") :]
    reaper_block = reaper_block[: reaper_block.index("cleanup_task")]
    assert "max(" not in reaper_block


# ---------------------------------------------------------------------------
# Runtime config accessors (worker fail-closed; no silent clamp)
# ---------------------------------------------------------------------------


def _clear_liveness_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "INGESTION_JOB_LEASE_SEC",
        "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        "INGESTION_JOB_QUEUED_STALE_SEC",
        "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
        "INGESTION_JOB_REAPER_INTERVAL_SEC",
    ):
        monkeypatch.delenv(var, raising=False)


def _set_valid_liveness_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "900")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")
    monkeypatch.setenv("INGESTION_JOB_REAPER_INTERVAL_SEC", "60")


def test_runtime_accessors_reject_zero_negative_and_non_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker-side accessors must fail closed — never max(1, ...) or ignore bad env."""
    from ingestion import liveness as live_mod

    accessors = (
        ("INGESTION_JOB_LEASE_SEC", live_mod.lease_duration_sec, "INGESTION_JOB_LEASE_SEC"),
        (
            "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
            live_mod.heartbeat_interval_sec,
            "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        ),
        (
            "INGESTION_JOB_QUEUED_STALE_SEC",
            live_mod.queued_stale_sec,
            "INGESTION_JOB_QUEUED_STALE_SEC",
        ),
        (
            "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
            live_mod.legacy_running_stale_sec,
            "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
        ),
        (
            "INGESTION_JOB_REAPER_INTERVAL_SEC",
            live_mod.reaper_interval_sec,
            "INGESTION_JOB_REAPER_INTERVAL_SEC",
        ),
    )

    for env_name, accessor, setting_token in accessors:
        for bad in ("0", "-1", "-30"):
            _set_valid_liveness_env(monkeypatch)
            monkeypatch.setenv(env_name, bad)
            with pytest.raises(RuntimeError) as ei:
                accessor()
            msg = str(ei.value)
            assert setting_token in msg
            # Never echo the raw configured value (may look like a secret).
            assert bad not in msg
            assert "sk-" not in msg.lower()

        _set_valid_liveness_env(monkeypatch)
        monkeypatch.setenv(env_name, "not-an-int")
        with pytest.raises(RuntimeError) as ei:
            accessor()
        msg = str(ei.value)
        assert setting_token in msg
        assert "not-an-int" not in msg


@pytest.mark.parametrize(
    "env_name,accessor_attr",
    [
        ("INGESTION_JOB_LEASE_SEC", "lease_duration_sec"),
        ("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "heartbeat_interval_sec"),
        ("INGESTION_JOB_QUEUED_STALE_SEC", "queued_stale_sec"),
        ("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "legacy_running_stale_sec"),
        ("INGESTION_JOB_REAPER_INTERVAL_SEC", "reaper_interval_sec"),
    ],
)
@pytest.mark.parametrize("blank", ("", " ", "\t", "\n", "  \t\n  "))
def test_runtime_accessors_reject_explicit_blank_env(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    accessor_attr: str,
    blank: str,
) -> None:
    """Explicit blank/whitespace env is authoritative — fail closed, never default.

    API Settings() rejects blank via int(''); worker _settings_int must match and
    must not treat whitespace as absent (which silently fell back to 120).
    """
    from ingestion import liveness as live_mod

    _set_valid_liveness_env(monkeypatch)
    monkeypatch.setenv(env_name, blank)
    accessor = getattr(live_mod, accessor_attr)
    with pytest.raises(RuntimeError) as ei:
        accessor()
    msg = str(ei.value)
    assert env_name in msg
    assert "positive integer" in msg
    # Fixed template only — never echo arbitrary raw configured text.
    assert msg == f"Invalid runtime config: {env_name} must be a positive integer"


def test_runtime_accessors_reject_heartbeat_ge_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ingestion import liveness as live_mod

    _set_valid_liveness_env(monkeypatch)
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "30")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")
    with pytest.raises(RuntimeError) as ei:
        live_mod.heartbeat_interval_sec()
    msg = str(ei.value)
    assert "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC" in msg
    assert "INGESTION_JOB_LEASE_SEC" in msg
    assert "30" not in msg  # no raw values

    # Equal is invalid; greater is also invalid.
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "60")
    with pytest.raises(RuntimeError) as ei2:
        live_mod.lease_duration_sec()
    msg2 = str(ei2.value)
    assert "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC" in msg2
    assert "60" not in msg2


def test_invalid_runtime_config_blocks_claim_before_leaving_queued(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Celery-style claim must not leave queued when lease/heartbeat config is invalid."""
    from ingestion import liveness as live_mod

    _set_valid_liveness_env(monkeypatch)
    jid = _seed(status="queued", tenant_id="cfg-tenant", celery_task_id="c-cfg")

    # Zero lease: fail closed before CAS update.
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "0")
    with pytest.raises(RuntimeError) as ei:
        jobs_mod.sync_claim_running(jid, "cfg-tenant")
    assert "INGESTION_JOB_LEASE_SEC" in str(ei.value)
    row = _get(jid)
    assert row.status == "queued"
    assert row.lease_token is None
    assert row.started_at is None

    # Non-integer lease env: same fail-closed contract.
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "twelve")
    with pytest.raises(RuntimeError):
        jobs_mod.sync_claim_running(jid, "cfg-tenant")
    assert _get(jid).status == "queued"

    # Heartbeat >= lease: claim must refuse before ownership moves.
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "30")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")
    with pytest.raises(RuntimeError) as ei_hb:
        jobs_mod.sync_claim_running(jid, "cfg-tenant")
    assert "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC" in str(ei_hb.value)
    assert _get(jid).status == "queued"
    assert _get(jid).lease_token is None

    # jobs and liveness share one validated path (same failure mode).
    with pytest.raises(RuntimeError):
        live_mod.lease_duration_sec()


def test_invalid_lease_config_blocks_celery_task_before_load(
    tmp_path,
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingest task must not load/index when runtime lease config is invalid."""
    from tasks import ingest_task

    _set_valid_liveness_env(monkeypatch)
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "-5")

    job_id = uuid.uuid4()
    upload = tmp_path / "doc.txt"
    upload.write_text("hello world", encoding="utf-8")
    _seed(
        status="queued",
        tenant_id="w-cfg",
        celery_task_id="c-w-cfg",
        job_id=job_id,
        filename="doc.txt",
    )

    load_calls: list[str] = []
    index_calls: list[str] = []

    class TrackingLoader:
        def __init__(self, recursive: bool = False) -> None:
            pass

        def load_documents(self, path: str):  # noqa: ANN001
            load_calls.append(path)
            return [SimpleNamespace(page_content="x", metadata={})]

    def _build(*_a, **_k):  # noqa: ANN001
        index_calls.append("build")
        return None

    monkeypatch.setattr("ingestion.loader.DocumentLoader", TrackingLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr("vectordb.manager.build_vector_store", _build)
    monkeypatch.setattr(
        ingest_task.ingest_document,
        "update_state",
        lambda **kwargs: None,
    )

    with pytest.raises(RuntimeError):
        ingest_task.ingest_document.run(str(upload), str(job_id), "w-cfg")

    row = _get(job_id)
    assert row.status == "queued"
    assert row.lease_token is None
    assert load_calls == []
    assert index_calls == []


def test_reaper_clears_stale_result_on_recovery(
    ingestion_jobs_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery failure must not leave a stale result on a terminal failed row."""
    from ingestion import liveness as live_mod

    _set_valid_liveness_env(monkeypatch)
    now = _utc()
    jid = _seed(
        status="running",
        tenant_id="stale-res",
        celery_task_id="c-stale-res",
        started_at=now - timedelta(seconds=200),
        lease_token="old-tok",
        heartbeat_at=now - timedelta(seconds=200),
        lease_expires_at=now - timedelta(seconds=10),
    )
    # Simulate inconsistent state: result payload coexists with a running row.
    with jobs_mod.sync_session() as session:
        row = session.get(IngestionJob, jid)
        assert row is not None
        row.result = {"status": "ok", "docs_count": 1, "stale": True}
        session.commit()

    assert _get(jid).result is not None
    counts = live_mod.reap_stale_jobs(now=now)
    assert counts["lease_expired"] >= 1
    final = _get(jid)
    assert final.status == "failed"
    assert final.lease_token is None
    assert final.result is None


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def test_settings_liveness_defaults_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import Settings

    for var in (
        "INGESTION_JOB_LEASE_SEC",
        "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        "INGESTION_JOB_QUEUED_STALE_SEC",
        "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
        "INGESTION_JOB_REAPER_INTERVAL_SEC",
    ):
        monkeypatch.delenv(var, raising=False)

    s = Settings()
    assert s.ingestion_job_lease_sec == 120
    assert s.ingestion_job_heartbeat_interval_sec == 30
    assert s.ingestion_job_queued_stale_sec > 0
    assert s.ingestion_job_legacy_running_stale_sec > 0
    assert s.ingestion_job_reaper_interval_sec > 0
    assert s.ingestion_job_heartbeat_interval_sec < s.ingestion_job_lease_sec

    # Heartbeat must be positive and strictly shorter than lease
    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "30")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")
    bad = Settings()
    with pytest.raises(RuntimeError):
        bad.validate()

    monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
    monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "0")
    bad2 = Settings()
    with pytest.raises(RuntimeError):
        bad2.validate()


def test_settings_liveness_rejects_zero_and_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid zeros/negatives must reach validate() — no silent max(1, ...) clamp."""
    from config.settings import Settings

    def _set_good_defaults() -> None:
        monkeypatch.setenv("INGESTION_JOB_LEASE_SEC", "120")
        monkeypatch.setenv("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "30")
        monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "900")
        monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")
        monkeypatch.setenv("INGESTION_JOB_REAPER_INTERVAL_SEC", "60")

    cases = (
        ("INGESTION_JOB_LEASE_SEC", "0"),
        ("INGESTION_JOB_LEASE_SEC", "-5"),
        ("INGESTION_JOB_HEARTBEAT_INTERVAL_SEC", "-1"),
        ("INGESTION_JOB_QUEUED_STALE_SEC", "0"),
        ("INGESTION_JOB_QUEUED_STALE_SEC", "-10"),
        ("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "0"),
        ("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "-1"),
        ("INGESTION_JOB_REAPER_INTERVAL_SEC", "0"),
        ("INGESTION_JOB_REAPER_INTERVAL_SEC", "-2"),
    )
    for env_name, bad_value in cases:
        _set_good_defaults()
        monkeypatch.setenv(env_name, bad_value)
        cfg = Settings()
        # Factories must preserve the invalid value (not clamp to 1).
        attr = {
            "INGESTION_JOB_LEASE_SEC": "ingestion_job_lease_sec",
            "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC": "ingestion_job_heartbeat_interval_sec",
            "INGESTION_JOB_QUEUED_STALE_SEC": "ingestion_job_queued_stale_sec",
            "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC": "ingestion_job_legacy_running_stale_sec",
            "INGESTION_JOB_REAPER_INTERVAL_SEC": "ingestion_job_reaper_interval_sec",
        }[env_name]
        assert getattr(cfg, attr) == int(bad_value)
        with pytest.raises(RuntimeError):
            cfg.validate()


def test_async_sync_upload_helpers_work_without_lease(
    ingestion_jobs_db,
) -> None:
    """Synchronous upload path uses async helpers; reaper must not target them."""
    import asyncio

    async def _run() -> uuid.UUID:
        job = await jobs_mod.create_ingestion_job(
            tenant_id="sync-tenant",
            filename="s.txt",
            source_path="data/uploads/s.txt",
        )
        assert job.celery_task_id is None
        running = await jobs_mod.mark_job_running(job.id, "sync-tenant")
        assert running is not None
        assert running.status == "running"
        assert running.lease_token is None
        done = await jobs_mod.mark_job_completed(
            job.id,
            "sync-tenant",
            result={"status": "ok"},
        )
        assert done is not None
        assert done.status == "completed"
        return job.id

    jid = asyncio.run(_run())
    row = _get(jid)
    assert row.lease_token is None
    assert row.celery_task_id is None


def test_env_example_and_config_docs_list_liveness_settings() -> None:
    env = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    docs = (PROJECT_ROOT / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    for key in (
        "INGESTION_JOB_LEASE_SEC",
        "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        "INGESTION_JOB_QUEUED_STALE_SEC",
        "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
        "INGESTION_JOB_REAPER_INTERVAL_SEC",
    ):
        assert key in env, key
        assert key in docs, key

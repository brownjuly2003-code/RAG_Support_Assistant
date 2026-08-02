"""Ingestion job lease heartbeat and independent stale-job reaper.

Worker heartbeats keep a running lease alive during long load/embed/index work.
The reaper runs in the FastAPI process so a dead Celery worker still becomes an
observable terminal failure. Only asynchronous jobs (celery_task_id present)
are reaped — synchronous upload rows are never targeted.

ING-02 (atomic index publish) remains open: heartbeats do not make delete-then-
build vector mutation atomic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, update

from db.models import IngestionJob

logger = logging.getLogger(__name__)

_DEFAULT_LEASE_SEC = 120
_DEFAULT_HEARTBEAT_SEC = 30
_DEFAULT_QUEUED_STALE_SEC = 900
_DEFAULT_LEGACY_RUNNING_STALE_SEC = 1800
_DEFAULT_REAPER_INTERVAL_SEC = 60

# Phase-level terminal messages only (no raw exceptions/secrets).
_MSG_QUEUED_STALE = "Ingestion job timed out while queued"
_MSG_LEASE_EXPIRED = "Ingestion job lease expired"
_MSG_LEGACY_RUNNING = "Ingestion job abandoned (stale running without lease)"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _settings_int(attr: str, env_name: str, default: int) -> int:
    """Read a positive integer runtime setting; fail closed on invalid values.

    Prefer live env so tests can monkeypatch without clearing get_settings cache.
    Any present env value is authoritative (including blank/whitespace) and must
    parse as a positive integer — only a genuinely absent env may consult
    settings/defaults. Error messages name the setting only — never echo the
    raw configured value.
    """
    raw = os.getenv(env_name)
    if raw is not None:
        try:
            value = int(str(raw).strip())
        except ValueError:
            raise RuntimeError(
                f"Invalid runtime config: {env_name} must be a positive integer"
            ) from None
        if value <= 0:
            raise RuntimeError(
                f"Invalid runtime config: {env_name} must be a positive integer"
            )
        return value
    try:
        from config.settings import get_settings

        configured = getattr(get_settings(), attr, None)
        if configured is not None:
            try:
                parsed = int(configured)
            except (TypeError, ValueError):
                raise RuntimeError(
                    f"Invalid runtime config: {env_name} must be a positive integer"
                ) from None
            if parsed <= 0:
                raise RuntimeError(
                    f"Invalid runtime config: {env_name} must be a positive integer"
                )
            return parsed
    except RuntimeError:
        raise
    except Exception:
        pass
    return default


def _assert_heartbeat_lt_lease(lease_sec: int, heartbeat_sec: int) -> None:
    if heartbeat_sec >= lease_sec:
        raise RuntimeError(
            "Invalid runtime config: INGESTION_JOB_HEARTBEAT_INTERVAL_SEC must be "
            "strictly less than INGESTION_JOB_LEASE_SEC"
        )


def lease_duration_sec() -> int:
    lease = _settings_int(
        "ingestion_job_lease_sec",
        "INGESTION_JOB_LEASE_SEC",
        _DEFAULT_LEASE_SEC,
    )
    heartbeat = _settings_int(
        "ingestion_job_heartbeat_interval_sec",
        "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        _DEFAULT_HEARTBEAT_SEC,
    )
    _assert_heartbeat_lt_lease(lease, heartbeat)
    return lease


def heartbeat_interval_sec() -> int:
    heartbeat = _settings_int(
        "ingestion_job_heartbeat_interval_sec",
        "INGESTION_JOB_HEARTBEAT_INTERVAL_SEC",
        _DEFAULT_HEARTBEAT_SEC,
    )
    lease = _settings_int(
        "ingestion_job_lease_sec",
        "INGESTION_JOB_LEASE_SEC",
        _DEFAULT_LEASE_SEC,
    )
    _assert_heartbeat_lt_lease(lease, heartbeat)
    return heartbeat


def queued_stale_sec() -> int:
    return _settings_int(
        "ingestion_job_queued_stale_sec",
        "INGESTION_JOB_QUEUED_STALE_SEC",
        _DEFAULT_QUEUED_STALE_SEC,
    )


def legacy_running_stale_sec() -> int:
    return _settings_int(
        "ingestion_job_legacy_running_stale_sec",
        "INGESTION_JOB_LEGACY_RUNNING_STALE_SEC",
        _DEFAULT_LEGACY_RUNNING_STALE_SEC,
    )


def reaper_interval_sec() -> int:
    return _settings_int(
        "ingestion_job_reaper_interval_sec",
        "INGESTION_JOB_REAPER_INTERVAL_SEC",
        _DEFAULT_REAPER_INTERVAL_SEC,
    )


def _jobs_sync_session() -> Any:
    """Resolve sync_session late so fixture monkeypatches always apply.

    Import-time binding of ``ingestion.jobs.sync_session`` pins the previous
    temporary DB after ``ingestion_jobs_db`` rotates the factory.
    """
    from ingestion import jobs as jobs_mod

    return jobs_mod.sync_session()


def _jobs_sync_extend_lease(job_id: UUID, tenant_id: str, lease_token: str) -> bool:
    """Resolve sync_extend_lease late (same import-order contract as session)."""
    from ingestion import jobs as jobs_mod

    return jobs_mod.sync_extend_lease(job_id, tenant_id, lease_token)


class JobLeaseHeartbeat:
    """Bounded background (or tickable) lease extension for long ingestion work.

    Tests should call ``tick_once`` — do not rely on real sleeps.
    Production wait is interruptible via ``threading.Event`` so ``stop()``
    does not wait out a full heartbeat interval.
    """

    def __init__(
        self,
        *,
        job_id: UUID,
        tenant_id: str,
        lease_token: str,
        interval_sec: float | None = None,
        extend_fn: Callable[[UUID, str, str], bool] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.lease_token = lease_token
        self.interval_sec = float(
            interval_sec if interval_sec is not None else heartbeat_interval_sec()
        )
        # None means resolve ingestion.jobs.sync_extend_lease on each tick.
        self._extend_fn = extend_fn
        self._sleeper = sleeper
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ownership_lost = False

    def tick_once(self) -> bool:
        """Extend once. False means ownership lost or persistence failed."""
        if self.ownership_lost:
            return False
        extend = self._extend_fn or _jobs_sync_extend_lease
        try:
            ok = bool(extend(self.job_id, self.tenant_id, self.lease_token))
        except Exception as exc:
            # Redacted: phase/type only — never token, URL, or exception message.
            logger.warning(
                "Ingestion lease heartbeat failed phase=heartbeat error_type=%s",
                type(exc).__name__,
            )
            self.ownership_lost = True
            return False
        if not ok:
            logger.warning(
                "Ingestion lease ownership lost phase=heartbeat",
            )
            self.ownership_lost = True
            return False
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self.ownership_lost = False

        def _loop() -> None:
            while not self._stop.is_set():
                if self._sleeper is not None:
                    # Deterministic test seam — must not busy-loop; caller
                    # provides a blocking or immediately-returning sleeper.
                    self._sleeper(self.interval_sec)
                else:
                    # Interruptible wait: stop() wakes without full interval.
                    if self._stop.wait(timeout=self.interval_sec):
                        break
                if self._stop.is_set():
                    break
                if not self.tick_once():
                    break

        self._thread = threading.Thread(
            target=_loop,
            name="ingestion-lease-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            # Event.wait is interruptible; join should be near-immediate.
            thread.join(timeout=min(2.0, max(0.5, self.interval_sec + 0.25)))

    def __enter__(self) -> JobLeaseHeartbeat:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def _clear_lease_values(now: datetime, error: str) -> dict[str, Any]:
    """Terminal recovery values: clear active ownership, keep last heartbeat.

    ``heartbeat_at`` is preserved so operators can see the last successful
    lease extension. The opaque token, active expiry, and any stale ``result``
    payload are always cleared so a recovered failure cannot look completed.
    """
    return {
        "status": "failed",
        "error": error,
        "finished_at": now,
        "lease_token": None,
        "lease_expires_at": None,
        "result": None,
    }


def reap_stale_jobs(*, now: datetime | None = None) -> dict[str, int]:
    """Reap stale async ingestion jobs. Returns aggregate counts only.

    Race-safe: conditional updates lose to concurrent claim/heartbeat/terminal.
    Boundary-inclusive: rows at the exact stale/expiry cutoff are reaped (``<=``).
    """
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    q_cutoff = now - timedelta(seconds=queued_stale_sec())
    legacy_cutoff = now - timedelta(seconds=legacy_running_stale_sec())

    counts = {
        "queued_stale": 0,
        "lease_expired": 0,
        "legacy_running": 0,
    }

    with _jobs_sync_session() as session:
        # 1) Stale queued async jobs (never claimed). Inclusive at exact cutoff.
        res_q = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.status == "queued",
                IngestionJob.celery_task_id.isnot(None),
                IngestionJob.created_at <= q_cutoff,
            )
            .values(**_clear_lease_values(now, _MSG_QUEUED_STALE))
        )
        counts["queued_stale"] = int(getattr(res_q, "rowcount", 0) or 0)

        # 2) Running async jobs with expired lease (inclusive at exact expiry).
        res_e = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.status == "running",
                IngestionJob.celery_task_id.isnot(None),
                IngestionJob.lease_token.isnot(None),
                IngestionJob.lease_expires_at.isnot(None),
                IngestionJob.lease_expires_at <= now,
            )
            .values(**_clear_lease_values(now, _MSG_LEASE_EXPIRED))
        )
        counts["lease_expired"] = int(getattr(res_e, "rowcount", 0) or 0)

        # 3) Legacy async running rows without a lease (pre-4.3 workers).
        res_l = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.status == "running",
                IngestionJob.celery_task_id.isnot(None),
                IngestionJob.lease_token.is_(None),
                or_(
                    and_(
                        IngestionJob.started_at.isnot(None),
                        IngestionJob.started_at <= legacy_cutoff,
                    ),
                    and_(
                        IngestionJob.started_at.is_(None),
                        IngestionJob.created_at <= legacy_cutoff,
                    ),
                ),
            )
            .values(**_clear_lease_values(now, _MSG_LEGACY_RUNNING))
        )
        counts["legacy_running"] = int(getattr(res_l, "rowcount", 0) or 0)

        session.commit()

    total = sum(counts.values())
    if total:
        # Aggregate counts only — no tenant/filename/path/token/error payload.
        logger.info(
            "Ingestion reaper sweep queued_stale=%d lease_expired=%d legacy_running=%d",
            counts["queued_stale"],
            counts["lease_expired"],
            counts["legacy_running"],
        )
    return counts


async def _invoke_reaper(
    reaper: Callable[[], Any],
) -> None:
    """Run reaper work without blocking the event loop for sync SQLAlchemy."""
    if asyncio.iscoroutinefunction(reaper):
        await reaper()  # type: ignore[misc]
        return
    # Production default and sync injectables: off the event-loop thread.
    await asyncio.to_thread(reaper)


async def ingestion_reaper_loop(
    *,
    interval_sec: float | None = None,
    reaper_fn: Callable[[], Any] | None = None,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    """Periodic reaper: initial sweep promptly, then sleep; cancel cleanly."""
    interval = float(interval_sec if interval_sec is not None else reaper_interval_sec())
    if interval <= 0:
        interval = float(_DEFAULT_REAPER_INTERVAL_SEC)
    reaper: Callable[[], Any] = reaper_fn or reap_stale_jobs
    sleep = sleeper or asyncio.sleep

    while True:
        try:
            await _invoke_reaper(reaper)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log exception message (may contain DSN/secrets).
            logger.warning(
                "Ingestion reaper sweep failed error_type=%s",
                type(exc).__name__,
            )
        try:
            await sleep(interval)
        except asyncio.CancelledError:
            raise

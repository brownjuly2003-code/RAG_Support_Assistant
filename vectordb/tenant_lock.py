"""PostgreSQL advisory lock for tenant-scoped index mutation."""
from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

from config.settings import get_settings

logger = logging.getLogger(__name__)

_LOCK_DOMAIN = b"rag-support:index-rebuild:v1\0"
_POLL_INTERVAL_SEC = 0.1
_TOKEN_PROOF = object()


class TenantIndexLockError(RuntimeError):
    """Base class for tenant index lock failures."""


class TenantIndexLockTimeout(TenantIndexLockError):
    """Raised when another rebuild keeps the tenant lock past the wait budget."""


class TenantIndexLockUnavailable(TenantIndexLockError):
    """Raised when lock ownership cannot be established or safely released."""


class TenantIndexLockToken:
    """Proof that the caller currently holds one tenant's rebuild lock."""

    __slots__ = ("_active", "_tenant_id")

    def __init__(self, tenant_id: str, proof: object) -> None:
        if proof is not _TOKEN_PROOF:
            raise TypeError("Tenant index lock tokens are created by tenant_index_lock")
        self._tenant_id = str(tenant_id or "default")
        self._active = True

    def _invalidate(self, proof: object) -> None:
        if proof is not _TOKEN_PROOF:
            raise TypeError("Tenant index lock tokens are managed by tenant_index_lock")
        self._active = False


def require_tenant_index_lock(
    lock_token: TenantIndexLockToken | None,
    tenant_id: str,
) -> None:
    """Fail closed unless ``lock_token`` is active for ``tenant_id``."""
    if not isinstance(lock_token, TenantIndexLockToken) or not lock_token._active:
        raise TenantIndexLockUnavailable("A held tenant index lock is required")
    if lock_token._tenant_id != str(tenant_id or "default"):
        raise TenantIndexLockUnavailable(
            "Tenant index lock token belongs to a different tenant"
        )


def _lock_key(tenant_id: str) -> int:
    canonical = str(tenant_id or "default").encode("utf-8")
    digest = hashlib.sha256(_LOCK_DOMAIN + canonical).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _wait_timeout_sec() -> float:
    value = float(getattr(get_settings(), "ingestion_tenant_lock_wait_sec", 30.0))
    if value < 0 or not math.isfinite(value):
        raise RuntimeError(
            "INGESTION_TENANT_LOCK_WAIT_SEC must be a finite float >= 0"
        )
    return value


def _open_lock_connection() -> Any:
    from ingestion.jobs import get_sync_engine  # noqa: PLC0415

    connection = get_sync_engine().connect()
    try:
        return connection.execution_options(isolation_level="AUTOCOMMIT")
    except BaseException:
        connection.close()
        raise


def _acquire(connection: Any, lock_key: int, wait_timeout_sec: float) -> None:
    deadline = time.monotonic() + wait_timeout_sec
    while True:
        try:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": lock_key},
                ).scalar_one()
            )
        except Exception as exc:
            raise TenantIndexLockUnavailable(
                "Tenant index lock service is unavailable"
            ) from exc
        if acquired:
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TenantIndexLockTimeout(
                "An index rebuild is already in progress for this tenant"
            )
        time.sleep(min(_POLL_INTERVAL_SEC, remaining))


def _release(connection: Any, lock_key: int) -> None:
    try:
        released = bool(
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            ).scalar_one()
        )
    except Exception as exc:
        raise TenantIndexLockUnavailable(
            "Tenant index lock service became unavailable during release"
        ) from exc
    if not released:
        raise TenantIndexLockUnavailable("Tenant index lock ownership was lost")


@contextmanager
def tenant_index_lock(tenant_id: str) -> Iterator[TenantIndexLockToken]:
    """Serialize destructive index rebuilds for one canonical tenant ID."""
    lock_key = _lock_key(tenant_id)
    try:
        connection = _open_lock_connection()
    except Exception as exc:
        raise TenantIndexLockUnavailable(
            "Tenant index lock service is unavailable"
        ) from exc

    try:
        _acquire(connection, lock_key, _wait_timeout_sec())
        lock_token = TenantIndexLockToken(tenant_id, _TOKEN_PROOF)
        body_failed = False
        try:
            yield lock_token
        except BaseException:
            body_failed = True
            raise
        finally:
            try:
                _release(connection, lock_key)
            except TenantIndexLockUnavailable as exc:
                if body_failed:
                    logger.error(
                        "Tenant index lock cleanup failed while rebuild was failing "
                        "error_type=%s",
                        type(exc.__cause__ or exc).__name__,
                    )
                else:
                    raise
            finally:
                lock_token._invalidate(_TOKEN_PROOF)
    finally:
        try:
            connection.close()
        except Exception as exc:
            logger.error(
                "Tenant index lock connection close failed error_type=%s",
                type(exc).__name__,
            )

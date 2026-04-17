"""Append-only audit logging."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def log_audit(
    actor: str,
    action: str,
    resource: str,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Append audit record. Fire-and-forget - never blocks request."""
    async def _write_entry() -> None:
        try:
            from db.engine import async_session
            from db.models import AuditLog

            async with async_session() as db:
                entry = AuditLog(
                    actor=actor,
                    action=action,
                    resource=resource,
                    detail=json.dumps(detail, ensure_ascii=False) if detail else None,
                    ip_address=ip_address,
                )
                db.add(entry)
                await asyncio.wait_for(db.commit(), timeout=0.25)
        except Exception as exc:
            logger.warning("Audit DB write failed, logging to file: %s", exc)
            logger.info(
                "AUDIT: actor=%s action=%s resource=%s detail=%s ip=%s",
                actor,
                action,
                resource,
                detail,
                ip_address,
            )

    asyncio.create_task(_write_entry())


async def purge_old_audit(retention_days: int) -> int:
    """Delete audit_log entries older than retention_days and return deleted rows."""
    if retention_days <= 0:
        return 0

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        from sqlalchemy import delete

        from db.engine import async_session
        from db.models import AuditLog

        async with async_session() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.ts < cutoff)
            )
            await db.commit()
            return result.rowcount or 0
    except Exception as exc:
        logger.warning("Audit purge failed: %s", exc)
        return 0

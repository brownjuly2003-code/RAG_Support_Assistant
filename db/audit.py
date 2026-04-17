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

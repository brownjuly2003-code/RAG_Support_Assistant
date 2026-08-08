"""Celery / operator entry for escalation outbox retry (plan §4.6).

Wires ``services.escalation.retry_failed_deliveries_sync`` into:
- a Celery task (worker + optional beat schedule);
- a pure runner used by CLI / tests without Redis.

Never creates tickets. One pass is bounded by ``limit``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
DEFAULT_STATES: tuple[str, ...] = ("failed",)
TASK_NAME = "tasks.outbox_retry_task.retry_escalation_outbox"


def outbox_retry_limit_from_env() -> int:
    raw = os.getenv("RAG_OUTBOX_RETRY_BATCH_LIMIT", str(DEFAULT_LIMIT))
    try:
        return max(1, min(int(raw or DEFAULT_LIMIT), 500))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def outbox_retry_interval_sec_from_env() -> float:
    raw = os.getenv("RAG_OUTBOX_RETRY_INTERVAL_SEC", "300")
    try:
        return max(30.0, float(raw or 300))
    except (TypeError, ValueError):
        return 300.0


def outbox_retry_beat_enabled_from_env() -> bool:
    """Beat schedule registration (default ON). Disable with RAG_OUTBOX_RETRY_BEAT=false."""
    return os.getenv("RAG_OUTBOX_RETRY_BEAT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def outbox_retry_states_from_env() -> list[str]:
    """Default failed-only; include pending when RAG_OUTBOX_RETRY_INCLUDE_PENDING=true."""
    states = ["failed"]
    if os.getenv("RAG_OUTBOX_RETRY_INCLUDE_PENDING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        states.append("pending")
    return states


def build_outbox_beat_schedule(
    *,
    enabled: bool | None = None,
    interval_sec: float | None = None,
    limit: int | None = None,
    states: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Celery beat_schedule fragment for escalation outbox retry."""
    if enabled is None:
        enabled = outbox_retry_beat_enabled_from_env()
    if not enabled:
        return {}
    interval = (
        float(interval_sec)
        if interval_sec is not None
        else outbox_retry_interval_sec_from_env()
    )
    batch_limit = int(limit) if limit is not None else outbox_retry_limit_from_env()
    state_list = list(states) if states is not None else outbox_retry_states_from_env()
    return {
        "escalation-outbox-retry": {
            "task": TASK_NAME,
            "schedule": interval,
            "kwargs": {
                "limit": batch_limit,
                "states": state_list,
            },
            "options": {"expires": max(interval * 0.9, 15.0)},
        }
    }


def run_outbox_retry_once(
    *,
    limit: int = DEFAULT_LIMIT,
    states: Sequence[str] | None = None,
    tenant_id: str | None = None,
    retry_fn: Any | None = None,
) -> dict[str, Any]:
    """Run one bounded outbox retry pass; return serializable summary."""
    from services.escalation import (  # noqa: PLC0415
        retry_failed_deliveries_sync,
    )

    wanted = list(states) if states is not None else list(DEFAULT_STATES)
    runner = retry_fn or retry_failed_deliveries_sync
    batch = runner(limit=int(limit), states=wanted, tenant_id=tenant_id)
    if hasattr(batch, "as_dict"):
        payload = batch.as_dict()
    elif isinstance(batch, dict):
        payload = dict(batch)
    else:
        payload = {
            "attempted": int(getattr(batch, "attempted", 0) or 0),
            "delivered": int(getattr(batch, "delivered", 0) or 0),
            "failed": int(getattr(batch, "failed", 0) or 0),
            "skipped": int(getattr(batch, "skipped", 0) or 0),
            "results": [],
        }
    payload["kind"] = "escalation-outbox-retry"
    payload["limit"] = int(limit)
    payload["states"] = wanted
    payload["tenant_id"] = tenant_id
    return payload


@shared_task(name=TASK_NAME, bind=False, ignore_result=False)
def retry_escalation_outbox(
    limit: int | None = None,
    states: list[str] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Celery task: one outbox retry pass (no second tickets)."""
    batch_limit = int(limit) if limit is not None else outbox_retry_limit_from_env()
    state_list = list(states) if states is not None else outbox_retry_states_from_env()
    logger.info(
        "Outbox retry start limit=%s states=%s tenant=%s",
        batch_limit,
        state_list,
        tenant_id or "*",
    )
    try:
        result = run_outbox_retry_once(
            limit=batch_limit,
            states=state_list,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error("Outbox retry task failed: %s", exc, exc_info=True)
        return {
            "kind": "escalation-outbox-retry",
            "attempted": 0,
            "delivered": 0,
            "failed": 0,
            "skipped": 0,
            "error": str(exc) or type(exc).__name__,
            "limit": batch_limit,
            "states": state_list,
            "tenant_id": tenant_id,
        }
    logger.info(
        "Outbox retry done attempted=%s delivered=%s failed=%s skipped=%s",
        result.get("attempted"),
        result.get("delivered"),
        result.get("failed"),
        result.get("skipped"),
    )
    return result

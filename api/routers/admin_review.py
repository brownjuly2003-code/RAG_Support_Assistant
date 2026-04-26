"""Admin review queue endpoints — list, update, stats.

Extracted from api.app on 2026-04-26 (Phase 2e). The three endpoints depend
on several private helpers in api.app (_review_queue_enabled,
_load_review_queue_trace_details, _refresh_review_queue_metrics,
_serialize_timestamp, _reviewed_by_uuid, _REVIEW_QUEUE_*). These are
imported lazily inside each handler to avoid a circular import with
api.app at module load time.

This is intentional: the helpers will move to api._shared in a follow-up
PR; once they do, the lazy imports here can become top-level.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.correlation import get_current_tenant
from auth.dependencies import require_role
from db import engine as _db_engine

router = APIRouter()


def _async_session():
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


class ReviewQueueUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        pattern=r"^(pending|in_review|confirmed_good|confirmed_bad|dismissed)$",
    )
    reviewer_notes: str = Field(default="", max_length=5000)
    reviewed_by: str | None = Field(default=None, max_length=64)


@router.get("/admin/review-queue")
async def admin_list_review_queue(
    status: str = "pending",
    reason: str = "*",
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from api import app as _app  # noqa: PLC0415

    if not _app._review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    normalized_status = None if status in ("", "*") else status
    normalized_reason = None if reason in ("", "*") else reason
    if normalized_status is not None and normalized_status not in _app._REVIEW_QUEUE_STATUSES:
        raise HTTPException(status_code=422, detail="invalid review queue status")
    if normalized_reason is not None and normalized_reason not in _app._REVIEW_QUEUE_REASONS:
        raise HTTPException(status_code=422, detail="invalid review queue reason")

    safe_limit = max(1, min(500, limit))
    safe_offset = max(0, offset)
    tenant = _user.get("tenant") or get_current_tenant() or "default"

    query = """
        SELECT id, trace_id, tenant_id, reason, status, reviewer_notes, created_at, reviewed_at, reviewed_by
        FROM review_queue
        WHERE tenant_id = :tenant_id
    """
    params: dict[str, Any] = {
        "tenant_id": tenant,
        "limit": safe_limit,
        "offset": safe_offset,
    }
    if normalized_status is not None:
        query += " AND status = :status"
        params["status"] = normalized_status
    if normalized_reason is not None:
        query += " AND reason = :reason"
        params["reason"] = normalized_reason
    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

    async with _async_session() as db:
        rows = (await db.execute(text(query), params)).mappings().all()

    trace_details = _app._load_review_queue_trace_details([str(row["trace_id"]) for row in rows])
    await _app._refresh_review_queue_metrics(tenant)
    return JSONResponse(
        content={
            "items": [
                {
                    "id": row["id"],
                    "trace_id": row["trace_id"],
                    "tenant_id": row["tenant_id"],
                    "reason": row["reason"],
                    "status": row["status"],
                    "reviewer_notes": row["reviewer_notes"] or "",
                    "created_at": _app._serialize_timestamp(row["created_at"]),
                    "reviewed_at": _app._serialize_timestamp(row["reviewed_at"]),
                    "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] is not None else None,
                    "quality": trace_details.get(str(row["trace_id"]), {}).get("quality"),
                    "fact_score": trace_details.get(str(row["trace_id"]), {}).get("fact_score"),
                    "duration_ms": trace_details.get(str(row["trace_id"]), {}).get("duration_ms"),
                    "trace_url": trace_details.get(str(row["trace_id"]), {}).get(
                        "trace_url",
                        f"/admin/traces/{row['trace_id']}",
                    ),
                }
                for row in rows
            ],
            "count": len(rows),
            "limit": safe_limit,
            "offset": safe_offset,
        }
    )


@router.post("/admin/review-queue/{review_id}")
async def admin_update_review_queue(
    review_id: int,
    body: ReviewQueueUpdateRequest,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from api import app as _app  # noqa: PLC0415

    if not _app._review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    reviewer_id = _app._reviewed_by_uuid(body.reviewed_by or _user.get("sub"))
    reviewed_at = datetime.now(timezone.utc) if body.status != "pending" else None

    async with _async_session() as db:
        result = await db.execute(
            text(
                """
                UPDATE review_queue
                SET status = :status,
                    reviewer_notes = :reviewer_notes,
                    reviewed_by = :reviewed_by,
                    reviewed_at = :reviewed_at
                WHERE id = :review_id AND tenant_id = :tenant_id
                """
            ),
            {
                "status": body.status,
                "reviewer_notes": body.reviewer_notes.strip(),
                "reviewed_by": reviewer_id,
                "reviewed_at": reviewed_at,
                "review_id": review_id,
                "tenant_id": tenant,
            },
        )
        await db.commit()

    if int(getattr(result, "rowcount", 0) or 0) == 0:
        raise HTTPException(status_code=404, detail="review item not found")

    await _app._refresh_review_queue_metrics(tenant)
    return JSONResponse(content={"status": "ok"})


@router.get("/admin/review-queue/stats")
async def admin_review_queue_stats(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from api import app as _app  # noqa: PLC0415

    if not _app._review_queue_enabled():
        raise HTTPException(status_code=404, detail="review queue disabled")

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    status_counts = {item: 0 for item in _app._REVIEW_QUEUE_STATUSES}
    reason_counts = {item: 0 for item in _app._REVIEW_QUEUE_REASONS}
    oldest_pending_seconds = 0.0

    async with _async_session() as db:
        status_rows = (
            await db.execute(
                text(
                    """
                    SELECT status, COUNT(*) AS total
                    FROM review_queue
                    WHERE tenant_id = :tenant_id
                    GROUP BY status
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        for row in status_rows:
            key = str(row["status"])
            if key in status_counts:
                status_counts[key] = int(row["total"] or 0)

        reason_rows = (
            await db.execute(
                text(
                    """
                    SELECT reason, COUNT(*) AS total
                    FROM review_queue
                    WHERE tenant_id = :tenant_id
                    GROUP BY reason
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        for row in reason_rows:
            key = str(row["reason"])
            if key in reason_counts:
                reason_counts[key] = int(row["total"] or 0)

        oldest_rows = (
            await db.execute(
                text(
                    """
                    SELECT MIN(created_at) AS oldest_pending
                    FROM review_queue
                    WHERE tenant_id = :tenant_id AND status = 'pending'
                    """
                ),
                {"tenant_id": tenant},
            )
        ).mappings().all()
        oldest_pending = oldest_rows[0]["oldest_pending"] if oldest_rows else None
        if oldest_pending is not None:
            if isinstance(oldest_pending, str):
                oldest_pending = datetime.fromisoformat(oldest_pending)
            if oldest_pending.tzinfo is None:
                oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
            oldest_pending_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - oldest_pending).total_seconds(),
            )

    await _app._refresh_review_queue_metrics(tenant)
    return JSONResponse(
        content={
            "status_counts": status_counts,
            "reason_counts": reason_counts,
            "oldest_pending_seconds": oldest_pending_seconds,
        }
    )

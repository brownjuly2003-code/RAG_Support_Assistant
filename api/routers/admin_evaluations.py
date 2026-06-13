"""Admin evaluation and regression-run endpoints.

Extracted from api.app on 2026-04-27 (Phase 2h). Regression job state and
report helpers remain in api.app so existing tests can keep monkeypatching
them there.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api._shared import app_module as _app_module
from auth.dependencies import require_role
from db import engine as _db_engine

router = APIRouter()


def _async_session() -> Any:
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


@router.get("/admin/evaluations/trends")
async def admin_evaluation_trends(
    evaluator: str,
    days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _ = _user
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be in [1, 365]")
    if not getattr(_app_module().get_settings(), "online_evaluators_enabled", True):
        return JSONResponse(content={"evaluator": evaluator, "days": days, "points": []})

    async with _async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        DATE(evaluated_at) AS bucket,
                        AVG(score) AS mean_score,
                        COUNT(*) AS runs
                    FROM trace_evaluations
                    WHERE evaluator_name = :evaluator_name
                      AND evaluated_at >= :window_start
                    GROUP BY DATE(evaluated_at)
                    ORDER BY bucket ASC
                    """
                ),
                {
                    "evaluator_name": evaluator,
                    "window_start": datetime.now(timezone.utc) - timedelta(days=days),
                },
            )
        ).mappings().all()

    return JSONResponse(
        content={
            "evaluator": evaluator,
            "days": days,
            "points": [
                {
                    "date": str(row.get("bucket") or ""),
                    "mean_score": float(row.get("mean_score") or 0.0),
                    "runs": int(row.get("runs") or 0),
                }
                for row in rows
            ],
        }
    )


@router.get("/admin/evaluations/worst")
async def admin_evaluation_worst(
    evaluator: str,
    limit: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _ = _user
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be in [1, 100]")
    if not getattr(_app_module().get_settings(), "online_evaluators_enabled", True):
        return JSONResponse(content={"evaluator": evaluator, "limit": limit, "items": []})

    async with _async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        trace_id,
                        score,
                        verdict,
                        metadata,
                        evaluated_at
                    FROM trace_evaluations
                    WHERE evaluator_name = :evaluator_name
                    ORDER BY score ASC, evaluated_at ASC
                    LIMIT :limit
                    """
                ),
                {
                    "evaluator_name": evaluator,
                    "limit": limit,
                },
            )
        ).mappings().all()

    return JSONResponse(
        content={
            "evaluator": evaluator,
            "limit": limit,
            "items": [
                {
                    "trace_id": str(row.get("trace_id") or ""),
                    "score": float(row.get("score") or 0.0),
                    "verdict": str(row.get("verdict") or ""),
                    "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                    "evaluated_at": (
                        row.get("evaluated_at").isoformat()
                        if hasattr(row.get("evaluated_at"), "isoformat")
                        else str(row.get("evaluated_at"))
                        if row.get("evaluated_at") is not None
                        else None
                    ),
                }
                for row in rows
            ],
        }
    )


@router.get("/admin/regression-runs")
async def admin_list_regression_runs(
    limit: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _app = _app_module()
    normalized_limit = max(1, min(limit, 100))
    rows = await _app._list_regression_run_rows(normalized_limit)
    items = [_app._serialize_regression_row(row) for row in rows]
    known_ids = {item["run_id"] for item in items}

    pending_jobs = [
        _app._serialize_regression_job(job)
        for job in _app._regression_jobs.values()
        if str(job.get("run_id") or "") not in known_ids
    ]

    combined = pending_jobs + items
    combined.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return JSONResponse(content={"runs": combined[:normalized_limit]})


@router.get("/admin/regression-runs/{run_id}")
async def admin_get_regression_run(
    run_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _app = _app_module()
    row = await _app._get_regression_run_row(run_id)
    if row is not None:
        report_payload, report_markdown = _app._read_regression_report_assets(row.get("report_path"))
        payload = _app._serialize_regression_row(row)
        payload["report"] = report_payload
        payload["report_markdown"] = report_markdown
        return JSONResponse(content=payload)

    job = _app._regression_jobs.get(run_id)
    if job is not None:
        return JSONResponse(content=_app._serialize_regression_job(job))

    raise HTTPException(status_code=404, detail="regression run not found")

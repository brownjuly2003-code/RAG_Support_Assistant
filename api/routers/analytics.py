"""Analytics dashboard endpoints.

Extracted from api.app on 2026-04-27 (Phase 2i). The trace summary loader
stays in api.app for now so existing tests can keep monkeypatching it there.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.correlation import get_current_tenant
from auth.dependencies import require_role

router = APIRouter()


def _load_recent_trace_summaries(tenant: str, days: int) -> list[dict[str, Any]]:
    from api import app as _app  # noqa: PLC0415

    return _app._load_recent_trace_summaries(tenant, days)


@router.get("/analytics/top-topics")
async def analytics_top_topics(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, dict[str, float]] = {}
    for item in summaries:
        for category in item["categories"]:
            entry = grouped.setdefault(category, {"count": 0, "quality_sum": 0.0})
            entry["count"] += 1
            entry["quality_sum"] += float(item["quality_score"] or 0)
    topics = [
        {
            "category": category,
            "count": int(values["count"]),
            "avg_quality": round(values["quality_sum"] / values["count"], 2) if values["count"] else 0.0,
        }
        for category, values in grouped.items()
    ]
    topics.sort(key=lambda item: (-item["count"], item["category"]))
    return JSONResponse(content={"topics": topics[:10]})


@router.get("/analytics/resolution-rate")
async def analytics_resolution_rate(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, dict[str, int]] = {}
    for item in summaries:
        for category in item["categories"]:
            entry = grouped.setdefault(category, {"total": 0, "resolved": 0})
            entry["total"] += 1
            if item["route"] == "auto":
                entry["resolved"] += 1
    payload = [
        {
            "category": category,
            "resolution_rate": round(values["resolved"] / values["total"], 4) if values["total"] else 0.0,
            "total": values["total"],
        }
        for category, values in grouped.items()
    ]
    payload.sort(key=lambda item: item["category"])
    return JSONResponse(content={"topics": payload})


@router.get("/analytics/cost-summary")
async def analytics_cost_summary(
    days: int = 7,
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    total_cost = round(sum(float(item["cost_usd"] or 0.0) for item in summaries), 6)
    per_category: dict[str, float] = {}
    per_model: dict[str, float] = {}
    for item in summaries:
        for category in item["categories"]:
            per_category[category] = round(per_category.get(category, 0.0) + float(item["cost_usd"] or 0.0), 6)
        model_name = str(item.get("model_name") or "unknown")
        per_model[model_name] = round(per_model.get(model_name, 0.0) + float(item["cost_usd"] or 0.0), 6)
    return JSONResponse(
        content={
            "summary": {
                "total_cost_usd": total_cost,
                "label": "self-hosted (no cost)" if total_cost == 0 else f"${total_cost:.2f}",
                "tooltip": "local models are not billed" if total_cost == 0 else "",
                "free_tier": total_cost == 0,
            },
            "per_category": [
                {"category": category, "cost_usd": cost}
                for category, cost in sorted(per_category.items())
            ],
            "per_model": [
                {"model_name": model_name, "cost_usd": cost}
                for model_name, cost in sorted(per_model.items())
            ],
        }
    )


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = 30,
    metric: str = "quality",
    _user: dict = Depends(require_role("admin", "agent")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    summaries = _load_recent_trace_summaries(tenant, days)
    grouped: dict[str, list[float]] = {}
    for item in summaries:
        bucket = item["created_at"].date().isoformat()
        if metric == "cost":
            value = float(item["cost_usd"] or 0.0)
        elif metric == "resolution":
            value = 1.0 if item["route"] == "auto" else 0.0
        else:
            value = float(item["quality_score"] or 0.0)
        grouped.setdefault(bucket, []).append(value)
    payload = [
        {
            "date": bucket,
            "value": round(sum(values) / len(values), 4) if values else 0.0,
        }
        for bucket, values in sorted(grouped.items())
    ]
    return JSONResponse(content={"metric": metric, "points": payload})

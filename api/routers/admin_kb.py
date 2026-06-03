"""Admin knowledge-base endpoints.

Extracted from api.app on 2026-04-27 (Phase 2f). Handlers keep lazy access to
api.app helpers so existing tests that monkeypatch api.app remain effective.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import text as sql_text

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant
from auth.dependencies import require_role
from db import engine as _db_engine
from utils.background_tasks import spawn_tracked

router = APIRouter()


def _async_session():
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


class KbDraftUpdateRequest(BaseModel):
    draft_content: str = Field(..., min_length=1, max_length=20000)


@router.get("/admin/curated-dataset/stats")
async def admin_curated_dataset_stats(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    _ = _user
    _app = _app_module()
    return JSONResponse(content=_app._curated_dataset_summary())


@router.post("/admin/curated-dataset/rebuild")
async def admin_rebuild_curated_dataset(
    tenant: str = "all",
    since: str | None = None,
    include_bad: bool = False,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    _ = _user
    _app = _app_module()
    job_id = str(uuid.uuid4())
    dataset_path = _app._curated_dataset_path()
    _app._store_curated_dataset_job(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "tenant": tenant,
            "since": since,
            "include_bad": include_bad,
            "progress": 0,
            "out": str(dataset_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    spawn_tracked(
        _app._run_curated_dataset_rebuild(
            job_id=job_id,
            tenant=tenant,
            since=since,
            include_bad=include_bad,
        )
    )
    return JSONResponse(content={"job_id": job_id, "status": "queued"})


@router.get("/admin/recommendations/current")
async def admin_recommendations_current(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    _app = _app_module()
    settings = _app.get_settings()
    if not getattr(settings, "recommendations_enabled", True):
        return JSONResponse(content={"recommendations": [], "status": "disabled"})

    from scripts.generate_recommendations import (  # noqa: PLC0415
        aggregate_recommendations,
        fetch_signals,
    )

    try:
        async with _async_session() as db:
            signals = await fetch_signals(db)
    except Exception:
        signals = {
            "backlog_items": [],
            "threshold_items": [],
            "green_regressions": [],
            "stale_cases": [],
        }

    recommendations = aggregate_recommendations(**signals)
    return JSONResponse(
        content={
            "recommendations": [rec.to_dict() for rec in recommendations],
            "status": "ok",
        }
    )


@router.get("/admin/curated-dataset/stale")
async def admin_curated_dataset_stale(
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    tenant = _user.get("tenant") or get_current_tenant() or None
    params: dict[str, object] = {}
    if tenant and tenant != "*":
        params["tenant_id"] = tenant

    statement = sql_text(
        "SELECT case_id, tenant_id, status, staleness_reason, last_checked_at "
        "FROM curated_case_status "
        "WHERE (:tenant_id IS NULL OR tenant_id = :tenant_id) "
        "AND status = 'stale_needs_review' "
        "ORDER BY last_checked_at DESC"
    )
    params.setdefault("tenant_id", None)

    async with _async_session() as db:
        result = await db.execute(statement, params)
        rows = list(result.mappings().all())

    items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        checked = item.get("last_checked_at")
        if checked is not None and hasattr(checked, "isoformat"):
            item["last_checked_at"] = checked.isoformat()
        items.append(item)

    return JSONResponse(content={"items": items})


@router.get("/admin/thresholds/analysis")
async def admin_threshold_analysis(
    days: int = 30,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    _app = _app_module()
    safe_days = max(1, min(365, days))
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    cache_key = f"threshold-analysis:{tenant}:{safe_days}"
    cached_payload = _app.cache_json_get(cache_key)
    if cached_payload is not None:
        payload = dict(cached_payload)
        payload["cached"] = True
        return JSONResponse(content=payload)

    from scripts import analyze_thresholds  # noqa: PLC0415

    settings = _app.get_settings()
    report_path = Path(getattr(settings, "project_root", _app.PROJECT_ROOT)) / "reports" / "threshold_recommendations.md"
    payload = await analyze_thresholds.run_once(
        days=safe_days,
        tenant=tenant,
        out=report_path,
        settings=settings,
    )
    _app.cache_json_set(cache_key, payload, ttl_seconds=86400)
    payload = dict(payload)
    payload["cached"] = False
    return JSONResponse(content=payload)


@router.post("/admin/thresholds/refresh")
async def admin_refresh_threshold_analysis(
    days: int = 30,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    from scripts import analyze_thresholds  # noqa: PLC0415

    _app = _app_module()
    safe_days = max(1, min(365, days))
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    settings = _app.get_settings()
    report_path = Path(getattr(settings, "project_root", _app.PROJECT_ROOT)) / "reports" / "threshold_recommendations.md"
    payload = await analyze_thresholds.run_once(
        days=safe_days,
        tenant=tenant,
        out=report_path,
        settings=settings,
    )
    _app.cache_json_set(f"threshold-analysis:{tenant}:{safe_days}", payload, ttl_seconds=86400)
    payload = dict(payload)
    payload["cached"] = False
    return JSONResponse(content=payload)


@router.get("/admin/improvement-backlog/current")
async def admin_current_improvement_backlog(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from scripts import generate_improvement_backlog  # noqa: PLC0415

    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    settings = _app.get_settings()
    project_root = Path(getattr(settings, "project_root", _app.PROJECT_ROOT))
    week = generate_improvement_backlog.latest_persisted_week(project_root)
    if week is None:
        week = generate_improvement_backlog.default_week_spec(datetime.now(timezone.utc))

    payload = await generate_improvement_backlog.run_once(
        tenant=tenant,
        week=week,
        out=None,
        settings=settings,
    )
    return JSONResponse(content=payload)


@router.get("/admin/improvement-backlog/archive")
async def admin_improvement_backlog_archive(
    year: int | None = None,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from scripts import generate_improvement_backlog  # noqa: PLC0415

    _ = _user
    _app = _app_module()
    settings = _app.get_settings()
    project_root = Path(getattr(settings, "project_root", _app.PROJECT_ROOT))
    return JSONResponse(
        content={
            "weeks": generate_improvement_backlog.list_archive_weeks(project_root, year),
        }
    )


@router.get("/admin/kb-gaps")
async def admin_list_kb_gaps(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import KnowledgeGap  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        stmt = (
            select(KnowledgeGap)
            .where(KnowledgeGap.tenant_id == tenant)
            .order_by(KnowledgeGap.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "gaps": [
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "cluster_id": row.cluster_id,
                    "topic_summary": row.topic_summary,
                    "sample_questions": row.sample_questions,
                    "question_count": row.question_count,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in rows
            ]
        }
    )


@router.get("/admin/categories")
async def admin_list_categories(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from ingestion.categorizer import load_categories  # noqa: PLC0415

    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return JSONResponse(
        content={
            "categories": load_categories(
                tenant,
                config_path=_app.get_settings().categories_config_path,
            )
        }
    )


@router.get("/admin/kb-drafts")
async def admin_list_kb_drafts(
    status: str | None = None,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        stmt = (
            select(KbDraft)
            .where(KbDraft.tenant_id == tenant)
            .order_by(KbDraft.created_at.desc())
        )
        if status:
            stmt = stmt.where(KbDraft.status == status)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return JSONResponse(
        content={
            "drafts": [
                {
                    "id": str(row.id),
                    "tenant_id": row.tenant_id,
                    "topic": row.topic,
                    "draft_content": row.draft_content,
                    "source_ticket_ids": row.source_ticket_ids,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                }
                for row in rows
            ]
        }
    )


@router.patch("/admin/kb-drafts/{draft_id}")
async def admin_update_kb_draft(
    draft_id: str,
    body: KbDraftUpdateRequest,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")
        draft.draft_content = body.draft_content.strip()
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.post("/admin/kb-drafts/{draft_id}/reject")
async def admin_reject_kb_draft(
    draft_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import KbDraft  # noqa: PLC0415

    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")
        draft.status = "rejected"
        draft.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.post("/admin/kb-drafts/{draft_id}/publish")
async def admin_publish_kb_draft(
    draft_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import KbDraft  # noqa: PLC0415
    from vectordb import manager as tenant_manager  # noqa: PLC0415

    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    async with _async_session() as db:
        draft = await db.get(KbDraft, uuid.UUID(draft_id))
        if draft is None or draft.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail="draft is immutable")

        doc = _app.Document(
            page_content=draft.draft_content,
            metadata={
                "doc_id": f"kb-builder/{draft.id}",
                "source": f"kb-builder/{draft.id}",
                "title": draft.topic,
                "tenant_id": draft.tenant_id,
                "auto_generated": True,
                "generated_from_tickets": draft.source_ticket_ids,
                "categories": ["uncategorized"],
                "primary_category": "uncategorized",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        )

        if tenant_manager.Chroma is not None:
            store = tenant_manager.Chroma(
                persist_directory=str(_app.get_settings().vectordb_chroma_dir),
                embedding_function=tenant_manager.get_embeddings(),
                collection_name=tenant_manager._collection_name(draft.tenant_id),
            )
            if hasattr(store, "add_documents"):
                store.add_documents([doc])
                if hasattr(store, "persist"):
                    store.persist()

        draft.status = "published"
        draft.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
    return JSONResponse(content={"status": "ok"})


@router.get("/admin/stale-docs")
async def admin_list_stale_docs(
    days: int = 90,
    top_cited: int = 20,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from db.models import DocumentStats  # noqa: PLC0415

    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    documents = {item["doc_id"]: item for item in _app._list_tenant_documents(tenant)}

    async with _async_session() as db:
        stmt = (
            select(DocumentStats)
            .where(DocumentStats.tenant_id == tenant)
            .order_by(DocumentStats.citation_count.desc())
            .limit(max(1, min(top_cited, 100)))
        )
        result = await db.execute(stmt)
        stats_rows = result.scalars().all()

    stale_documents = []
    for row in stats_rows:
        metadata = documents.get(row.doc_id)
        if not metadata or not metadata.get("last_updated"):
            continue
        try:
            last_updated = datetime.fromisoformat(str(metadata["last_updated"]))
        except ValueError:
            continue
        if last_updated >= cutoff:
            continue
        stale_documents.append(
            {
                "doc_id": row.doc_id,
                "title": metadata.get("title") or row.doc_id,
                "source": metadata.get("source") or row.doc_id,
                "last_updated": metadata.get("last_updated"),
                "citation_count": row.citation_count,
                "last_cited_at": row.last_cited_at.isoformat() if row.last_cited_at else None,
            }
        )

    try:
        _app.prometheus_metrics.record_stale_important_docs(len(stale_documents))
    except Exception:
        pass
    return JSONResponse(content={"documents": stale_documents})


@router.post("/admin/stale-docs/{doc_id}/review")
async def admin_review_stale_doc(
    doc_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    if not _app._touch_tenant_document(tenant, doc_id):
        raise HTTPException(status_code=404, detail="document not found")
    return JSONResponse(content={"status": "ok"})

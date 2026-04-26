"""Admin experiment endpoints.

Extracted from api.app on 2026-04-27 (Phase 2g). Regression job state and
runner logic remain in api.app because /admin/regression-runs still uses them.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text as sql_text

from auth.dependencies import require_role
from db import engine as _db_engine

logger = logging.getLogger(__name__)

router = APIRouter()


def _async_session():
    """Indirection to keep monkeypatch.setattr('db.engine.async_session', ...) effective."""
    return _db_engine.async_session()


def _app_module():
    from api import app as _app  # noqa: PLC0415

    return _app


def _project_root_path() -> Path:
    _app = _app_module()
    return Path(getattr(_app.get_settings(), "project_root", _app.PROJECT_ROOT))


def _experiments_dir() -> Path:
    return _project_root_path() / "evaluation" / "experiments"


def _empty_experiment_bucket(experiment_id: str | None) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "trace_count": 0,
        "quality": {"mean": None, "p50": None, "p95": None},
        "evaluator_breakdown": {},
        "cost_per_trace": None,
        "latency": {"p50": None, "p95": None},
    }


async def _fetch_experiment_live_bucket(db, experiment_id: str) -> dict[str, Any]:
    bucket = _empty_experiment_bucket(experiment_id)
    try:
        result = await db.execute(
            sql_text(
                "SELECT COUNT(*) AS trace_count, AVG(quality_score) AS quality_mean, "
                "AVG(cost_usd) AS cost_mean, AVG(latency_ms) AS latency_mean "
                "FROM traces WHERE experiment_id = :experiment_id"
            ),
            {"experiment_id": experiment_id},
        )
        row = result.mappings().first() or {}
    except Exception:
        return bucket

    trace_count = int(row.get("trace_count") or 0)
    quality = row.get("quality_mean")
    cost = row.get("cost_mean")
    latency = row.get("latency_mean")
    bucket["trace_count"] = trace_count
    bucket["quality"] = {
        "mean": float(quality) if quality is not None else None,
        "p50": float(quality) if quality is not None else None,
        "p95": float(quality) if quality is not None else None,
    }
    bucket["cost_per_trace"] = float(cost) if cost is not None else None
    bucket["latency"] = {
        "p50": float(latency) if latency is not None else None,
        "p95": float(latency) if latency is not None else None,
    }
    return bucket


async def _fetch_experiment_staged_bucket(db, experiment_id: str) -> dict[str, Any]:
    bucket = _empty_experiment_bucket(experiment_id)
    try:
        result = await db.execute(
            sql_text(
                "SELECT run_id, quality_delta, cost_delta, latency_delta "
                "FROM eval_results WHERE candidate_experiment_id = :experiment_id "
                "ORDER BY started_at DESC LIMIT 1"
            ),
            {"experiment_id": experiment_id},
        )
        row = result.mappings().first() or {}
    except Exception:
        return bucket

    if not row:
        return bucket

    quality_delta = row.get("quality_delta")
    cost_delta = row.get("cost_delta")
    latency_delta = row.get("latency_delta")
    bucket["evaluator_breakdown"] = {
        "run_id": row.get("run_id"),
        "quality_delta": float(quality_delta) if quality_delta is not None else None,
        "cost_delta": float(cost_delta) if cost_delta is not None else None,
        "latency_delta": float(latency_delta) if latency_delta is not None else None,
    }
    if quality_delta is not None:
        bucket["quality"] = {
            "mean": float(quality_delta),
            "p50": float(quality_delta),
            "p95": float(quality_delta),
        }
    return bucket


def _fetch_experiment_candidate_bucket(experiment_id: str | None) -> dict[str, Any]:
    bucket = _empty_experiment_bucket(experiment_id)
    if not experiment_id:
        return bucket
    path = _experiments_dir() / f"{experiment_id}.yaml"
    if path.exists():
        bucket["evaluator_breakdown"] = {"yaml_present": True}
    else:
        bucket["evaluator_breakdown"] = {"yaml_present": False}
    return bucket


def _deployed_experiment_runtime_path() -> Path:
    return _project_root_path() / "config" / "deployed_experiment.yaml"


def _write_deployed_experiment_runtime_file(experiment_id: str) -> None:
    import yaml as _yaml  # noqa: PLC0415

    path = _deployed_experiment_runtime_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _yaml.safe_dump({"experiment_id": experiment_id}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )


def _clear_deployed_experiment_runtime_file() -> None:
    path = _deployed_experiment_runtime_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


@router.get("/admin/experiments")
async def admin_list_experiments(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment  # noqa: PLC0415

    experiments = []
    for path in sorted(_experiments_dir().glob("*.yaml")):
        experiment = load_experiment(path)
        experiments.append(
            {
                "id": experiment.id,
                "name": experiment.name,
                "status": experiment.status,
                "latest_eval_link": None,
            }
        )
    return JSONResponse(content={"experiments": experiments})


@router.get("/admin/experiments/comparison")
async def admin_experiments_comparison(
    deployed: str | None = None,
    staged: str | None = None,
    candidate: str | None = None,
    _user: dict = Depends(require_role("admin", "reviewer")),
) -> JSONResponse:
    async with _async_session() as db:
        deployed_bucket = (
            await _fetch_experiment_live_bucket(db, deployed)
            if deployed
            else _empty_experiment_bucket(None)
        )
        staged_bucket = (
            await _fetch_experiment_staged_bucket(db, staged)
            if staged
            else _empty_experiment_bucket(None)
        )

    candidate_bucket = _fetch_experiment_candidate_bucket(candidate)

    return JSONResponse(
        content={
            "deployed": deployed_bucket,
            "staged": staged_bucket,
            "candidate": candidate_bucket,
        }
    )


@router.get("/admin/experiments/{experiment_id}")
async def admin_get_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    experiment = load_experiment(path)
    payload = experiment.model_dump(mode="json")
    payload["latest_eval_link"] = None
    return JSONResponse(content=payload)


@router.post("/admin/experiments/{experiment_id}/archive")
async def admin_archive_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment, save_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    experiment = load_experiment(path)
    experiment.status = "archived"
    save_experiment(experiment, path)
    return JSONResponse(content={"status": "archived", "id": experiment.id})


@router.post("/admin/experiments/{experiment_id}/regression-run")
async def admin_run_experiment_regression(
    experiment_id: str,
    baseline: str = "current",
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _app = _app_module()

    if experiment_id != "current":
        candidate_path = _experiments_dir() / f"{experiment_id}.yaml"
        if not candidate_path.exists():
            raise HTTPException(status_code=404, detail="experiment not found")

    if baseline != "current":
        baseline_path = _experiments_dir() / f"{baseline}.yaml"
        if not baseline_path.exists():
            raise HTTPException(status_code=404, detail="baseline experiment not found")

    run_id = f"regression-{uuid.uuid4().hex[:12]}"
    _app._regression_jobs[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "baseline": baseline,
        "candidate": experiment_id,
        "created_at": datetime.now(timezone.utc),
    }
    asyncio.create_task(_app._run_regression_job(run_id, baseline, experiment_id))
    return JSONResponse(
        status_code=202,
        content={"job_id": run_id, "status": "queued"},
    )


@router.post("/admin/experiments/{experiment_id}/deploy")
async def admin_deploy_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment, save_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    now = datetime.now(timezone.utc)
    async with _async_session() as db:
        regression_stmt = sql_text(
            "SELECT run_id, candidate_experiment_id, drift_alert "
            "FROM eval_results "
            "WHERE candidate_experiment_id = :experiment_id "
            "AND drift_alert = false "
            "ORDER BY started_at DESC LIMIT 1"
        )
        regression_result = await db.execute(
            regression_stmt,
            {"experiment_id": experiment_id},
        )
        regression_row = regression_result.mappings().first()
        if not regression_row:
            raise HTTPException(
                status_code=409,
                detail="green regression run on curated dataset is required before deploy",
            )

        run_id = regression_row["run_id"]
        await db.execute(
            sql_text(
                "INSERT INTO experiment_deployments "
                "(experiment_id, regression_run_id, staged_at, deployed_at) "
                "VALUES (:experiment_id, :regression_run_id, :staged_at, :deployed_at)"
            ),
            {
                "experiment_id": experiment_id,
                "regression_run_id": run_id,
                "staged_at": now,
                "deployed_at": now,
            },
        )
        await db.commit()

    experiment = load_experiment(path)
    experiment.status = "deployed"
    save_experiment(experiment, path)
    _write_deployed_experiment_runtime_file(experiment_id)

    return JSONResponse(
        content={
            "status": "deployed",
            "id": experiment_id,
            "deployment": {
                "regression_run_id": run_id,
                "staged_at": now.isoformat(),
                "deployed_at": now.isoformat(),
            },
        }
    )


@router.post("/admin/experiments/{experiment_id}/rollback")
async def admin_rollback_experiment(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    from evaluation.experiment_schema import load_experiment, save_experiment  # noqa: PLC0415

    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    now = datetime.now(timezone.utc)
    async with _async_session() as db:
        active_stmt = sql_text(
            "SELECT experiment_id, regression_run_id, staged_at, deployed_at "
            "FROM experiment_deployments "
            "WHERE experiment_id = :experiment_id "
            "AND rolled_back_at IS NULL "
            "ORDER BY deployed_at DESC LIMIT 1"
        )
        active_result = await db.execute(
            active_stmt,
            {"experiment_id": experiment_id},
        )
        active_row = active_result.mappings().first()
        if not active_row:
            raise HTTPException(
                status_code=409,
                detail="no active deployment to rollback",
            )

        regression_run_id = active_row.get("regression_run_id")
        await db.execute(
            sql_text(
                "UPDATE experiment_deployments "
                "SET rolled_back_at = :rolled_back_at "
                "WHERE experiment_id = :experiment_id "
                "AND regression_run_id = :regression_run_id "
                "AND rolled_back_at IS NULL"
            ),
            {
                "rolled_back_at": now,
                "experiment_id": experiment_id,
                "regression_run_id": regression_run_id,
            },
        )
        await db.commit()

    experiment = load_experiment(path)
    experiment.status = "completed"
    save_experiment(experiment, path)
    _clear_deployed_experiment_runtime_file()

    return JSONResponse(
        content={
            "status": "rolled_back",
            "id": experiment_id,
            "rolled_back_at": now.isoformat(),
        }
    )


@router.post("/admin/experiments/{experiment_id}/assignments")
async def admin_upsert_experiment_assignment(
    experiment_id: str,
    body: dict,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    path = _experiments_dir() / f"{experiment_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="experiment not found")

    tenant_id = str(body.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    rollout_percentage_raw = body.get("rollout_percentage", 0)
    try:
        rollout_percentage = int(rollout_percentage_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rollout_percentage must be integer")
    if not 0 <= rollout_percentage <= 100:
        raise HTTPException(status_code=400, detail="rollout_percentage must be within [0, 100]")

    now = datetime.now(timezone.utc)
    async with _async_session() as db:
        await db.execute(
            sql_text(
                "DELETE FROM experiment_assignments "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
        await db.execute(
            sql_text(
                "INSERT INTO experiment_assignments "
                "(tenant_id, experiment_id, rollout_percentage, rolled_out_at) "
                "VALUES (:tenant_id, :experiment_id, :rollout_percentage, :rolled_out_at)"
            ),
            {
                "tenant_id": tenant_id,
                "experiment_id": experiment_id,
                "rollout_percentage": rollout_percentage,
                "rolled_out_at": now,
            },
        )
        await db.commit()

    try:
        from agent.prompt_registry import set_assignment_cache_entry  # noqa: PLC0415

        set_assignment_cache_entry(tenant_id, experiment_id, rollout_percentage)
    except Exception:
        logger.debug("assignment cache update failed", exc_info=True)

    return JSONResponse(
        content={
            "assignment": {
                "tenant_id": tenant_id,
                "experiment_id": experiment_id,
                "rollout_percentage": rollout_percentage,
                "rolled_out_at": now.isoformat(),
            }
        }
    )


@router.get("/admin/experiments/{experiment_id}/assignments")
async def admin_list_experiment_assignments(
    experiment_id: str,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    async with _async_session() as db:
        result = await db.execute(
            sql_text(
                "SELECT tenant_id, experiment_id, rollout_percentage, rolled_out_at "
                "FROM experiment_assignments "
                "WHERE experiment_id = :experiment_id "
                "ORDER BY rolled_out_at DESC"
            ),
            {"experiment_id": experiment_id},
        )
        rows = list(result.mappings().all())

    assignments: list[dict[str, object]] = []
    for row in rows:
        record = dict(row)
        value = record.get("rolled_out_at")
        if hasattr(value, "isoformat"):
            record["rolled_out_at"] = value.isoformat()
        assignments.append(record)
    return JSONResponse(content={"assignments": assignments})

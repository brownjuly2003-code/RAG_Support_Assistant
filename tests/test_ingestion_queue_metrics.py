"""Plan step 4.5: observable ingestion queue age and alert contract."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from db.models import IngestionJob
from ingestion import jobs as jobs_mod
from ingestion import liveness
from monitoring import prometheus as prometheus_metrics

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _metric_value(metrics_text: str, name: str) -> float:
    match = re.search(rf"^{re.escape(name)}\s+([^\s]+)$", metrics_text, re.MULTILINE)
    assert match is not None, f"missing metric {name}"
    return float(match.group(1))


def _seed_job(
    *,
    now: datetime,
    status: str = "queued",
    celery_task_id: str | None = "task-1",
    created_age_sec: int = 0,
    ready_age_sec: int | None = None,
) -> None:
    with jobs_mod.sync_session() as session:
        session.add(
            IngestionJob(
                id=uuid.uuid4(),
                tenant_id="queue-metrics",
                filename="doc.txt",
                source_path="data/uploads/doc.txt",
                status=status,
                celery_task_id=celery_task_id,
                created_at=now - timedelta(seconds=created_age_sec),
                source_ready_at=(
                    None
                    if ready_age_sec is None
                    else now - timedelta(seconds=ready_age_sec)
                ),
            )
        )
        session.commit()


@pytest.mark.usefixtures("ingestion_jobs_db")
def test_reaper_exports_oldest_async_queued_age_without_tenant_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "900")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")

    _seed_job(now=now, created_age_sec=180, ready_age_sec=120)
    _seed_job(now=now, created_age_sec=90, ready_age_sec=60)
    _seed_job(now=now, created_age_sec=150)
    _seed_job(now=now, created_age_sec=600, celery_task_id=None)
    _seed_job(now=now, created_age_sec=500, status="running")

    liveness.reap_stale_jobs(now=now)

    metrics_text = prometheus_metrics.generate_latest(
        prometheus_metrics.REGISTRY
    ).decode("utf-8")
    assert _metric_value(metrics_text, "rag_ingestion_queue_oldest_seconds") == 150
    assert "rag_ingestion_queue_oldest_seconds{" not in metrics_text


@pytest.mark.usefixtures("ingestion_jobs_db")
def test_reaper_clears_queue_age_when_no_async_job_is_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setenv("INGESTION_JOB_QUEUED_STALE_SEC", "900")
    monkeypatch.setenv("INGESTION_JOB_LEGACY_RUNNING_STALE_SEC", "1800")
    prometheus_metrics.set_ingestion_queue_oldest(123)

    _seed_job(now=now, created_age_sec=500, status="completed")
    _seed_job(now=now, created_age_sec=500, celery_task_id=None)
    liveness.reap_stale_jobs(now=now)

    metrics_text = prometheus_metrics.generate_latest(
        prometheus_metrics.REGISTRY
    ).decode("utf-8")
    assert _metric_value(metrics_text, "rag_ingestion_queue_oldest_seconds") == 0


def test_ingestion_queue_stalled_alert_has_pre_timeout_window() -> None:
    rules_path = PROJECT_ROOT / "monitoring" / "alert_rules.yml"
    rules_doc = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    alerts = {
        rule["alert"]: rule
        for group in rules_doc["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }

    alert = alerts["IngestionQueueStalled"]
    expression = str(alert["expr"])
    assert "rag_ingestion_queue_oldest_seconds" in expression
    assert "> 300" in expression
    assert alert["for"] == "5m"
    assert alert["labels"]["severity"] == "warning"

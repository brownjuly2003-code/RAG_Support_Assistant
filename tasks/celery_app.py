"""Celery application config."""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rag_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    # ingest_task + outbox_retry_task (plan §4.6 escalation outbox schedule)
    include=["tasks.ingest_task", "tasks.outbox_retry_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    broker_connection_timeout=1,
    broker_connection_max_retries=0,
    redis_socket_connect_timeout=1,
    redis_socket_timeout=1,
    result_backend_max_retries=0,
    result_backend_transport_options={
        "retry_policy": {
            "max_retries": 0,
            "timeout": 1,
            "interval_start": 0,
            "interval_step": 0,
            "interval_max": 0,
        }
    },
)

# Plan §4.6: periodic escalation outbox retry (failed inbox deliveries).
# Requires a Celery beat process; worker alone does not fire the schedule.
# Disable registration with RAG_OUTBOX_RETRY_BEAT=false.
try:
    from tasks.outbox_retry_task import build_outbox_beat_schedule

    _outbox_beat = build_outbox_beat_schedule()
    if _outbox_beat:
        existing = dict(getattr(celery_app.conf, "beat_schedule", None) or {})
        existing.update(_outbox_beat)
        celery_app.conf.beat_schedule = existing
except Exception:
    # Import-time failures must not block ingest worker startup.
    pass

celery_app.autodiscover_tasks(["tasks"], related_name="ingest_task")
celery_app.autodiscover_tasks(["tasks"], related_name="outbox_retry_task")

app = celery_app

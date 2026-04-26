"""Celery application config."""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rag_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.ingest_task"],
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

celery_app.autodiscover_tasks(["tasks"], related_name="ingest_task")

app = celery_app

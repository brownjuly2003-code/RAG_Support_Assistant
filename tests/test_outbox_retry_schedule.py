"""Plan §4.6: escalation outbox retry schedule (Celery beat + CLI wire)."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tasks.outbox_retry_task import (
    TASK_NAME,
    build_outbox_beat_schedule,
    outbox_retry_beat_enabled_from_env,
    run_outbox_retry_once,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = PROJECT_ROOT / "docker-compose.yml"


def test_build_outbox_beat_schedule_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_OUTBOX_RETRY_BEAT", "true")
    monkeypatch.setenv("RAG_OUTBOX_RETRY_INTERVAL_SEC", "120")
    monkeypatch.setenv("RAG_OUTBOX_RETRY_BATCH_LIMIT", "25")
    monkeypatch.delenv("RAG_OUTBOX_RETRY_INCLUDE_PENDING", raising=False)
    schedule = build_outbox_beat_schedule()
    assert "escalation-outbox-retry" in schedule
    entry = schedule["escalation-outbox-retry"]
    assert entry["task"] == TASK_NAME
    assert entry["schedule"] == pytest.approx(120.0)
    assert entry["kwargs"]["limit"] == 25
    assert entry["kwargs"]["states"] == ["failed"]


def test_build_outbox_beat_schedule_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_OUTBOX_RETRY_BEAT", "false")
    assert build_outbox_beat_schedule() == {}
    assert outbox_retry_beat_enabled_from_env() is False


def test_build_outbox_beat_include_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_OUTBOX_RETRY_BEAT", "true")
    monkeypatch.setenv("RAG_OUTBOX_RETRY_INCLUDE_PENDING", "true")
    entry = build_outbox_beat_schedule()["escalation-outbox-retry"]
    assert entry["kwargs"]["states"] == ["failed", "pending"]


def test_run_outbox_retry_once_uses_sync_runner() -> None:
    calls: list[dict] = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            attempted=2,
            delivered=1,
            failed=1,
            skipped=0,
            results=[],
            as_dict=lambda: {
                "attempted": 2,
                "delivered": 1,
                "failed": 1,
                "skipped": 0,
                "results": [],
            },
        )

    payload = run_outbox_retry_once(
        limit=10,
        states=["failed", "pending"],
        tenant_id="acme",
        retry_fn=_fake,
    )
    assert calls == [{"limit": 10, "states": ["failed", "pending"], "tenant_id": "acme"}]
    assert payload["kind"] == "escalation-outbox-retry"
    assert payload["attempted"] == 2
    assert payload["delivered"] == 1
    assert payload["limit"] == 10


def test_celery_app_registers_outbox_task_and_beat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_OUTBOX_RETRY_BEAT", "true")
    monkeypatch.setenv("RAG_OUTBOX_RETRY_INTERVAL_SEC", "180")
    # Re-import celery app modules so conf picks env (fresh module state).
    import tasks.celery_app as celery_mod
    import tasks.outbox_retry_task as outbox_mod

    importlib.reload(outbox_mod)
    importlib.reload(celery_mod)

    app = celery_mod.celery_app
    # Task registered via include / shared_task
    registered = app.tasks
    assert TASK_NAME in registered or any(
        TASK_NAME in str(k) for k in registered
    ), f"task {TASK_NAME} not in {list(registered)[:20]}"

    beat = dict(getattr(app.conf, "beat_schedule", None) or {})
    assert "escalation-outbox-retry" in beat
    assert beat["escalation-outbox-retry"]["task"] == TASK_NAME
    assert beat["escalation-outbox-retry"]["schedule"] == pytest.approx(180.0)


def test_docker_compose_has_worker_beat() -> None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    assert "worker" in services
    assert "worker-beat" in services
    beat = services["worker-beat"]
    cmd = " ".join(beat.get("command") or [])
    assert "tasks.celery_app:celery_app" in cmd
    assert "beat" in cmd
    # Single schedule process — no host ports
    assert not beat.get("ports")
    env = beat.get("environment") or []
    env_text = "\n".join(str(x) for x in env)
    assert "RAG_OUTBOX_RETRY" in env_text
    worker_env = "\n".join(str(x) for x in (services["worker"].get("environment") or []))
    assert "RAG_OUTBOX_RETRY" in worker_env


def test_outbox_retry_cli_dry_run_config() -> None:
    script = PROJECT_ROOT / "scripts" / "outbox_retry.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--dry-run-config"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "RAG_OUTBOX_RETRY_BEAT": "true",
            "RAG_OUTBOX_RETRY_INTERVAL_SEC": "90",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "escalation-outbox-retry-config"
    assert payload["beat_enabled"] is True
    assert "escalation-outbox-retry" in payload["beat_schedule"]


def test_outbox_retry_cli_once_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.outbox_retry as cli

    report = tmp_path / "report.json"

    def _fake(**kwargs):
        return {
            "kind": "escalation-outbox-retry",
            "attempted": 1,
            "delivered": 1,
            "failed": 0,
            "skipped": 0,
            "results": [{"ticket_id": "t1"}],
            "limit": kwargs.get("limit"),
            "states": kwargs.get("states"),
            "tenant_id": kwargs.get("tenant_id"),
        }

    monkeypatch.setattr(cli, "run_outbox_retry_once", _fake)
    code = cli.main(["--limit", "3", "--include-pending", "--report", str(report)])
    assert code == 0
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["attempted"] == 1
    assert data["states"] == ["failed", "pending"]

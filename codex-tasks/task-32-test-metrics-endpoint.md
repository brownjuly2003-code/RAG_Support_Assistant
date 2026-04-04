# Task 32 — tests/test_metrics.py: покрытие GET /api/metrics

## Goal
`GET /api/metrics` не покрыт тестами. Добавить тесты в `tests/test_metrics.py`
с использованием TestClient (без реального SQLite — mock `get_metrics_snapshot`).

## Background
- `GET /api/metrics` роутер: `api/app.py`, рядом с `/api/health`
- Импортирует `from sqlite_trace import get_metrics_snapshot` внутри функции
- При Exception — возвращает `{"error": "...", "generated_at": ""}`
- При пустой БД — нули и None (тестируется через реальный вызов с in-memory DB)

## Files to create
- `tests/test_metrics.py`

---

## tests/test_metrics.py

```python
"""tests/test_metrics.py — тесты для GET /api/metrics."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app

CLIENT = TestClient(app, raise_server_exceptions=False)

MOCK_SNAPSHOT = {
    "latency": {"p50_sec": 1.5, "p95_sec": 8.2, "p99_sec": 14.0, "window": "24h"},
    "escalation": {"total_traces": 100, "escalated": 15, "rate_pct": 15.0, "window": "24h"},
    "quality": {"scored_traces": 90, "avg_quality": 78.5, "low_quality_share_pct": 10.0, "window": "7d"},
    "errors": {"total_started": 100, "likely_failed": 2, "likely_failure_rate_pct": 2.0, "window": "24h"},
    "feedback": {"total": 60, "thumbs_down": 8, "thumbs_down_rate_pct": 13.3, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}

EMPTY_SNAPSHOT = {
    "latency": {"p50_sec": None, "p95_sec": None, "p99_sec": None, "window": "24h"},
    "escalation": {"total_traces": 0, "escalated": 0, "rate_pct": None, "window": "24h"},
    "quality": {"scored_traces": 0, "avg_quality": None, "low_quality_share_pct": None, "window": "7d"},
    "errors": {"total_started": 0, "likely_failed": 0, "likely_failure_rate_pct": None, "window": "24h"},
    "feedback": {"total": 0, "thumbs_down": 0, "thumbs_down_rate_pct": None, "window": "7d"},
    "generated_at": "2025-01-01T00:00:00+00:00",
}


def test_metrics_returns_200():
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        resp = CLIENT.get("/api/metrics")
    assert resp.status_code == 200


def test_metrics_has_required_keys():
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        resp = CLIENT.get("/api/metrics")
    data = resp.json()
    for key in ("latency", "escalation", "quality", "errors", "feedback", "generated_at"):
        assert key in data, f"Missing key: {key}"


def test_metrics_latency_fields():
    with patch("sqlite_trace.get_metrics_snapshot", return_value=MOCK_SNAPSHOT):
        resp = CLIENT.get("/api/metrics")
    lat = resp.json()["latency"]
    assert lat["p50_sec"] == 1.5
    assert lat["p95_sec"] == 8.2
    assert lat["window"] == "24h"


def test_metrics_empty_db_returns_200():
    """При пустой БД — 200, нули, не 500."""
    with patch("sqlite_trace.get_metrics_snapshot", return_value=EMPTY_SNAPSHOT):
        resp = CLIENT.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latency"]["p50_sec"] is None
    assert data["escalation"]["total_traces"] == 0


def test_metrics_error_fallback():
    """При Exception в get_metrics_snapshot — возвращает dict с 'error', не 500."""
    with patch("sqlite_trace.get_metrics_snapshot", side_effect=RuntimeError("db locked")):
        resp = CLIENT.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
```

---

## CONSTRAINTS
- Создать только `tests/test_metrics.py`
- Использовать `unittest.mock.patch` — не трогать реальный SQLite
- `pytest tests/ -v` — проходит (все тесты, включая существующие 29)

## DONE WHEN
- [ ] `tests/test_metrics.py` создан
- [ ] 5 новых тестов проходят
- [ ] `pytest tests/ -v` — все тесты зелёные

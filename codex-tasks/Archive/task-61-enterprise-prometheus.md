# Task 61 — OBS-2: Prometheus /metrics endpoint

## Goal
Заменить кастомный JSON `/api/metrics` на стандартный Prometheus формат.
Grafana/Prometheus смогут scrape-ить метрики напрямую.

## Files to create
- `monitoring/__init__.py`
- `monitoring/prometheus.py` — Prometheus metrics registry

## Files to change
- `requirements.txt` — добавить prometheus-client
- `api/app.py` — добавить `/metrics` endpoint в Prometheus формате

---

## 1. requirements.txt

Добавить:
```
prometheus-client>=0.20.0
```

---

## 2. monitoring/__init__.py

```python
"""Monitoring — Prometheus metrics."""
```

---

## 3. monitoring/prometheus.py

```python
"""Prometheus metrics для RAG Support Assistant."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Summary

# Request metrics
REQUEST_COUNT = Counter(
    "rag_requests_total",
    "Total number of /api/ask requests",
    ["route"],  # auto, human, error
)

REQUEST_DURATION = Histogram(
    "rag_request_duration_seconds",
    "Request processing time",
    buckets=[0.5, 1, 2, 3, 5, 8, 10, 15, 30],
)

# Quality metrics
QUALITY_SCORE = Summary(
    "rag_quality_score",
    "Quality scores from self-evaluation",
)

ESCALATION_TOTAL = Counter(
    "rag_escalation_total",
    "Total escalations to human",
)

# Feedback metrics
FEEDBACK_COUNT = Counter(
    "rag_feedback_total",
    "Feedback events",
    ["rating"],  # up, down
)

# System metrics
ACTIVE_SESSIONS = Gauge(
    "rag_active_sessions",
    "Number of active sessions",
)

VECTOR_STORE_DOCS = Gauge(
    "rag_vector_store_documents",
    "Number of documents in vector store",
)
```

---

## 4. api/app.py

### Добавить Prometheus metrics endpoint

```python
@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint for scraping."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

### Инструментировать /api/ask

В начале обработки `/api/ask`:
```python
import time as _time
from monitoring.prometheus import (
    REQUEST_COUNT, REQUEST_DURATION, QUALITY_SCORE,
    ESCALATION_TOTAL, ACTIVE_SESSIONS,
)

t0 = _time.monotonic()
```

В конце, после получения результата:
```python
duration = _time.monotonic() - t0
REQUEST_DURATION.observe(duration)
REQUEST_COUNT.labels(route=result.get("route", "auto")).inc()

quality = result.get("quality_score", 0)
if quality:
    QUALITY_SCORE.observe(quality)

if result.get("route") == "human":
    ESCALATION_TOTAL.inc()

ACTIVE_SESSIONS.set(len(_sessions))
```

### Инструментировать /api/feedback

```python
from monitoring.prometheus import FEEDBACK_COUNT
FEEDBACK_COUNT.labels(rating=body.rating).inc()
```

---

## 5. .env.example

Добавить:
```
# Prometheus metrics are exposed at GET /metrics (no auth)
```

---

## CONSTRAINTS
- `GET /metrics` возвращает text/plain в Prometheus exposition format
- Существующий `GET /api/metrics` (JSON) остаётся без изменений
- `/metrics` без auth (стандарт для Prometheus scraping)
- Graceful: если prometheus-client не установлен — `/metrics` возвращает 501
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `GET /metrics` → Prometheus format (`rag_requests_total`, `rag_request_duration_seconds` и т.д.)
- [ ] `/api/ask` инструментирован: каждый запрос → counter + histogram
- [ ] `/api/feedback` инструментирован: up/down counter
- [ ] Существующий `/api/metrics` (JSON) работает
- [ ] `pytest tests/ -v` — проходит

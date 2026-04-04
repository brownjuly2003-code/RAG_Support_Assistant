# Task 28 — GET /api/metrics: SQLite aggregate helpers

## Goal
Добавить endpoint `GET /api/metrics` — JSON-снапшот здоровья системы
на основе агрегатов из SQLite (`traces` + `feedback`).
SQL-запросы взяты напрямую из `docs/research/production-monitoring-2025.md`.

## Files to change
- `sqlite_trace.py` — добавить `get_metrics_snapshot()`
- `api/app.py` — добавить `GET /api/metrics`

---

## 1. sqlite_trace.py

Добавить функцию после `get_feedback_stats()`:

```python
def get_metrics_snapshot() -> dict:
    """Агрегированный снапшот метрик здоровья сервиса.

    Возвращает:
    {
        "latency": {
            "p50_sec": float | None,
            "p95_sec": float | None,
            "p99_sec": float | None,
            "window": "24h",
        },
        "escalation": {
            "total_traces": int,
            "escalated": int,
            "rate_pct": float | None,
            "window": "24h",
        },
        "quality": {
            "scored_traces": int,
            "avg_quality": float | None,
            "low_quality_share_pct": float | None,
            "window": "7d",
        },
        "errors": {
            "total_started": int,
            "likely_failed": int,
            "likely_failure_rate_pct": float | None,
            "window": "24h",
        },
        "feedback": {
            "total": int,
            "thumbs_down": int,
            "thumbs_down_rate_pct": float | None,
            "window": "7d",
        },
        "generated_at": str,  # ISO 8601 UTC
    }
    """
    with _get_connection() as conn:
        cur = conn.cursor()

        # --- latency p50/p95/p99 за 24h ---
        cur.execute("""
            WITH latencies AS (
                SELECT (julianday(finished_at) - julianday(started_at)) * 86400.0 AS s
                FROM traces
                WHERE finished_at IS NOT NULL
                  AND julianday(started_at) >= julianday('now', '-1 day')
            ),
            ranked AS (
                SELECT s, ROW_NUMBER() OVER (ORDER BY s) AS rn, COUNT(*) OVER () AS total
                FROM latencies
            )
            SELECT
                ROUND(MIN(CASE WHEN rn >= total * 0.50 THEN s END), 2) AS p50,
                ROUND(MIN(CASE WHEN rn >= total * 0.95 THEN s END), 2) AS p95,
                ROUND(MIN(CASE WHEN rn >= total * 0.99 THEN s END), 2) AS p99
            FROM ranked
        """)
        row = cur.fetchone()
        latency = {
            "p50_sec": row[0] if row else None,
            "p95_sec": row[1] if row else None,
            "p99_sec": row[2] if row else None,
            "window": "24h",
        }

        # --- escalation rate за 24h ---
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END) AS escalated,
                ROUND(100.0 * SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0), 1) AS rate_pct
            FROM traces
            WHERE julianday(started_at) >= julianday('now', '-1 day')
        """)
        row = cur.fetchone() or (0, 0, None)
        escalation = {"total_traces": row[0], "escalated": row[1], "rate_pct": row[2], "window": "24h"}

        # --- quality за 7d ---
        cur.execute("""
            SELECT
                COUNT(final_quality) AS scored,
                ROUND(AVG(final_quality), 1) AS avg_q,
                ROUND(100.0 * SUM(CASE WHEN final_quality < 60 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(final_quality), 0), 1) AS low_share
            FROM traces
            WHERE final_quality IS NOT NULL
              AND julianday(started_at) >= julianday('now', '-7 day')
        """)
        row = cur.fetchone() or (0, None, None)
        quality = {"scored_traces": row[0], "avg_quality": row[1], "low_quality_share_pct": row[2], "window": "7d"}

        # --- error proxy за 24h ---
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN finished_at IS NULL
                          AND julianday(started_at) < julianday('now', '-15 minute')
                         THEN 1 ELSE 0 END) AS failed,
                ROUND(100.0 * SUM(CASE WHEN finished_at IS NULL
                          AND julianday(started_at) < julianday('now', '-15 minute')
                         THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS rate
            FROM traces
            WHERE julianday(started_at) >= julianday('now', '-1 day')
        """)
        row = cur.fetchone() or (0, 0, None)
        errors = {"total_started": row[0], "likely_failed": row[1], "likely_failure_rate_pct": row[2], "window": "24h"}

        # --- feedback за 7d ---
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END) AS thumbs_down,
                ROUND(100.0 * SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0), 1) AS rate
            FROM feedback
            WHERE julianday(ts) >= julianday('now', '-7 day')
        """)
        row = cur.fetchone() or (0, 0, None)
        feedback = {"total": row[0], "thumbs_down": row[1], "thumbs_down_rate_pct": row[2], "window": "7d"}

    return {
        "latency": latency,
        "escalation": escalation,
        "quality": quality,
        "errors": errors,
        "feedback": feedback,
        "generated_at": _now_iso(),
    }
```

---

## 2. api/app.py

Добавить endpoint рядом с `/api/health`:

```python
@router.get("/metrics")
async def get_metrics() -> dict:
    """Агрегированный JSON-снапшот метрик здоровья системы.

    Покрывает: latency (p50/p95/p99), escalation rate, quality scores,
    error proxy, thumbs-down rate. Все данные из SQLite.
    """
    try:
        from sqlite_trace import get_metrics_snapshot  # noqa: PLC0415
        return get_metrics_snapshot()
    except Exception as exc:
        logger.warning("Failed to get metrics: %s", exc)
        return {"error": str(exc), "generated_at": ""}
```

---

## CONSTRAINTS
- Изменить только `sqlite_trace.py` и `api/app.py`
- При пустой БД (нет трасс) — не падать, возвращать нули и None
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `get_metrics_snapshot()` существует в `sqlite_trace.py`
- [ ] `GET /api/metrics` возвращает JSON с ключами `latency`, `escalation`, `quality`, `errors`, `feedback`
- [ ] При пустой БД — 200, нули, не 500
- [ ] `pytest tests/ -v` — проходит

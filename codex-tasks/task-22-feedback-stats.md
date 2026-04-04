# Task 22 — Feedback stats endpoint + отображение в UI

## Goal
Закрыть loop: фидбек собирается (task-15), но нигде не отображается.
Добавить `GET /api/feedback/stats` и минимальный вывод статистики в help.html.

## Files to change
- `sqlite_trace.py` — добавить `get_feedback_stats()`
- `api/app.py` — добавить `GET /api/feedback/stats`
- `static/help.html` — добавить секцию со статистикой (загружается динамически)

---

## 1. sqlite_trace.py

Добавить функцию после `save_feedback()`:

```python
def get_feedback_stats(days: int = 30) -> dict:
    """Агрегированная статистика фидбека за последние N дней.

    Returns:
        {
            "total": int,
            "up": int,
            "down": int,
            "up_pct": float,          # процент положительных
            "by_route": {             # разбивка по маршруту (через JOIN с traces)
                "auto": {"up": int, "down": int},
                "human": {"up": int, "down": int},
            },
            "period_days": int,
        }
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    with _get_connection() as conn:
        cur = conn.cursor()

        # Общие счётчики
        cur.execute(
            "SELECT rating, COUNT(*) FROM feedback WHERE ts >= ? GROUP BY rating",
            (cutoff,),
        )
        counts = dict(cur.fetchall())
        up = counts.get("up", 0)
        down = counts.get("down", 0)
        total = up + down
        up_pct = round(up / total * 100, 1) if total else 0.0

        # По маршруту через JOIN
        cur.execute(
            """
            SELECT t.final_route, f.rating, COUNT(*)
            FROM feedback f
            LEFT JOIN traces t ON f.trace_id = t.trace_id
            WHERE f.ts >= ?
            GROUP BY t.final_route, f.rating
            """,
            (cutoff,),
        )
        by_route: dict = {}
        for route, rating, cnt in cur.fetchall():
            r = route or "unknown"
            if r not in by_route:
                by_route[r] = {"up": 0, "down": 0}
            if rating in ("up", "down"):
                by_route[r][rating] += cnt

    return {
        "total": total,
        "up": up,
        "down": down,
        "up_pct": up_pct,
        "by_route": by_route,
        "period_days": days,
    }
```

---

## 2. api/app.py

Добавить endpoint рядом с `/api/feedback`:

```python
@router.get("/feedback/stats")
async def feedback_stats(days: int = 30) -> dict:
    """Статистика фидбека за последние N дней."""
    try:
        from sqlite_trace import get_feedback_stats  # noqa: PLC0415
        return get_feedback_stats(days=days)
    except Exception as exc:
        logger.warning("Failed to get feedback stats: %s", exc)
        return {"total": 0, "up": 0, "down": 0, "up_pct": 0.0, "by_route": {}, "period_days": days}
```

---

## 3. static/help.html

Добавить секцию перед `<a href="/chat" class="back-link">`:

```html
<section id="statsSection" style="display:none">
    <h2>Статистика ответов</h2>
    <p id="statsText" style="color:var(--text-secondary);font-size:14px">Загрузка...</p>
</section>
```

Добавить в конец `<body>` (перед `</body>`):

```html
<script>
(async () => {
    try {
        const resp = await fetch('/api/feedback/stats?days=30');
        if (!resp.ok) return;
        const d = await resp.json();
        if (d.total === 0) return;
        document.getElementById('statsSection').style.display = '';
        document.getElementById('statsText').textContent =
            `За 30 дней: ${d.total} оценок, ${d.up_pct}% положительных. `
            + `Авто-ответы: ${(d.by_route?.auto?.up||0)} 👍 / ${(d.by_route?.auto?.down||0)} 👎. `
            + `Эскалации: ${(d.by_route?.human?.up||0)} 👍 / ${(d.by_route?.human?.down||0)} 👎.`;
    } catch (_) {}
})();
</script>
```

---

## CONSTRAINTS
- Изменить только `sqlite_trace.py`, `api/app.py`, `static/help.html`
- Секция статистики в help.html скрыта если `total === 0` (нет фидбека)
- Ошибки в endpoint → fallback-объект с нулями, не 500
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `GET /api/feedback/stats` возвращает JSON с `total`, `up`, `down`, `up_pct`, `by_route`
- [ ] При `total=0` секция в help.html скрыта
- [ ] При наличии фидбека — отображается текст со статистикой
- [ ] `pytest tests/ -v` — проходит

# Task 29 — scripts/check_alerts.py: scheduled alert checker

## Goal
Скрипт, который запускается каждые 5 минут (cron или systemd timer),
проверяет метрики против порогов и отправляет webhook при нарушениях.
Hysteresis: алерт только если порог нарушен 2 запуска подряд.

## Prerequisite
task-28 должен быть выполнен — нужен `get_metrics_snapshot()` в sqlite_trace.py.

## Files to create
- `scripts/check_alerts.py`
- `scripts/README.md` — как запустить и настроить

## Env-переменные (добавить в .env.example)
```dotenv
# Alerting thresholds (used by scripts/check_alerts.py)
ALERT_WEBHOOK_URL=          # Slack/Telegram webhook, пусто = только лог
ALERT_ESCALATION_PCT=35     # alert if escalation_rate > N%
ALERT_QUALITY_MIN=65        # alert if avg_quality < N
ALERT_LOW_QUALITY_PCT=30    # alert if low_quality_share > N%
ALERT_P95_LATENCY_SEC=12    # alert if p95 > N seconds
ALERT_THUMBS_DOWN_PCT=20    # alert if thumbs_down_rate > N% (при >= 50 feedback)
ALERT_THUMBS_DOWN_MIN_N=50  # minimum feedback count to fire thumbs-down alert
```

---

## scripts/check_alerts.py

```python
#!/usr/bin/env python3
"""
scripts/check_alerts.py

Проверяет метрики из SQLite против порогов и отправляет webhook при нарушениях.

Запуск:
    python scripts/check_alerts.py
    python scripts/check_alerts.py --dry-run   # только вывод, без webhook

Cron (каждые 5 минут):
    */5 * * * * cd /path/to/project && python scripts/check_alerts.py >> data/alerts.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlite_trace import get_metrics_snapshot

# ---------------------------------------------------------------------------
# Конфиг из env
# ---------------------------------------------------------------------------
WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
THRESH_ESCALATION_PCT: float = float(os.getenv("ALERT_ESCALATION_PCT", "35"))
THRESH_QUALITY_MIN: float = float(os.getenv("ALERT_QUALITY_MIN", "65"))
THRESH_LOW_QUALITY_PCT: float = float(os.getenv("ALERT_LOW_QUALITY_PCT", "30"))
THRESH_P95_SEC: float = float(os.getenv("ALERT_P95_LATENCY_SEC", "12"))
THRESH_THUMBS_DOWN_PCT: float = float(os.getenv("ALERT_THUMBS_DOWN_PCT", "20"))
THRESH_THUMBS_DOWN_MIN_N: int = int(os.getenv("ALERT_THUMBS_DOWN_MIN_N", "50"))

# Файл состояния для hysteresis (алерт только если нарушение 2 раза подряд)
STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "alerts_state.json"
ALERT_LOG = Path(__file__).resolve().parent.parent / "data" / "alerts.log"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _check_thresholds(m: dict) -> list[dict]:
    """Возвращает список нарушенных правил."""
    violations = []

    esc = m.get("escalation", {})
    if (esc.get("rate_pct") or 0) > THRESH_ESCALATION_PCT:
        violations.append({
            "rule": "escalation_rate",
            "value": esc["rate_pct"],
            "threshold": THRESH_ESCALATION_PCT,
            "message": f"Escalation rate {esc['rate_pct']}% > {THRESH_ESCALATION_PCT}% (24h)",
        })

    q = m.get("quality", {})
    avg_q = q.get("avg_quality")
    if avg_q is not None and avg_q < THRESH_QUALITY_MIN:
        violations.append({
            "rule": "avg_quality",
            "value": avg_q,
            "threshold": THRESH_QUALITY_MIN,
            "message": f"Avg quality {avg_q} < {THRESH_QUALITY_MIN} (7d)",
        })
    low_q = q.get("low_quality_share_pct")
    if low_q is not None and low_q > THRESH_LOW_QUALITY_PCT:
        violations.append({
            "rule": "low_quality_share",
            "value": low_q,
            "threshold": THRESH_LOW_QUALITY_PCT,
            "message": f"Low-quality share {low_q}% > {THRESH_LOW_QUALITY_PCT}% (7d)",
        })

    lat = m.get("latency", {})
    p95 = lat.get("p95_sec")
    if p95 is not None and p95 > THRESH_P95_SEC:
        violations.append({
            "rule": "p95_latency",
            "value": p95,
            "threshold": THRESH_P95_SEC,
            "message": f"p95 latency {p95}s > {THRESH_P95_SEC}s (24h)",
        })

    fb = m.get("feedback", {})
    td_rate = fb.get("thumbs_down_rate_pct")
    if td_rate is not None and fb.get("total", 0) >= THRESH_THUMBS_DOWN_MIN_N and td_rate > THRESH_THUMBS_DOWN_PCT:
        violations.append({
            "rule": "thumbs_down_rate",
            "value": td_rate,
            "threshold": THRESH_THUMBS_DOWN_PCT,
            "message": f"Thumbs-down rate {td_rate}% > {THRESH_THUMBS_DOWN_PCT}% (7d, n={fb['total']})",
        })

    return violations


def _send_webhook(violations: list[dict], dry_run: bool) -> None:
    """Отправляет Slack/Telegram webhook."""
    lines = ["🚨 *RAG Support Assistant — Alert*", ""]
    for v in violations:
        lines.append(f"• {v['message']}")
    lines += ["", f"_Generated: {datetime.now(timezone.utc).isoformat()}_"]
    text = "\n".join(lines)

    print(text)

    if dry_run or not WEBHOOK_URL:
        print("[dry-run] Webhook not sent.")
        return

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
        print("[alert] Webhook sent.")
    except Exception as exc:
        print(f"[alert] Webhook failed: {exc}")


def _write_log(violations: list[dict]) -> None:
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        for v in violations:
            f.write(json.dumps({"ts": ts, "rule": v["rule"], "value": v["value"],
                                "threshold": v["threshold"]}) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    metrics = get_metrics_snapshot()
    violations = _check_thresholds(metrics)

    # Hysteresis: алерт только если нарушение 2 раза подряд
    state = _load_state()
    new_state: dict = {}
    to_alert = []

    for v in violations:
        rule = v["rule"]
        prev_count = state.get(rule, 0)
        new_count = prev_count + 1
        new_state[rule] = new_count
        if new_count >= 2:
            to_alert.append(v)

    # Сбросить счётчики для правил, которые больше не нарушены
    for rule in state:
        if rule not in new_state:
            new_state[rule] = 0

    _save_state(new_state)

    if not violations:
        print(f"[{datetime.now(timezone.utc).isoformat()}] All OK.")
        return

    print(f"[{datetime.now(timezone.utc).isoformat()}] "
          f"Violations: {[v['rule'] for v in violations]} | "
          f"Alerting: {[v['rule'] for v in to_alert]}")

    if to_alert:
        _send_webhook(to_alert, dry_run=args.dry_run)
        _write_log(to_alert)


if __name__ == "__main__":
    main()
```

---

## scripts/README.md

```markdown
# scripts/

## check_alerts.py — мониторинг метрик

Проверяет метрики из SQLite против порогов. Запускай каждые 5 минут через cron.

### Запуск вручную
```bash
python scripts/check_alerts.py
python scripts/check_alerts.py --dry-run   # без webhook
```

### Cron
```cron
*/5 * * * * cd /path/to/rag-support-assistant && \
  python scripts/check_alerts.py >> data/alerts.log 2>&1
```

### Настройка (в .env)
| Переменная | По умолчанию | Описание |
|---|---|---|
| `ALERT_WEBHOOK_URL` | пусто | Slack/Telegram incoming webhook |
| `ALERT_ESCALATION_PCT` | 35 | % эскалаций (24h) |
| `ALERT_QUALITY_MIN` | 65 | минимальный avg quality (7d) |
| `ALERT_LOW_QUALITY_PCT` | 30 | % ответов quality < 60 (7d) |
| `ALERT_P95_LATENCY_SEC` | 12 | p95 latency в секундах (24h) |
| `ALERT_THUMBS_DOWN_PCT` | 20 | % thumbs-down (7d, при >= 50 fb) |

Состояние hysteresis: `data/alerts_state.json`.
Лог алертов: `data/alerts.log`.
```
```

---

## Также: добавить в .env.example

```dotenv
# Alerting thresholds (scripts/check_alerts.py)
ALERT_WEBHOOK_URL=
ALERT_ESCALATION_PCT=35
ALERT_QUALITY_MIN=65
ALERT_LOW_QUALITY_PCT=30
ALERT_P95_LATENCY_SEC=12
ALERT_THUMBS_DOWN_PCT=20
ALERT_THUMBS_DOWN_MIN_N=50
```

---

## CONSTRAINTS
- Создать `scripts/check_alerts.py` и `scripts/README.md`
- Добавить переменные в `.env.example`
- НЕ изменять `api/app.py`, `sqlite_trace.py` или другие модули
- При пустой БД или отсутствии `ALERT_WEBHOOK_URL` — только stdout, не падать
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `scripts/check_alerts.py` создан
- [ ] `python scripts/check_alerts.py --dry-run` запускается без ошибок
- [ ] При нарушении порога 2+ раза подряд — выводит алерт в stdout
- [ ] `data/alerts_state.json` создаётся при запуске
- [ ] `.env.example` содержит ALERT_* переменные
- [ ] `pytest tests/ -v` — проходит

# Task 33 — tests/test_check_alerts.py: unit-тесты alert checker

## Goal
`scripts/check_alerts.py` не покрыт тестами. Добавить unit-тесты
для `_check_thresholds()` и логики hysteresis без реального SQLite и webhook.

## Background
- `scripts/check_alerts.py` содержит:
  - `_check_thresholds(m: dict) -> list[dict]` — возвращает список нарушений
  - `_load_state() / _save_state(state)` — JSON-файл hysteresis
  - `main()` — вызывает `get_metrics_snapshot()`, затем логику алертов
- Hysteresis: алерт только если счётчик правила >= 2

## Files to create
- `tests/test_check_alerts.py`

---

## tests/test_check_alerts.py

```python
"""tests/test_check_alerts.py — unit-тесты для scripts/check_alerts.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.check_alerts as ca


# ---------------------------------------------------------------------------
# _check_thresholds
# ---------------------------------------------------------------------------

def _metrics(
    esc_pct=10.0, avg_q=80.0, low_q=10.0, p95=5.0, td_rate=5.0, td_total=60
) -> dict:
    return {
        "escalation": {"rate_pct": esc_pct},
        "quality": {"avg_quality": avg_q, "low_quality_share_pct": low_q},
        "latency": {"p95_sec": p95},
        "feedback": {"thumbs_down_rate_pct": td_rate, "total": td_total},
    }


def test_no_violations_when_all_ok():
    assert ca._check_thresholds(_metrics()) == []


def test_escalation_violation():
    v = ca._check_thresholds(_metrics(esc_pct=40.0))
    rules = [x["rule"] for x in v]
    assert "escalation_rate" in rules


def test_avg_quality_violation():
    v = ca._check_thresholds(_metrics(avg_q=50.0))
    rules = [x["rule"] for x in v]
    assert "avg_quality" in rules


def test_p95_latency_violation():
    v = ca._check_thresholds(_metrics(p95=15.0))
    rules = [x["rule"] for x in v]
    assert "p95_latency" in rules


def test_thumbs_down_violation():
    v = ca._check_thresholds(_metrics(td_rate=25.0, td_total=60))
    rules = [x["rule"] for x in v]
    assert "thumbs_down_rate" in rules


def test_thumbs_down_skipped_when_too_few_feedback():
    """Алерт thumbs_down не срабатывает при < THRESH_THUMBS_DOWN_MIN_N."""
    v = ca._check_thresholds(_metrics(td_rate=99.0, td_total=5))
    rules = [x["rule"] for x in v]
    assert "thumbs_down_rate" not in rules


# ---------------------------------------------------------------------------
# Hysteresis via main()
# ---------------------------------------------------------------------------

def test_hysteresis_no_alert_on_first_violation(tmp_path, monkeypatch):
    """Первое нарушение — не алертим."""
    monkeypatch.setattr(ca, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ca, "ALERT_LOG", tmp_path / "alerts.log")

    bad_metrics = _metrics(esc_pct=40.0)
    sent = []

    with patch("scripts.check_alerts.get_metrics_snapshot", return_value=bad_metrics), \
         patch("scripts.check_alerts._send_webhook", side_effect=lambda v, dr: sent.extend(v)), \
         patch("sys.argv", ["check_alerts.py", "--dry-run"]):
        ca.main()

    assert sent == [], "Не должно быть алерта на первом нарушении"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state.get("escalation_rate", 0) == 1


def test_hysteresis_alert_on_second_violation(tmp_path, monkeypatch):
    """Второе нарушение подряд — алертим."""
    monkeypatch.setattr(ca, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ca, "ALERT_LOG", tmp_path / "alerts.log")

    bad_metrics = _metrics(esc_pct=40.0)
    sent = []

    def run():
        with patch("scripts.check_alerts.get_metrics_snapshot", return_value=bad_metrics), \
             patch("scripts.check_alerts._send_webhook", side_effect=lambda v, dr: sent.extend(v)), \
             patch("sys.argv", ["check_alerts.py", "--dry-run"]):
            ca.main()

    run()  # первый запуск — нет алерта
    run()  # второй запуск — алерт

    assert any(v["rule"] == "escalation_rate" for v in sent), "Алерт должен сработать на 2-м нарушении"


def test_all_ok_resets_counter(tmp_path, monkeypatch):
    """После OK-запуска счётчик сбрасывается."""
    monkeypatch.setattr(ca, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ca, "ALERT_LOG", tmp_path / "alerts.log")

    (tmp_path / "state.json").write_text(json.dumps({"escalation_rate": 1}))

    with patch("scripts.check_alerts.get_metrics_snapshot", return_value=_metrics()), \
         patch("scripts.check_alerts._send_webhook"), \
         patch("sys.argv", ["check_alerts.py", "--dry-run"]):
        ca.main()

    state = json.loads((tmp_path / "state.json").read_text())
    assert state.get("escalation_rate", 0) == 0
```

---

## CONSTRAINTS
- Создать только `tests/test_check_alerts.py`
- Не менять `scripts/check_alerts.py`
- `pytest tests/ -v` — все тесты зелёные (включая существующие)

## DONE WHEN
- [ ] `tests/test_check_alerts.py` создан
- [ ] 9 новых тестов проходят
- [ ] Hysteresis: first violation = no alert, second = alert, reset on OK
- [ ] `pytest tests/ -v` — все тесты зелёные

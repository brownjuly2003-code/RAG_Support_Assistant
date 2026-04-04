from __future__ import annotations

import json
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _install_sqlite_trace_stub() -> None:
    module = sys.modules.get("sqlite_trace")
    if module is None:
        module = types.ModuleType("sqlite_trace")
        sys.modules["sqlite_trace"] = module

    module.get_metrics_snapshot = getattr(module, "get_metrics_snapshot", lambda: {})


_install_sqlite_trace_stub()

import scripts.check_alerts as ca


def _metrics(
    esc_pct: float = 10.0,
    avg_q: float = 80.0,
    low_q: float = 10.0,
    p95: float = 5.0,
    td_rate: float = 5.0,
    td_total: int = 60,
) -> dict:
    return {
        "escalation": {"rate_pct": esc_pct},
        "quality": {"avg_quality": avg_q, "low_quality_share_pct": low_q},
        "latency": {"p95_sec": p95},
        "feedback": {"thumbs_down_rate_pct": td_rate, "total": td_total},
    }


def test_no_violations_when_all_ok() -> None:
    assert ca._check_thresholds(_metrics()) == []


def test_escalation_violation() -> None:
    violations = ca._check_thresholds(_metrics(esc_pct=40.0))
    rules = [item["rule"] for item in violations]
    assert "escalation_rate" in rules


def test_avg_quality_violation() -> None:
    violations = ca._check_thresholds(_metrics(avg_q=50.0))
    rules = [item["rule"] for item in violations]
    assert "avg_quality" in rules


def test_low_quality_share_violation() -> None:
    violations = ca._check_thresholds(_metrics(low_q=40.0))
    rules = [item["rule"] for item in violations]
    assert "low_quality_share" in rules


def test_p95_latency_violation() -> None:
    violations = ca._check_thresholds(_metrics(p95=15.0))
    rules = [item["rule"] for item in violations]
    assert "p95_latency" in rules


def test_thumbs_down_violation() -> None:
    violations = ca._check_thresholds(_metrics(td_rate=25.0, td_total=60))
    rules = [item["rule"] for item in violations]
    assert "thumbs_down_rate" in rules


def test_thumbs_down_skipped_when_too_few_feedback() -> None:
    violations = ca._check_thresholds(_metrics(td_rate=99.0, td_total=5))
    rules = [item["rule"] for item in violations]
    assert "thumbs_down_rate" not in rules


def test_hysteresis_no_alert_on_first_violation(monkeypatch) -> None:
    suffix = uuid.uuid4().hex
    state_path = Path.cwd() / f"test-alert-state-{suffix}.json"
    alert_path = Path.cwd() / f"test-alert-log-{suffix}.log"
    monkeypatch.setattr(ca, "STATE_FILE", state_path)
    monkeypatch.setattr(ca, "ALERT_LOG", alert_path)

    sent: list[dict] = []

    try:
        with (
            patch("scripts.check_alerts.get_metrics_snapshot", return_value=_metrics(esc_pct=40.0)),
            patch("scripts.check_alerts._send_webhook", side_effect=lambda violations, dry_run: sent.extend(violations)),
            patch("sys.argv", ["check_alerts.py", "--dry-run"]),
        ):
            ca.main()

        assert sent == []
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state.get("escalation_rate", 0) == 1
    finally:
        state_path.unlink(missing_ok=True)
        alert_path.unlink(missing_ok=True)


def test_hysteresis_alert_on_second_violation(monkeypatch) -> None:
    suffix = uuid.uuid4().hex
    state_path = Path.cwd() / f"test-alert-state-{suffix}.json"
    alert_path = Path.cwd() / f"test-alert-log-{suffix}.log"
    monkeypatch.setattr(ca, "STATE_FILE", state_path)
    monkeypatch.setattr(ca, "ALERT_LOG", alert_path)

    sent: list[dict] = []

    def run() -> None:
        with (
            patch("scripts.check_alerts.get_metrics_snapshot", return_value=_metrics(esc_pct=40.0)),
            patch("scripts.check_alerts._send_webhook", side_effect=lambda violations, dry_run: sent.extend(violations)),
            patch("sys.argv", ["check_alerts.py", "--dry-run"]),
        ):
            ca.main()

    try:
        run()
        run()

        assert any(item["rule"] == "escalation_rate" for item in sent)
    finally:
        state_path.unlink(missing_ok=True)
        alert_path.unlink(missing_ok=True)


def test_all_ok_resets_counter(monkeypatch) -> None:
    suffix = uuid.uuid4().hex
    state_path = Path.cwd() / f"test-alert-state-{suffix}.json"
    alert_path = Path.cwd() / f"test-alert-log-{suffix}.log"
    monkeypatch.setattr(ca, "STATE_FILE", state_path)
    monkeypatch.setattr(ca, "ALERT_LOG", alert_path)

    try:
        state_path.write_text(
            json.dumps({"escalation_rate": 1}),
            encoding="utf-8",
            newline="\n",
        )

        with (
            patch("scripts.check_alerts.get_metrics_snapshot", return_value=_metrics()),
            patch("scripts.check_alerts._send_webhook"),
            patch("sys.argv", ["check_alerts.py", "--dry-run"]),
        ):
            ca.main()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state.get("escalation_rate", 0) == 0
    finally:
        state_path.unlink(missing_ok=True)
        alert_path.unlink(missing_ok=True)

#!/usr/bin/env python3
"""
scripts/check_alerts.py

Проверяет метрики из SQLite против порогов и отправляет webhook при нарушениях.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracing.sqlite_trace import get_metrics_snapshot

WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
THRESH_ESCALATION_PCT: float = float(os.getenv("ALERT_ESCALATION_PCT", "35"))
THRESH_QUALITY_MIN: float = float(os.getenv("ALERT_QUALITY_MIN", "65"))
THRESH_LOW_QUALITY_PCT: float = float(os.getenv("ALERT_LOW_QUALITY_PCT", "30"))
THRESH_P95_SEC: float = float(os.getenv("ALERT_P95_LATENCY_SEC", "12"))
THRESH_THUMBS_DOWN_PCT: float = float(os.getenv("ALERT_THUMBS_DOWN_PCT", "20"))
THRESH_THUMBS_DOWN_MIN_N: int = int(os.getenv("ALERT_THUMBS_DOWN_MIN_N", "50"))

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "alerts_state.json"
ALERT_LOG = Path(__file__).resolve().parent.parent / "data" / "alerts.log"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8", newline="\n")


def _check_thresholds(metrics: dict) -> list[dict]:
    violations: list[dict] = []

    escalation = metrics.get("escalation", {})
    if (escalation.get("rate_pct") or 0) > THRESH_ESCALATION_PCT:
        violations.append(
            {
                "rule": "escalation_rate",
                "value": escalation["rate_pct"],
                "threshold": THRESH_ESCALATION_PCT,
                "message": (
                    f"Escalation rate {escalation['rate_pct']}% > "
                    f"{THRESH_ESCALATION_PCT}% (24h)"
                ),
            }
        )

    quality = metrics.get("quality", {})
    avg_quality = quality.get("avg_quality")
    if avg_quality is not None and avg_quality < THRESH_QUALITY_MIN:
        violations.append(
            {
                "rule": "avg_quality",
                "value": avg_quality,
                "threshold": THRESH_QUALITY_MIN,
                "message": f"Avg quality {avg_quality} < {THRESH_QUALITY_MIN} (7d)",
            }
        )

    low_quality_share = quality.get("low_quality_share_pct")
    if low_quality_share is not None and low_quality_share > THRESH_LOW_QUALITY_PCT:
        violations.append(
            {
                "rule": "low_quality_share",
                "value": low_quality_share,
                "threshold": THRESH_LOW_QUALITY_PCT,
                "message": (
                    f"Low-quality share {low_quality_share}% > "
                    f"{THRESH_LOW_QUALITY_PCT}% (7d)"
                ),
            }
        )

    latency = metrics.get("latency", {})
    p95 = latency.get("p95_sec")
    if p95 is not None and p95 > THRESH_P95_SEC:
        violations.append(
            {
                "rule": "p95_latency",
                "value": p95,
                "threshold": THRESH_P95_SEC,
                "message": f"p95 latency {p95}s > {THRESH_P95_SEC}s (24h)",
            }
        )

    feedback = metrics.get("feedback", {})
    thumbs_down_rate = feedback.get("thumbs_down_rate_pct")
    if (
        thumbs_down_rate is not None
        and feedback.get("total", 0) >= THRESH_THUMBS_DOWN_MIN_N
        and thumbs_down_rate > THRESH_THUMBS_DOWN_PCT
    ):
        violations.append(
            {
                "rule": "thumbs_down_rate",
                "value": thumbs_down_rate,
                "threshold": THRESH_THUMBS_DOWN_PCT,
                "message": (
                    f"Thumbs-down rate {thumbs_down_rate}% > "
                    f"{THRESH_THUMBS_DOWN_PCT}% (7d, n={feedback['total']})"
                ),
            }
        )

    return violations


def _send_webhook(violations: list[dict], dry_run: bool) -> None:
    lines = ["RAG Support Assistant Alert", ""]
    for violation in violations:
        lines.append(f"- {violation['message']}")
    lines.extend(["", f"Generated: {datetime.now(timezone.utc).isoformat()}"])
    text = "\n".join(lines)

    print(text)

    if dry_run or not WEBHOOK_URL:
        print("[dry-run] Webhook not sent.")
        return

    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
        print("[alert] Webhook sent.")
    except Exception as exc:
        print(f"[alert] Webhook failed: {exc}")


def _write_log(violations: list[dict]) -> None:
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with ALERT_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        for violation in violations:
            handle.write(
                json.dumps(
                    {
                        "ts": ts,
                        "rule": violation["rule"],
                        "value": violation["value"],
                        "threshold": violation["threshold"],
                    }
                )
                + "\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    metrics = get_metrics_snapshot()
    violations = _check_thresholds(metrics)

    state = _load_state()
    new_state: dict = {}
    to_alert = []

    for violation in violations:
        rule = violation["rule"]
        previous = state.get(rule, 0)
        current = previous + 1
        new_state[rule] = current
        if current >= 2:
            to_alert.append(violation)

    for rule in state:
        if rule not in new_state:
            new_state[rule] = 0

    _save_state(new_state)

    now_iso = datetime.now(timezone.utc).isoformat()
    if not violations:
        print(f"[{now_iso}] All OK.")
        return

    print(
        f"[{now_iso}] "
        f"Violations: {[violation['rule'] for violation in violations]} | "
        f"Alerting: {[violation['rule'] for violation in to_alert]}"
    )

    if to_alert:
        _send_webhook(to_alert, dry_run=args.dry_run)
        _write_log(to_alert)


if __name__ == "__main__":
    main()

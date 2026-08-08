#!/usr/bin/env python3
"""Plan §4.6: operator / cron entry for escalation outbox retry.

Runs one bounded pass of ``retry_failed_deliveries`` without creating tickets.
Does not require Celery beat — suitable for cron or manual recovery.

Examples:

  python scripts/outbox_retry.py
  python scripts/outbox_retry.py --limit 20 --include-pending
  python scripts/outbox_retry.py --tenant acme --report reports/outbox-retry.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tasks.outbox_retry_task import (  # noqa: E402
    DEFAULT_LIMIT,
    run_outbox_retry_once,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Retry failed escalation inbox deliveries (plan §4.6 outbox)."
    )
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max tickets per pass (default {DEFAULT_LIMIT}, cap 500)",
    )
    p.add_argument(
        "--include-pending",
        action="store_true",
        help="Also retry delivery_state=pending (default: failed only)",
    )
    p.add_argument(
        "--tenant",
        type=str,
        default=None,
        help="Optional tenant_id filter",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path",
    )
    p.add_argument(
        "--dry-run-config",
        action="store_true",
        help="Print beat schedule / defaults only; no DB work",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.dry_run_config:
        from tasks.outbox_retry_task import (  # noqa: PLC0415
            build_outbox_beat_schedule,
            outbox_retry_beat_enabled_from_env,
            outbox_retry_interval_sec_from_env,
            outbox_retry_limit_from_env,
            outbox_retry_states_from_env,
        )

        payload = {
            "kind": "escalation-outbox-retry-config",
            "created_at": datetime.now(UTC).isoformat(),
            "beat_enabled": outbox_retry_beat_enabled_from_env(),
            "interval_sec": outbox_retry_interval_sec_from_env(),
            "batch_limit": outbox_retry_limit_from_env(),
            "states": outbox_retry_states_from_env(),
            "beat_schedule": build_outbox_beat_schedule(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    states = ["failed"]
    if args.include_pending:
        states.append("pending")

    print("=== escalation outbox retry (§4.6) ===")
    print(f"limit={args.limit} states={states} tenant={args.tenant or '*'}")

    try:
        result = run_outbox_retry_once(
            limit=int(args.limit),
            states=states,
            tenant_id=args.tenant,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result["created_at"] = datetime.now(UTC).isoformat()
    print(
        "attempted={attempted} delivered={delivered} failed={failed} skipped={skipped}".format(
            **{
                "attempted": result.get("attempted", 0),
                "delivered": result.get("delivered", 0),
                "failed": result.get("failed", 0),
                "skipped": result.get("skipped", 0),
            }
        )
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        # Drop bulky per-ticket results from optional report unless small.
        report = dict(result)
        if len(report.get("results") or []) > 20:
            report["results"] = report["results"][:20]
            report["results_truncated"] = True
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote report: {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

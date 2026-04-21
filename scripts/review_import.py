# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.engine import async_session

VERDICT_TO_STATUS = {
    "good": "confirmed_good",
    "bad": "confirmed_bad",
    "dismiss": "dismissed",
}


def _load_rows(path: Path) -> list[tuple[int, dict[str, Any]]]:
    items: list[tuple[int, dict[str, Any]]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid JSON object at line {line_no}")
        items.append((line_no, payload))
    return items


def _get_reviewer_email(explicit_email: str | None = None) -> str:
    reviewer_email = (explicit_email or os.getenv("REVIEWER_EMAIL", "")).strip().lower()
    if not reviewer_email:
        raise ValueError("REVIEWER_EMAIL is required. Set REVIEWER_EMAIL before running review_import.py.")
    return reviewer_email


def _build_reviewer_notes(review_payload: dict[str, Any]) -> str:
    notes = str(review_payload.get("notes") or "").strip()
    fix_hint = str(review_payload.get("fix_hint") or "").strip()
    if notes and fix_hint:
        return f"{notes}\n{fix_hint}"
    return notes or fix_hint


async def _resolve_reviewer_id(session: Any, reviewer_email: str) -> Any:
    result = await session.execute(
        text(
            """
            SELECT id FROM users
            WHERE lower(username) = :username
            LIMIT 1
            """
        ),
        {"username": reviewer_email},
    )
    row = result.mappings().first()
    if row is None:
        raise ValueError(
            "REVIEWER_EMAIL must match an existing users.username because review_queue.reviewed_by uses the current DB reviewer identity."
        )
    return row["id"]


def _should_confirm(actionable_count: int, confirm: bool, input_fn: Any) -> bool:
    if actionable_count <= 10 or confirm:
        return True
    answer = str(
        input_fn(
            f"About to apply {actionable_count} review decisions. Continue? [y/N]: "
        )
    ).strip().lower()
    return answer in {"y", "yes"}


async def run_once(
    path: str | Path,
    *,
    dry_run: bool,
    tenant_override: str | None,
    confirm: bool,
    session_factory: Any = async_session,
    reviewer_email: str | None = None,
    now: datetime | None = None,
    input_fn: Any = input,
) -> dict[str, Any]:
    batch_path = Path(path)
    rows = _load_rows(batch_path)
    actionable_count = 0
    for _, payload in rows:
        review_payload = payload.get("review") or {}
        if isinstance(review_payload, dict) and review_payload.get("verdict") is not None:
            actionable_count += 1

    if not _should_confirm(actionable_count, confirm, input_fn):
        return {
            "status": "aborted",
            "updated": 0,
            "skipped": actionable_count,
            "errored": 0,
            "warnings": 0,
            "dry_run": dry_run,
            "would_update": 0,
        }

    reviewer_identity = _get_reviewer_email(reviewer_email)
    current_time = now or datetime.now(timezone.utc)
    updated = 0
    skipped = 0
    errored = 0
    warnings = 0
    would_update = 0

    async with session_factory() as session:
        reviewer_id = await _resolve_reviewer_id(session, reviewer_identity)

        for line_no, payload in rows:
            review_payload = payload.get("review") or {}
            if not isinstance(review_payload, dict):
                errored += 1
                continue

            verdict = review_payload.get("verdict")
            if verdict is None:
                skipped += 1
                continue

            target_status = VERDICT_TO_STATUS.get(str(verdict).strip().lower())
            if target_status is None:
                errored += 1
                continue

            review_id = payload.get("review_id")
            tenant_id = tenant_override or payload.get("tenant_id")
            if review_id is None or not tenant_id:
                errored += 1
                continue

            existing = (
                await session.execute(
                    text(
                        """
                        SELECT id, tenant_id, status FROM review_queue
                        WHERE id = :review_id AND tenant_id = :tenant_id
                        """
                    ),
                    {
                        "review_id": int(review_id),
                        "tenant_id": str(tenant_id),
                    },
                )
            ).mappings().first()
            if existing is None:
                errored += 1
                continue
            if str(existing["status"]) != "pending":
                skipped += 1
                warnings += 1
                continue

            would_update += 1
            if dry_run:
                continue

            result = await session.execute(
                text(
                    """
                    UPDATE review_queue
                    SET status = :status,
                        reviewer_notes = :reviewer_notes,
                        reviewed_by = :reviewed_by,
                        reviewed_at = :reviewed_at
                    WHERE id = :review_id AND tenant_id = :tenant_id AND status = 'pending'
                    """
                ),
                {
                    "status": target_status,
                    "reviewer_notes": _build_reviewer_notes(review_payload),
                    "reviewed_by": reviewer_id,
                    "reviewed_at": current_time,
                    "review_id": int(review_id),
                    "tenant_id": str(tenant_id),
                    "line_no": line_no,
                },
            )
            if int(getattr(result, "rowcount", 0) or 0) == 0:
                errored += 1
                continue
            updated += 1

        if not dry_run and updated > 0:
            await session.commit()

    return {
        "status": "ok",
        "updated": updated,
        "skipped": skipped,
        "errored": errored,
        "warnings": warnings,
        "dry_run": dry_run,
        "would_update": would_update,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant-override", default=None)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    result = await run_once(
        args.path,
        dry_run=bool(args.dry_run),
        tenant_override=args.tenant_override,
        confirm=bool(args.confirm),
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

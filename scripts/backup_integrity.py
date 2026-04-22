#!/usr/bin/env python3
"""Backup retention + integrity audit (task-163).

Walks a directory of ``backup_snapshot.py`` outputs, verifies each
``snapshot_manifest.json`` against the actual files via SHA256, and flags
snapshots older than ``BACKUP_RETENTION_DAYS`` as candidates for deletion
(no destructive action is ever taken).

Output is a markdown report with per-snapshot status and aggregate
valid/corrupted/expired counters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class SnapshotStatus:
    path: str
    created_at: str | None
    is_valid: bool
    is_expired: bool
    issues: list[str] = field(default_factory=list)


def _hash_file(path: Path, *, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_created_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def audit_snapshot(
    snapshot_dir: Path,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> SnapshotStatus:
    now = now or datetime.now(timezone.utc)
    issues: list[str] = []
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    if not manifest_path.exists():
        return SnapshotStatus(
            path=str(snapshot_dir),
            created_at=None,
            is_valid=False,
            is_expired=False,
            issues=["missing snapshot_manifest.json"],
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return SnapshotStatus(
            path=str(snapshot_dir),
            created_at=None,
            is_valid=False,
            is_expired=False,
            issues=[f"manifest not valid JSON: {exc}"],
        )

    created_raw = manifest.get("created_at")
    created_at = _parse_created_at(created_raw)

    for component in manifest.get("components", []) or []:
        if component.get("status") != "ok":
            continue
        rel_path = component.get("path")
        expected_digest = component.get("sha256")
        expected_size = component.get("size_bytes")
        name = component.get("name") or "?"
        if not rel_path or not expected_digest:
            issues.append(f"{name}: manifest missing path/sha256")
            continue
        target = snapshot_dir / rel_path
        if not target.exists():
            issues.append(f"{name}: expected file missing at {rel_path}")
            continue
        actual_size = target.stat().st_size
        if expected_size is not None and actual_size != int(expected_size):
            issues.append(
                f"{name}: size mismatch (expected={expected_size}, actual={actual_size})"
            )
        actual_digest = _hash_file(target)
        if actual_digest != expected_digest:
            issues.append(f"{name}: sha256 mismatch")

    is_expired = False
    if created_at is not None:
        age_days = (now - created_at).total_seconds() / 86400.0
        if age_days > retention_days:
            is_expired = True

    return SnapshotStatus(
        path=str(snapshot_dir),
        created_at=created_raw,
        is_valid=not issues,
        is_expired=is_expired,
        issues=issues,
    )


def iter_snapshots(backup_dir: Path) -> Iterable[Path]:
    if not backup_dir.exists():
        return []
    entries = []
    for child in backup_dir.iterdir():
        if not child.is_dir():
            continue
        if not (child / "snapshot_manifest.json").exists():
            continue
        entries.append(child)
    return sorted(entries, key=lambda p: p.name)


def render_report(statuses: list[SnapshotStatus], *, retention_days: int) -> str:
    valid = sum(1 for s in statuses if s.is_valid and not s.is_expired)
    corrupted = sum(1 for s in statuses if not s.is_valid)
    expired = sum(1 for s in statuses if s.is_expired)

    lines: list[str] = [
        "# Backup integrity report",
        "",
        f"Generated at {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Retention window: {retention_days} day(s)",
        "",
        f"- Valid: **{valid}**",
        f"- Corrupted: **{corrupted}**",
        f"- Expired (deletion candidates): **{expired}**",
        "",
    ]

    if not statuses:
        lines.append("_No snapshots found._")
        return "\n".join(lines)

    lines.extend(["## Per-snapshot", ""])
    for status in statuses:
        flag = "OK" if status.is_valid else "CORRUPTED"
        if status.is_expired:
            flag = flag + " / EXPIRED"
        lines.append(f"### {Path(status.path).name} — {flag}")
        lines.append(f"- path: `{status.path}`")
        lines.append(f"- created_at: {status.created_at or 'unknown'}")
        if status.issues:
            lines.append("- issues:")
            for issue in status.issues:
                lines.append(f"  - {issue}")
        lines.append("")

    if any(status.is_expired for status in statuses):
        lines.extend(["## Recommended deletions", ""])
        for status in statuses:
            if status.is_expired:
                lines.append(f"- `{status.path}`")
        lines.append("")

    return "\n".join(lines)


def run_audit(
    backup_dir: Path,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> list[SnapshotStatus]:
    return [
        audit_snapshot(path, retention_days=retention_days, now=now)
        for path in iter_snapshots(backup_dir)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument(
        "--report",
        default=None,
        help="output markdown path (default: stdout)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="override BACKUP_RETENTION_DAYS (default 30)",
    )
    args = parser.parse_args(argv)

    retention = args.retention_days
    if retention is None:
        retention = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))

    backup_dir = Path(args.backup_dir)
    statuses = run_audit(backup_dir, retention_days=retention)
    markdown = render_report(statuses, retention_days=retention)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)

    if any(not s.is_valid for s in statuses):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

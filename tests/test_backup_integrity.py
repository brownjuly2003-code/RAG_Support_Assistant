from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_integrity, backup_snapshot


def _write_snapshot(project_root: Path, out_dir: Path) -> None:
    (project_root / "data" / "tracing").mkdir(parents=True, exist_ok=True)
    (project_root / "data" / "uploads").mkdir(parents=True, exist_ok=True)
    (project_root / "alembic" / "versions").mkdir(parents=True, exist_ok=True)
    (project_root / "alembic" / "versions" / "001_initial_schema.py").write_text("# migration", encoding="utf-8")

    import sqlite3

    db_path = project_root / "data" / "tracing" / "traces.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    (project_root / "data" / "uploads" / "sample.txt").write_text("content", encoding="utf-8")

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=True,
    )


def test_audit_valid_snapshot(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    snapshot_dir = tmp_path / "backup"
    _write_snapshot(project_root, snapshot_dir)

    status = backup_integrity.audit_snapshot(snapshot_dir, retention_days=30)

    assert status.is_valid is True
    assert status.is_expired is False
    assert status.issues == []


def test_audit_detects_corrupted_sha(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    snapshot_dir = tmp_path / "backup"
    _write_snapshot(project_root, snapshot_dir)

    tampered = snapshot_dir / "uploads" / "uploads.tar.gz"
    tampered.write_bytes(tampered.read_bytes() + b"\x00")

    status = backup_integrity.audit_snapshot(snapshot_dir, retention_days=30)

    assert status.is_valid is False
    assert any("uploads" in issue and "sha256" in issue for issue in status.issues)


def test_audit_missing_manifest(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "empty-snapshot"
    snapshot_dir.mkdir()

    status = backup_integrity.audit_snapshot(snapshot_dir, retention_days=30)

    assert status.is_valid is False
    assert any("missing snapshot_manifest.json" in issue for issue in status.issues)


def test_audit_flags_expired_candidate(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    snapshot_dir = tmp_path / "old-backup"
    _write_snapshot(project_root, snapshot_dir)

    manifest_path = snapshot_dir / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    long_ago = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec="seconds")
    manifest["created_at"] = long_ago
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )

    status = backup_integrity.audit_snapshot(snapshot_dir, retention_days=30)

    assert status.is_valid is True
    assert status.is_expired is True


def test_run_audit_iterates_all_snapshots(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    for idx in range(2):
        _write_snapshot(project_root, tmp_path / "backups" / f"snap-{idx}")

    statuses = backup_integrity.run_audit(tmp_path / "backups", retention_days=30)

    assert len(statuses) == 2
    assert all(s.is_valid for s in statuses)


def test_render_report_markdown_has_counters(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_snapshot(project_root, tmp_path / "backups" / "snap-1")

    statuses = backup_integrity.run_audit(tmp_path / "backups", retention_days=30)
    report = backup_integrity.render_report(statuses, retention_days=30)

    assert "# Backup integrity report" in report
    assert "Valid: **1**" in report
    assert "Corrupted: **0**" in report


def test_main_writes_report_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_snapshot(project_root, tmp_path / "backups" / "snap-1")

    report_path = tmp_path / "out.md"
    rc = backup_integrity.main(
        [
            "--backup-dir",
            str(tmp_path / "backups"),
            "--report",
            str(report_path),
            "--retention-days",
            "30",
        ]
    )

    assert rc == 0
    assert report_path.exists()
    assert "Backup integrity report" in report_path.read_text(encoding="utf-8")

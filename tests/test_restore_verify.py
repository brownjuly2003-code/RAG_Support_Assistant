from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot, restore_verify


def _build_source_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "data" / "tracing").mkdir(parents=True)
    (project_root / "data" / "uploads").mkdir(parents=True)
    (project_root / "data" / "vectordb" / "chroma").mkdir(parents=True)
    (project_root / "alembic" / "versions").mkdir(parents=True)
    (project_root / "alembic" / "versions" / "001_initial_schema.py").write_text("# migration", encoding="utf-8")

    db_path = project_root / "data" / "tracing" / "traces.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    (project_root / "data" / "uploads" / "hello.txt").write_text("upload", encoding="utf-8")
    (project_root / "data" / "vectordb" / "chroma" / "marker").write_text("chroma", encoding="utf-8")
    return project_root


def _produce_snapshot(tmp_path: Path) -> Path:
    project_root = _build_source_project(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    backup_snapshot.create_snapshot(
        out_dir=snapshot_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )
    return snapshot_dir


def test_verify_happy_path_returns_exit_zero(tmp_path: Path) -> None:
    snapshot_dir = _produce_snapshot(tmp_path)
    target_root = tmp_path / "restore"

    report = restore_verify.verify_snapshot(snapshot_dir, target_root=target_root)

    assert report.exit_code == restore_verify.EXIT_OK
    assert report.passed is True
    step_names = {s.name for s in report.steps}
    assert {"manifest", "sqlite", "uploads", "chromadb", "layout_smoke"}.issubset(step_names)


def test_verify_fails_when_manifest_missing(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    target_root = tmp_path / "restore"

    report = restore_verify.verify_snapshot(empty_dir, target_root=target_root)

    assert report.exit_code == restore_verify.EXIT_RESTORE_FAILED
    assert report.passed is False
    manifest_step = next(s for s in report.steps if s.name == "manifest")
    assert manifest_step.passed is False


def test_verify_fails_when_tarball_is_corrupted(tmp_path: Path) -> None:
    snapshot_dir = _produce_snapshot(tmp_path)
    tarball = snapshot_dir / "uploads" / "uploads.tar.gz"
    tarball.write_bytes(b"\x00" * 16)
    target_root = tmp_path / "restore"

    report = restore_verify.verify_snapshot(snapshot_dir, target_root=target_root)

    assert report.exit_code == restore_verify.EXIT_RESTORE_FAILED
    uploads_step = next(s for s in report.steps if s.name == "uploads")
    assert uploads_step.passed is False
    assert "tar extract failed" in uploads_step.detail


def test_verify_cleans_up_auto_temp_root_even_on_failure(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    report = restore_verify.verify_snapshot(empty_dir)

    assert report.exit_code == restore_verify.EXIT_RESTORE_FAILED


def test_render_report_includes_status(tmp_path: Path) -> None:
    snapshot_dir = _produce_snapshot(tmp_path)
    report = restore_verify.verify_snapshot(snapshot_dir, target_root=tmp_path / "restore")
    markdown = restore_verify.render_report(report)
    assert "Restore verification report" in markdown
    assert "passed: **True**" in markdown
    assert "sqlite" in markdown


def test_main_cli_exits_ok_on_happy_path(tmp_path: Path) -> None:
    snapshot_dir = _produce_snapshot(tmp_path)
    report_path = tmp_path / "report.md"

    rc = restore_verify.main(
        [
            "--snapshot",
            str(snapshot_dir),
            "--report",
            str(report_path),
        ]
    )

    assert rc == 0
    assert report_path.exists()

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot


def _make_project_root(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "data" / "tracing").mkdir(parents=True)
    (project_root / "data" / "uploads").mkdir(parents=True)
    (project_root / "data" / "vectordb" / "chroma").mkdir(parents=True)
    (project_root / "alembic" / "versions").mkdir(parents=True)

    db_path = project_root / "data" / "tracing" / "traces.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample (value) VALUES ('hello')")
        conn.commit()
    finally:
        conn.close()

    (project_root / "data" / "uploads" / "doc.txt").write_text("hello upload", encoding="utf-8")
    (project_root / "data" / "vectordb" / "chroma" / "marker").write_text("chroma placeholder", encoding="utf-8")

    for name in ("001_initial_schema.py", "017_curated_case_status.py"):
        (project_root / "alembic" / "versions" / name).write_text("# migration", encoding="utf-8")

    return project_root


def test_snapshot_produces_manifest_with_valid_hashes(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )

    assert (out_dir / "snapshot_manifest.json").exists()
    data = json.loads((out_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    assert data["alembic_revision"] == "017"
    components = {c["name"]: c for c in data["components"]}
    assert components["sqlite_traces"]["status"] == "ok"
    assert components["chromadb"]["status"] == "ok"
    assert components["uploads"]["status"] == "ok"
    assert components["postgres"]["status"] == "skipped"

    for name in ("sqlite_traces", "chromadb", "uploads"):
        component = components[name]
        target = out_dir / component["path"]
        assert target.exists()
        hasher = hashlib.sha256()
        hasher.update(target.read_bytes())
        assert hasher.hexdigest() == component["sha256"]
        assert component["size_bytes"] == target.stat().st_size


def test_snapshot_skip_chroma_flag(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=True,
    )

    components = {c.name: c for c in manifest.components}
    assert components["chromadb"].status == "skipped"
    assert not (out_dir / "chromadb").exists()


def test_snapshot_reports_total_size(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )

    expected = sum(c.size_bytes for c in manifest.components)
    assert manifest.total_size_bytes == expected
    assert manifest.total_size_bytes > 0


def test_snapshot_idempotent_when_rerun(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    first_dir = tmp_path / "backup-1"
    second_dir = tmp_path / "backup-2"

    first = backup_snapshot.create_snapshot(
        out_dir=first_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )
    second = backup_snapshot.create_snapshot(
        out_dir=second_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )

    first_components = {c.name: c for c in first.components}
    second_components = {c.name: c for c in second.components}
    for name in ("sqlite_traces", "uploads"):
        assert first_components[name].sha256 == second_components[name].sha256


def test_snapshot_skipped_when_missing_sources(tmp_path: Path) -> None:
    project_root = tmp_path / "empty"
    project_root.mkdir()
    out_dir = tmp_path / "backup"

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )

    statuses = {c.name: c.status for c in manifest.components}
    assert statuses["sqlite_traces"] == "skipped"
    assert statuses["uploads"] == "skipped"
    assert statuses["chromadb"] == "skipped"
    assert statuses["postgres"] == "skipped"
    assert all(status in ("skipped", "ok") for status in statuses.values())


def test_snapshot_records_key_fingerprint_without_raw_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"

    monkeypatch.setenv("DB_ENCRYPTION_KEY", "super-secret-key-do-not-leak")

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=True,
    )

    components = {c.name: c for c in manifest.components}
    assert components["encryption_key_fingerprint"].status == "ok"
    fingerprint_file = out_dir / components["encryption_key_fingerprint"].path
    text = fingerprint_file.read_text(encoding="utf-8")
    assert "super-secret-key-do-not-leak" not in text
    expected = hashlib.sha256(b"super-secret-key-do-not-leak").hexdigest()
    assert expected in text


def test_snapshot_cli_entry_exits_zero_on_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup-cli"

    monkeypatch.setattr(backup_snapshot, "PROJECT_ROOT", project_root)

    rc = backup_snapshot.main(["--out", str(out_dir), "--skip-chroma"])

    assert rc == 0
    assert (out_dir / "snapshot_manifest.json").exists()

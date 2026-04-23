from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot, restore_verify


def _build_source_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "data" / "tracing").mkdir(parents=True)
    (project_root / "data" / "uploads").mkdir(parents=True)
    (project_root / "data" / "vectordb" / "chroma").mkdir(parents=True)
    (project_root / "alembic" / "versions").mkdir(parents=True)
    (project_root / "alembic" / "versions" / "017_curated_case_status.py").write_text(
        "# migration",
        encoding="utf-8",
    )

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


def _produce_snapshot_with_postgres(tmp_path: Path) -> Path:
    project_root = _build_source_project(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    backup_snapshot.create_snapshot(
        out_dir=snapshot_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=False,
    )
    dump_path = snapshot_dir / "postgres" / "postgres.dump"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    dump_path.write_bytes(b"PGDMP")

    manifest_path = snapshot_dir / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"].append(
        {
            "name": "postgres",
            "status": "ok",
            "path": "postgres/postgres.dump",
            "size_bytes": dump_path.stat().st_size,
            "sha256": None,
            "detail": None,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    return snapshot_dir


def test_verify_snapshot_returns_postgres_exit_code_when_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = _produce_snapshot_with_postgres(tmp_path)

    def _pg_restore_fail(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=kwargs.get("args") or args[0])

    monkeypatch.setattr(restore_verify.subprocess, "run", _pg_restore_fail)

    report = restore_verify.verify_snapshot(
        snapshot_dir,
        target_root=tmp_path / "restore",
        postgres_url="postgresql://rag:rag_test@localhost:5432/rag_restore_test",
    )

    assert report.exit_code == restore_verify.EXIT_POSTGRES_VERIFY_FAILED
    postgres_step = next(step for step in report.steps if step.name == "postgres")
    assert postgres_step.passed is False
    assert "pg_restore" in postgres_step.detail


@pytest.mark.integration
def test_restore_verify_integration_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("docker")
    missing = [
        tool
        for tool in ("docker", "pg_dump", "pg_restore", "alembic")
        if shutil.which(tool) is None
    ]
    if missing:
        pytest.skip(f"missing required tools: {', '.join(missing)}")

    from scripts import restore_verify_integration

    compose_base = restore_verify_integration._compose_base()
    project_root = _build_source_project(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "restore-verify-test-key")

    try:
        restore_verify_integration._run_compose(
            compose_base,
            ["up", "-d", restore_verify_integration.POSTGRES_SERVICE],
        )
        restore_verify_integration._wait_for_pg_ready(compose_base)
        port = restore_verify_integration._resolve_host_port(compose_base)
        database_url = (
            "postgresql://"
            f"{restore_verify_integration.POSTGRES_USER}:"
            f"{restore_verify_integration.POSTGRES_PASSWORD}@localhost:{port}/"
            f"{restore_verify_integration.POSTGRES_DB}"
        )

        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        env["DB_ENCRYPTION_KEY"] = "restore-verify-test-key"
        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
        )

        backup_snapshot.create_snapshot(
            out_dir=snapshot_dir,
            project_root=project_root,
            database_url=database_url,
            skip_chroma=False,
        )
    finally:
        restore_verify_integration._run_compose(compose_base, ["down", "-v"], check=False)

    try:
        rc = restore_verify_integration.main(
            [
                "--snapshot",
                str(snapshot_dir),
            ]
        )
        assert rc == 0
    finally:
        restore_verify_integration._run_compose(compose_base, ["down", "-v"], check=False)

    ps = restore_verify_integration._run_compose(
        compose_base,
        ["ps", "-q", restore_verify_integration.POSTGRES_SERVICE],
        check=False,
    )
    assert ps.stdout.strip() == ""

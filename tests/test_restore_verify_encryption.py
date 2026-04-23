from __future__ import annotations

import sqlite3
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot, restore_verify
from tests.test_backup_snapshot_encryption import _generate_age_identity, _make_project_root


pytestmark = pytest.mark.skipif(
    shutil.which("age") is None or shutil.which("age-keygen") is None,
    reason="age tooling not installed",
)


def _produce_encrypted_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    project_root = _make_project_root(tmp_path)
    snapshot_dir = tmp_path / "snapshot"
    identity_path, recipient = _generate_age_identity(tmp_path, "restore-identity")

    def _fake_pg_dump(database_url: str, target: Path, *, pg_dump_path: str | None = None) -> None:
        del database_url, pg_dump_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PGDMP")

    monkeypatch.setattr(backup_snapshot, "_pg_dump", _fake_pg_dump)
    monkeypatch.setenv("BACKUP_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("BACKUP_ENCRYPTION_RECIPIENT", recipient)

    backup_snapshot.create_snapshot(
        out_dir=snapshot_dir,
        project_root=project_root,
        database_url="postgresql://example.invalid/rag",
        skip_chroma=False,
    )
    return snapshot_dir, identity_path


def test_restore_verify_decrypts_snapshot_with_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir, identity_path = _produce_encrypted_snapshot(tmp_path, monkeypatch)
    target_root = tmp_path / "restore"

    report = restore_verify.verify_snapshot(
        snapshot_dir,
        target_root=target_root,
        age_identity_file=identity_path,
    )

    assert report.exit_code == restore_verify.EXIT_OK
    assert report.passed is True
    restored_db = target_root / "data" / "tracing" / "traces.db"
    assert restored_db.exists()

    conn = sqlite3.connect(str(restored_db))
    try:
        rows = conn.execute("SELECT value FROM sample").fetchall()
    finally:
        conn.close()
    assert rows == [("hello",)]


def test_restore_verify_returns_decrypt_error_for_wrong_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir, _ = _produce_encrypted_snapshot(tmp_path, monkeypatch)
    wrong_identity_path, _ = _generate_age_identity(tmp_path, "wrong-identity")

    report = restore_verify.verify_snapshot(
        snapshot_dir,
        target_root=tmp_path / "restore",
        age_identity_file=wrong_identity_path,
    )

    assert report.exit_code == restore_verify.EXIT_DECRYPT_FAILED
    assert report.passed is False
    failed_steps = [step for step in report.steps if not step.passed]
    assert failed_steps
    assert any("decrypt failed" in step.detail.lower() for step in failed_steps)

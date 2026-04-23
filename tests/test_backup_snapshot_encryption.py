from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot


pytestmark = pytest.mark.skipif(
    shutil.which("age") is None or shutil.which("age-keygen") is None,
    reason="age tooling not installed",
)


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
    (project_root / "data" / "vectordb" / "chroma" / "marker").write_text("chroma", encoding="utf-8")
    (project_root / "alembic" / "versions" / "017_curated_case_status.py").write_text(
        "# migration",
        encoding="utf-8",
    )
    return project_root


def _generate_age_identity(tmp_path: Path, name: str) -> tuple[Path, str]:
    identity_path = tmp_path / f"{name}.txt"
    subprocess.run(
        ["age-keygen", "-o", str(identity_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    recipient = subprocess.run(
        ["age-keygen", "-y", str(identity_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return identity_path, recipient


def test_snapshot_encrypts_components_at_rest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    _, recipient = _generate_age_identity(tmp_path, "identity")

    def _fake_pg_dump(database_url: str, target: Path, *, pg_dump_path: str | None = None) -> None:
        del database_url, pg_dump_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PGDMP")

    monkeypatch.setattr(backup_snapshot, "_pg_dump", _fake_pg_dump)
    monkeypatch.setenv("BACKUP_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("BACKUP_ENCRYPTION_RECIPIENT", recipient)

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url="postgresql://example.invalid/rag",
        skip_chroma=False,
    )

    manifest = json.loads((out_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    components = {component["name"]: component for component in manifest["components"]}

    assert manifest["encryption"]["enabled"] is True
    assert manifest["encryption"]["recipient_fingerprint"] == hashlib.sha256(
        recipient.encode("utf-8")
    ).hexdigest()

    expected = {
        "postgres": ("postgres.dump.age", Path("postgres") / "postgres.dump"),
        "sqlite_traces": ("traces.sqlite.age", Path("sqlite") / "traces.db"),
        "uploads": ("uploads.tar.gz.age", Path("uploads") / "uploads.tar.gz"),
        "chromadb": ("chroma.tar.gz.age", Path("chromadb") / "chroma.tar.gz"),
    }
    for name, (encrypted_name, plaintext_name) in expected.items():
        component = components[name]
        assert component["status"] == "ok"
        assert component["encrypted"] is True
        assert component["algorithm"] == "age"
        assert component["path"] == encrypted_name
        assert (out_dir / encrypted_name).exists()
        assert not (out_dir / plaintext_name).exists()

#!/usr/bin/env python3
"""Snapshot backup for RAG_Support_Assistant persistent stores (task-159).

Creates an atomic snapshot directory with:
- Optional ``pg_dump`` of the live Postgres (when ``POSTGRES_URL`` env is set).
- Atomic SQLite backup of ``data/tracing/traces.db`` via the SQLite backup API.
- Tarballs of ChromaDB persistent path and ``data/uploads`` (opt-in, default on).
- ``snapshot_manifest.json`` with versions, per-file SHA256 + size.

Cross-platform Python script (no bash). When a store is missing it is listed
as ``skipped`` rather than failing hard so single-store local dev continues to
work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ComponentReport:
    name: str
    status: str  # "ok" | "skipped" | "failed"
    path: str | None = None
    size_bytes: int = 0
    sha256: str | None = None
    detail: str | None = None


@dataclass
class SnapshotManifest:
    created_at: str
    host: str
    python: str
    alembic_revision: str | None
    total_size_bytes: int = 0
    components: list[ComponentReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "host": self.host,
            "python": self.python,
            "alembic_revision": self.alembic_revision,
            "total_size_bytes": self.total_size_bytes,
            "components": [asdict(c) for c in self.components],
        }


def _hash_file(path: Path, *, chunk_size: int = 65536) -> tuple[str, int]:
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            total += len(chunk)
    return hasher.hexdigest(), total


def _detect_alembic_revision(project_root: Path) -> str | None:
    versions_dir = project_root / "alembic" / "versions"
    if not versions_dir.exists():
        return None
    numeric: list[tuple[int, str]] = []
    for path in versions_dir.glob("*.py"):
        stem = path.stem
        prefix = stem.split("_", 1)[0]
        try:
            numeric.append((int(prefix), prefix))
        except ValueError:
            continue
    if not numeric:
        return None
    numeric.sort()
    return numeric[-1][1]


def _atomic_sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(source))
    dst_conn = sqlite3.connect(str(target))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _pg_dump(database_url: str, target: Path, *, pg_dump_path: str | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    binary = pg_dump_path or os.environ.get("PG_DUMP_PATH") or shutil.which("pg_dump") or "pg_dump"
    with target.open("wb") as fh:
        subprocess.run(
            [binary, database_url, "-Fc"],
            check=True,
            stdout=fh,
        )


def _create_tarball(source_dir: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)


def _snapshot_sqlite(project_root: Path, out_dir: Path) -> ComponentReport:
    source = project_root / "data" / "tracing" / "traces.db"
    if not source.exists():
        return ComponentReport(name="sqlite_traces", status="skipped", detail="traces.db missing")
    target = out_dir / "sqlite" / "traces.db"
    try:
        _atomic_sqlite_backup(source, target)
    except Exception as exc:
        return ComponentReport(name="sqlite_traces", status="failed", detail=str(exc))
    digest, size = _hash_file(target)
    return ComponentReport(
        name="sqlite_traces",
        status="ok",
        path=str(target.relative_to(out_dir)).replace("\\", "/"),
        size_bytes=size,
        sha256=digest,
    )


def _snapshot_postgres(out_dir: Path, database_url: Optional[str]) -> ComponentReport:
    if not database_url:
        return ComponentReport(name="postgres", status="skipped", detail="POSTGRES_URL unset")
    target = out_dir / "postgres" / "postgres.dump"
    try:
        _pg_dump(database_url, target)
    except FileNotFoundError:
        return ComponentReport(name="postgres", status="failed", detail="pg_dump binary not found")
    except subprocess.CalledProcessError as exc:
        return ComponentReport(name="postgres", status="failed", detail=f"pg_dump exit {exc.returncode}")
    except Exception as exc:
        return ComponentReport(name="postgres", status="failed", detail=str(exc))
    digest, size = _hash_file(target)
    return ComponentReport(
        name="postgres",
        status="ok",
        path=str(target.relative_to(out_dir)).replace("\\", "/"),
        size_bytes=size,
        sha256=digest,
    )


def _snapshot_chroma(project_root: Path, out_dir: Path, *, skip: bool) -> ComponentReport:
    if skip:
        return ComponentReport(name="chromadb", status="skipped", detail="--skip-chroma")
    source_dir = project_root / "data" / "vectordb" / "chroma"
    if not source_dir.exists():
        return ComponentReport(name="chromadb", status="skipped", detail="chroma dir missing")
    target = out_dir / "chromadb" / "chroma.tar.gz"
    try:
        _create_tarball(source_dir, target)
    except Exception as exc:
        return ComponentReport(name="chromadb", status="failed", detail=str(exc))
    digest, size = _hash_file(target)
    return ComponentReport(
        name="chromadb",
        status="ok",
        path=str(target.relative_to(out_dir)).replace("\\", "/"),
        size_bytes=size,
        sha256=digest,
    )


def _snapshot_uploads(project_root: Path, out_dir: Path) -> ComponentReport:
    source_dir = project_root / "data" / "uploads"
    if not source_dir.exists():
        return ComponentReport(name="uploads", status="skipped", detail="uploads dir missing")
    target = out_dir / "uploads" / "uploads.tar.gz"
    try:
        _create_tarball(source_dir, target)
    except Exception as exc:
        return ComponentReport(name="uploads", status="failed", detail=str(exc))
    digest, size = _hash_file(target)
    return ComponentReport(
        name="uploads",
        status="ok",
        path=str(target.relative_to(out_dir)).replace("\\", "/"),
        size_bytes=size,
        sha256=digest,
    )


def _snapshot_key_fingerprint(out_dir: Path) -> ComponentReport:
    key = os.environ.get("DB_ENCRYPTION_KEY", "").strip()
    if not key:
        return ComponentReport(name="encryption_key_fingerprint", status="skipped", detail="DB_ENCRYPTION_KEY unset")
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
    target = out_dir / "keys" / "fingerprint.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"DB_ENCRYPTION_KEY sha256: {fingerprint}\n", encoding="utf-8")
    digest, size = _hash_file(target)
    return ComponentReport(
        name="encryption_key_fingerprint",
        status="ok",
        path=str(target.relative_to(out_dir)).replace("\\", "/"),
        size_bytes=size,
        sha256=digest,
        detail="sha256 only — raw key never persisted",
    )


def create_snapshot(
    *,
    out_dir: Path,
    project_root: Path = PROJECT_ROOT,
    database_url: Optional[str] = None,
    skip_chroma: bool = False,
) -> SnapshotManifest:
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = SnapshotManifest(
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        host=platform.node() or "unknown",
        python=platform.python_version(),
        alembic_revision=_detect_alembic_revision(project_root),
    )

    manifest.components.append(_snapshot_sqlite(project_root, out_dir))
    manifest.components.append(_snapshot_postgres(out_dir, database_url or os.environ.get("POSTGRES_URL")))
    manifest.components.append(_snapshot_chroma(project_root, out_dir, skip=skip_chroma))
    manifest.components.append(_snapshot_uploads(project_root, out_dir))
    manifest.components.append(_snapshot_key_fingerprint(out_dir))

    manifest.total_size_bytes = sum(c.size_bytes for c in manifest.components)

    manifest_path = out_dir / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory for the snapshot")
    parser.add_argument("--skip-chroma", action="store_true", help="skip ChromaDB tarball")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres URL (falls back to POSTGRES_URL env)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    manifest = create_snapshot(
        out_dir=out_dir,
        database_url=args.database_url,
        skip_chroma=args.skip_chroma,
    )

    ok = sum(1 for c in manifest.components if c.status == "ok")
    failed = sum(1 for c in manifest.components if c.status == "failed")
    print(
        f"snapshot -> {out_dir}: {ok} ok / {failed} failed / {len(manifest.components)} total,"
        f" size={manifest.total_size_bytes} bytes"
    )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

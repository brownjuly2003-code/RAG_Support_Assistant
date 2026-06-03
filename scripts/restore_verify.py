#!/usr/bin/env python3
"""Disposable restore verification (task-160).

Stages a snapshot produced by ``scripts/backup_snapshot.py`` into an
ephemeral project-root-shaped directory, runs smoke checks against the
restored layout (SQLite queryable, tarballs unpackable, manifest sane),
and emits a markdown report. Does not touch the live deployment.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.models import Base  # noqa: E402

EXIT_OK = 0
EXIT_RESTORE_FAILED = 1
EXIT_SMOKE_FAILED = 2
EXIT_INFRA_ERROR = 3
EXIT_POSTGRES_VERIFY_FAILED = 4
EXIT_DECRYPT_FAILED = 5
EXPECTED_PUBLIC_TABLE_COUNT = 18
EXPECTED_MODEL_TABLES = tuple(sorted(Base.metadata.tables))
DECRYPTED_COMPONENT_FILENAMES = {
    "postgres": "postgres.dump",
    "sqlite_traces": "traces.sqlite",
    "uploads": "uploads.tar.gz",
    "chromadb": "chroma.tar.gz",
}


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RestoreReport:
    snapshot_path: str
    created_at: str
    steps: list[StepResult] = field(default_factory=list)
    exit_code: int = EXIT_OK

    @property
    def passed(self) -> bool:
        return all(step.passed for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "steps": [step.to_dict() for step in self.steps],
        }


def _load_manifest(snapshot_dir: Path) -> dict[str, Any]:
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("snapshot_manifest.json missing")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _read_passphrase_file(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"empty passphrase file: {path}")
    return value


def _decrypt_component(
    snapshot_dir: Path,
    component: dict[str, Any],
    *,
    age_identity_file: Path | None,
    age_passphrase_file: Path | None,
    temp_root: Path,
    label: str,
) -> tuple[Path | None, StepResult | None]:
    rel = component.get("path")
    if not rel:
        return None, StepResult(label, passed=False, detail="manifest missing path")

    source = snapshot_dir / rel
    if not source.exists():
        return None, StepResult(label, passed=False, detail=f"{rel} missing")

    if not component.get("encrypted"):
        return source, None

    if age_identity_file and age_passphrase_file:
        return None, StepResult(
            label,
            passed=False,
            detail="decrypt failed: specify only one of --age-identity-file or --age-passphrase-file",
        )
    if not age_identity_file and not age_passphrase_file:
        return None, StepResult(
            label,
            passed=False,
            detail="decrypt failed: encrypted snapshot requires --age-identity-file or --age-passphrase-file",
        )
    if shutil.which("age") is None:
        return None, StepResult(label, passed=False, detail="decrypt failed: age binary not found")
    if age_passphrase_file and shutil.which("age-plugin-batchpass") is None:
        return None, StepResult(
            label,
            passed=False,
            detail="decrypt failed: age-plugin-batchpass not found",
        )

    output_name = DECRYPTED_COMPONENT_FILENAMES.get(component.get("name"), Path(rel).stem)
    target = temp_root / output_name
    command = ["age", "--decrypt"]
    env = os.environ.copy()
    if age_identity_file:
        command.extend(["--identity", str(age_identity_file)])
    else:
        command.extend(["-j", "batchpass"])
        try:
            env["AGE_PASSPHRASE"] = _read_passphrase_file(age_passphrase_file)
        except ValueError as exc:
            return None, StepResult(label, passed=False, detail=f"decrypt failed: {exc}")

    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("wb") as dst:
        result = subprocess.run(
            command,
            stdin=src,
            stdout=dst,
            stderr=subprocess.PIPE,
            env=env,
        )
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        detail = result.stderr.decode("utf-8", errors="replace").strip() or f"age exit {result.returncode}"
        return None, StepResult(label, passed=False, detail=f"decrypt failed: {detail}")
    return target, None


def _is_decrypt_failure(step: StepResult) -> bool:
    return not step.passed and step.detail.startswith("decrypt failed:")


def _restore_sqlite(snapshot_dir: Path, component: dict[str, Any], target_root: Path) -> StepResult:
    rel = component.get("path")
    if not rel:
        return StepResult("sqlite", passed=False, detail="manifest missing path")
    source = snapshot_dir / rel
    if not source.exists():
        return StepResult("sqlite", passed=False, detail=f"{rel} missing")
    return _restore_sqlite_source(source, target_root)


def _restore_sqlite_source(source: Path, target_root: Path) -> StepResult:
    target = target_root / "data" / "tracing" / "traces.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    try:
        conn = sqlite3.connect(str(target))
        try:
            conn.execute("PRAGMA integrity_check").fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return StepResult("sqlite", passed=False, detail=f"sqlite check failed: {exc}")
    return StepResult("sqlite", passed=True, detail=f"restored to {target}")


def _restore_tarball(
    source: Path,
    target_root: Path,
    *,
    relative_target: Path,
    label: str,
) -> StepResult:
    extract_to = target_root / relative_target
    extract_to.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(extract_to, filter="data")
    except Exception as exc:
        return StepResult(label, passed=False, detail=f"tar extract failed: {exc}")
    return StepResult(label, passed=True, detail=f"restored to {extract_to}")


def _run_layout_smoke(target_root: Path, manifest: dict[str, Any]) -> StepResult:
    expected_components = {c.get("name") for c in (manifest.get("components") or []) if c.get("status") == "ok"}
    found = []
    if "sqlite_traces" in expected_components:
        found.append((target_root / "data" / "tracing" / "traces.db").exists())
    if "uploads" in expected_components:
        found.append((target_root / "data" / "uploads").exists())
    if "chromadb" in expected_components:
        found.append((target_root / "data" / "vectordb" / "chroma").exists())

    if not found:
        return StepResult("layout_smoke", passed=False, detail="no restorable components present")
    if not all(found):
        return StepResult("layout_smoke", passed=False, detail="some restored paths missing post-extract")
    return StepResult("layout_smoke", passed=True, detail=f"{len(found)} layout checks passed")


def _verify_postgres(
    source: Path,
    manifest: dict[str, Any],
    postgres_url: str,
) -> StepResult:
    try:
        restore = subprocess.run(
            [
                "pg_restore",
                f"--dbname={postgres_url}",
                "--clean",
                "--if-exists",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return StepResult("postgres", passed=False, detail="pg_restore binary not found")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or f"pg_restore exit {exc.returncode}"
        return StepResult("postgres", passed=False, detail=f"pg_restore failed: {detail}")

    try:
        import psycopg2
        from psycopg2 import sql
    except Exception as exc:
        return StepResult("postgres", passed=False, detail=f"psycopg2 import failed: {exc}")

    manifest_revision = manifest.get("alembic_revision")
    if not isinstance(manifest_revision, str) or not manifest_revision:
        return StepResult("postgres", passed=False, detail="manifest missing alembic_revision")

    try:
        with psycopg2.connect(postgres_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version_num FROM alembic_version")
                row = cur.fetchone()
                live_revision = row[0] if row else None
                if live_revision != manifest_revision:
                    return StepResult(
                        "postgres",
                        passed=False,
                        detail=f"alembic_version mismatch: expected {manifest_revision}, got {live_revision}",
                    )

                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
                )
                table_count = cur.fetchone()[0]
                if table_count != EXPECTED_PUBLIC_TABLE_COUNT:
                    return StepResult(
                        "postgres",
                        passed=False,
                        detail=(
                            "unexpected public table count: "
                            f"expected {EXPECTED_PUBLIC_TABLE_COUNT}, got {table_count}"
                        ),
                    )

                for table_name in EXPECTED_MODEL_TABLES:
                    cur.execute(
                        sql.SQL("SELECT * FROM public.{} LIMIT 0").format(sql.Identifier(table_name))
                    )
    except Exception as exc:
        return StepResult("postgres", passed=False, detail=f"postgres verify failed: {exc}")

    restore_note = restore.stderr.strip() if restore.stderr else "pg_restore ok"
    return StepResult(
        "postgres",
        passed=True,
        detail=(
            f"{restore_note}; alembic={manifest_revision}; "
            f"tables={EXPECTED_PUBLIC_TABLE_COUNT}; model_tables={len(EXPECTED_MODEL_TABLES)}"
        ),
    )


def verify_snapshot(
    snapshot_dir: Path,
    *,
    target_root: Path | None = None,
    postgres_url: str | None = None,
    age_identity_file: Path | None = None,
    age_passphrase_file: Path | None = None,
) -> RestoreReport:
    cleanup_target = False
    if target_root is None:
        target_root = Path(tempfile.mkdtemp(prefix="rag-restore-"))
        cleanup_target = True
    decrypt_root = Path(tempfile.mkdtemp(prefix="rag-restore-decrypt-"))

    report = RestoreReport(
        snapshot_path=str(snapshot_dir),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    try:
        try:
            manifest = _load_manifest(snapshot_dir)
        except FileNotFoundError as exc:
            report.steps.append(StepResult("manifest", passed=False, detail=str(exc)))
            report.exit_code = EXIT_RESTORE_FAILED
            return report

        report.steps.append(StepResult("manifest", passed=True, detail=f"{len(manifest.get('components') or [])} components"))

        components = {c.get("name"): c for c in (manifest.get("components") or [])}

        if components.get("sqlite_traces", {}).get("status") == "ok":
            sqlite_source, sqlite_error = _decrypt_component(
                snapshot_dir,
                components["sqlite_traces"],
                age_identity_file=age_identity_file,
                age_passphrase_file=age_passphrase_file,
                temp_root=decrypt_root,
                label="sqlite",
            )
            if sqlite_error:
                report.steps.append(sqlite_error)
                if _is_decrypt_failure(sqlite_error):
                    report.exit_code = EXIT_DECRYPT_FAILED
                else:
                    report.exit_code = EXIT_RESTORE_FAILED
                return report
            report.steps.append(_restore_sqlite_source(sqlite_source, target_root))
        if components.get("uploads", {}).get("status") == "ok":
            uploads_source, uploads_error = _decrypt_component(
                snapshot_dir,
                components["uploads"],
                age_identity_file=age_identity_file,
                age_passphrase_file=age_passphrase_file,
                temp_root=decrypt_root,
                label="uploads",
            )
            if uploads_error:
                report.steps.append(uploads_error)
                if _is_decrypt_failure(uploads_error):
                    report.exit_code = EXIT_DECRYPT_FAILED
                else:
                    report.exit_code = EXIT_RESTORE_FAILED
                return report
            report.steps.append(
                _restore_tarball(
                    uploads_source,
                    target_root,
                    relative_target=Path("data"),
                    label="uploads",
                )
            )
        if components.get("chromadb", {}).get("status") == "ok":
            chroma_source, chroma_error = _decrypt_component(
                snapshot_dir,
                components["chromadb"],
                age_identity_file=age_identity_file,
                age_passphrase_file=age_passphrase_file,
                temp_root=decrypt_root,
                label="chromadb",
            )
            if chroma_error:
                report.steps.append(chroma_error)
                if _is_decrypt_failure(chroma_error):
                    report.exit_code = EXIT_DECRYPT_FAILED
                else:
                    report.exit_code = EXIT_RESTORE_FAILED
                return report
            report.steps.append(
                _restore_tarball(
                    chroma_source,
                    target_root,
                    relative_target=Path("data") / "vectordb",
                    label="chromadb",
                )
            )

        restore_failed = not all(step.passed for step in report.steps)
        if restore_failed:
            report.exit_code = EXIT_RESTORE_FAILED
            return report

        if postgres_url:
            postgres_component = components.get("postgres")
            if postgres_component and postgres_component.get("status") == "ok":
                postgres_source, postgres_error = _decrypt_component(
                    snapshot_dir,
                    postgres_component,
                    age_identity_file=age_identity_file,
                    age_passphrase_file=age_passphrase_file,
                    temp_root=decrypt_root,
                    label="postgres",
                )
                if postgres_error:
                    report.steps.append(postgres_error)
                    if _is_decrypt_failure(postgres_error):
                        report.exit_code = EXIT_DECRYPT_FAILED
                    else:
                        report.exit_code = EXIT_POSTGRES_VERIFY_FAILED
                    return report
                postgres_step = _verify_postgres(postgres_source, manifest, postgres_url)
            else:
                postgres_step = StepResult(
                    "postgres",
                    passed=False,
                    detail="snapshot does not contain a restorable postgres component",
                )
            report.steps.append(postgres_step)
            if not postgres_step.passed:
                report.exit_code = EXIT_POSTGRES_VERIFY_FAILED
                return report

        smoke = _run_layout_smoke(target_root, manifest)
        report.steps.append(smoke)
        if not smoke.passed:
            report.exit_code = EXIT_SMOKE_FAILED
            return report

        report.exit_code = EXIT_OK
        return report
    finally:
        try:
            shutil.rmtree(decrypt_root, ignore_errors=True)
        except Exception:
            pass
        if cleanup_target:
            try:
                shutil.rmtree(target_root, ignore_errors=True)
            except Exception:
                pass


def render_report(report: RestoreReport) -> str:
    lines: list[str] = [
        "# Restore verification report",
        "",
        f"snapshot_path: {report.snapshot_path}",
        f"created_at: {report.created_at}",
        f"passed: **{report.passed}**",
        f"exit_code: {report.exit_code}",
        "",
        "| step | status | detail |",
        "| --- | --- | --- |",
    ]
    for step in report.steps:
        status = "PASS" if step.passed else "FAIL"
        detail = step.detail.replace("|", "\\|")
        lines.append(f"| {step.name} | {status} | {detail} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--age-identity-file", default=None)
    parser.add_argument("--age-passphrase-file", default=None)
    args = parser.parse_args(argv)

    snapshot_dir = Path(args.snapshot)
    if not snapshot_dir.exists():
        sys.stderr.write(f"snapshot path not found: {snapshot_dir}\n")
        return EXIT_INFRA_ERROR

    report = verify_snapshot(
        snapshot_dir,
        postgres_url=args.postgres_url,
        age_identity_file=Path(args.age_identity_file) if args.age_identity_file else None,
        age_passphrase_file=Path(args.age_passphrase_file) if args.age_passphrase_file else None,
    )
    markdown = render_report(report)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)

    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

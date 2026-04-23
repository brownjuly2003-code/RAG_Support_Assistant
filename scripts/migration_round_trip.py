#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.models import Base  # noqa: E402

EXIT_OK = 0
EXIT_UPGRADE_FAILED = 1
EXIT_DOWNGRADE_FAILED = 2
EXIT_REUPGRADE_FAILED = 3
EXIT_TABLE_SET_MISMATCH = 4

_DEFAULT_ENCRYPTION_KEY = "test-encryption-key-32-characters-long-xyz"
_MIGRATION_ONLY_TABLES = {
    "review_queue",
    "trace_evaluations",
    "experiment_deployments",
    "experiment_assignments",
    "curated_case_status",
}


def _expected_tables() -> set[str]:
    return set(Base.metadata.tables.keys()) | _MIGRATION_ONLY_TABLES | {"alembic_version"}


def _emit(process: subprocess.CompletedProcess[str]) -> None:
    if process.stdout:
        sys.stdout.write(process.stdout)
    if process.stderr:
        sys.stderr.write(process.stderr)


def _run_alembic(command: list[str], *, database_url: str, verbose: bool) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env.setdefault("DB_ENCRYPTION_KEY", _DEFAULT_ENCRYPTION_KEY)
    if verbose:
        sys.stderr.write(f"+ alembic {' '.join(command)}\n")
    process = subprocess.run(
        ["alembic", *command],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    _emit(process)
    return process


def _revision_from_output(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.split()[0]
    return ""


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run alembic migration round-trip audit.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    database_url = args.database_url.strip()
    if not database_url:
        parser.error("--database-url or DATABASE_URL is required")

    heads = _run_alembic(["heads"], database_url=database_url, verbose=args.verbose)
    if heads.returncode != 0:
        return EXIT_UPGRADE_FAILED

    head_revision = _revision_from_output(heads.stdout)
    if not head_revision:
        sys.stderr.write("failed to resolve alembic head revision\n")
        return EXIT_UPGRADE_FAILED

    expected_tables = _expected_tables()
    missing_from_metadata = sorted(_MIGRATION_ONLY_TABLES - set(Base.metadata.tables.keys()))
    if args.verbose and missing_from_metadata:
        sys.stderr.write(
            "metadata is missing migration-owned tables, extending expected set with: "
            f"{', '.join(missing_from_metadata)}\n"
        )
        sys.stderr.write(f"expected tables ({len(expected_tables)}): {', '.join(sorted(expected_tables))}\n")

    upgrade = _run_alembic(["upgrade", "head"], database_url=database_url, verbose=args.verbose)
    if upgrade.returncode != 0:
        return EXIT_UPGRADE_FAILED

    current = _run_alembic(["current"], database_url=database_url, verbose=args.verbose)
    if current.returncode != 0:
        return EXIT_UPGRADE_FAILED
    if _revision_from_output(current.stdout) != head_revision:
        sys.stderr.write(
            f"expected alembic current to be {head_revision} after upgrade, got "
            f"{_revision_from_output(current.stdout) or '<empty>'}\n"
        )
        return EXIT_UPGRADE_FAILED

    downgrade = _run_alembic(["downgrade", "base"], database_url=database_url, verbose=args.verbose)
    if downgrade.returncode != 0:
        return EXIT_DOWNGRADE_FAILED

    current = _run_alembic(["current"], database_url=database_url, verbose=args.verbose)
    if current.returncode != 0:
        return EXIT_DOWNGRADE_FAILED
    if _revision_from_output(current.stdout):
        sys.stderr.write(
            f"expected alembic current to be empty after downgrade, got {_revision_from_output(current.stdout)}\n"
        )
        return EXIT_DOWNGRADE_FAILED

    reupgrade = _run_alembic(["upgrade", "head"], database_url=database_url, verbose=args.verbose)
    if reupgrade.returncode != 0:
        return EXIT_REUPGRADE_FAILED

    actual_tables = _table_names(database_url)
    missing_tables = sorted(expected_tables - actual_tables)
    extra_tables = sorted(actual_tables - expected_tables)
    if missing_tables or extra_tables:
        if missing_tables:
            sys.stderr.write(f"missing tables: {', '.join(missing_tables)}\n")
        if extra_tables:
            sys.stderr.write(f"unexpected tables: {', '.join(extra_tables)}\n")
        return EXIT_TABLE_SET_MISMATCH

    if args.verbose:
        sys.stderr.write(f"table set verified ({len(actual_tables)} tables)\n")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migration_round_trip


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'migration-round-trip.db').as_posix()}"


def _apply_tables(sqlite_url: str, tables: set[str]) -> None:
    db_path = Path(sqlite_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        existing = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        for table in existing:
            if table.startswith("sqlite_"):
                continue
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        for table in sorted(tables):
            conn.execute(f'CREATE TABLE "{table}" (id INTEGER)')
        conn.commit()


def test_migration_round_trip_main_returns_zero_with_explicit_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sqlite_url = _sqlite_url(tmp_path)
    expected_tables = {"sessions", "review_queue", "alembic_version"}
    state = {"current_revision": ""}
    calls: list[tuple[str, ...]] = []

    def _fake_run_alembic(command: list[str], *, database_url: str, verbose: bool) -> subprocess.CompletedProcess[str]:
        assert database_url == sqlite_url
        assert verbose is False
        calls.append(tuple(command))
        if command == ["heads"]:
            return subprocess.CompletedProcess(command, 0, stdout="017 (head)\n", stderr="")
        if command == ["upgrade", "head"]:
            _apply_tables(sqlite_url, expected_tables)
            state["current_revision"] = "017"
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["current"]:
            stdout = f"{state['current_revision']} (head)\n" if state["current_revision"] else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if command == ["downgrade", "base"]:
            _apply_tables(sqlite_url, set())
            state["current_revision"] = ""
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(migration_round_trip, "_expected_tables", lambda: expected_tables)
    monkeypatch.setattr(migration_round_trip, "_run_alembic", _fake_run_alembic)

    rc = migration_round_trip.main(["--database-url", sqlite_url])

    assert rc == 0
    assert calls == [
        ("heads",),
        ("upgrade", "head"),
        ("current",),
        ("downgrade", "base"),
        ("current",),
        ("upgrade", "head"),
    ]


def test_migration_round_trip_main_uses_database_url_env_and_reports_table_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sqlite_url = _sqlite_url(tmp_path)
    expected_tables = {"sessions", "review_queue", "alembic_version"}
    state = {"current_revision": ""}

    def _fake_run_alembic(command: list[str], *, database_url: str, verbose: bool) -> subprocess.CompletedProcess[str]:
        assert database_url == sqlite_url
        assert verbose is False
        if command == ["heads"]:
            return subprocess.CompletedProcess(command, 0, stdout="017 (head)\n", stderr="")
        if command == ["upgrade", "head"]:
            _apply_tables(sqlite_url, {"sessions", "alembic_version"})
            state["current_revision"] = "017"
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["current"]:
            stdout = f"{state['current_revision']} (head)\n" if state["current_revision"] else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if command == ["downgrade", "base"]:
            _apply_tables(sqlite_url, set())
            state["current_revision"] = ""
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(migration_round_trip, "_expected_tables", lambda: expected_tables)
    monkeypatch.setattr(migration_round_trip, "_run_alembic", _fake_run_alembic)

    rc = migration_round_trip.main([])
    captured = capsys.readouterr()

    assert rc == migration_round_trip.EXIT_TABLE_SET_MISMATCH
    assert "missing tables" in captured.err
    assert "review_queue" in captured.err

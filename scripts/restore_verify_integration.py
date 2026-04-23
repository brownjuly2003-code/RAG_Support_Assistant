#!/usr/bin/env python3
"""Disposable Postgres wrapper around scripts.restore_verify (task-173)."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import restore_verify  # noqa: E402

COMPOSE_FILE = PROJECT_ROOT / "docker-compose.test.yml"
POSTGRES_SERVICE = "postgres-test"
POSTGRES_DB = "rag_restore_test"
POSTGRES_USER = "rag"
POSTGRES_PASSWORD = "rag_test"


def _compose_base() -> list[str]:
    if shutil.which("docker-compose"):
        return ["docker-compose", "-f", str(COMPOSE_FILE)]
    if shutil.which("docker"):
        return ["docker", "compose", "-f", str(COMPOSE_FILE)]
    raise FileNotFoundError("docker compose CLI not found")


def _run_compose(compose_base: list[str], args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        compose_base + args,
        check=check,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


def _wait_for_pg_ready(compose_base: list[str], *, timeout_sec: int = 90) -> None:
    deadline = time.monotonic() + timeout_sec
    last_detail = "pg_isready did not report healthy"
    while time.monotonic() < deadline:
        result = _run_compose(
            compose_base,
            ["exec", "-T", POSTGRES_SERVICE, "pg_isready", "-U", POSTGRES_USER, "-d", POSTGRES_DB],
            check=False,
        )
        if result.returncode == 0:
            return
        last_detail = (result.stderr or result.stdout).strip() or last_detail
        time.sleep(2)
    raise RuntimeError(f"postgres-test did not become ready within {timeout_sec}s: {last_detail}")


def _resolve_host_port(compose_base: list[str]) -> str:
    result = _run_compose(compose_base, ["port", POSTGRES_SERVICE, "5432"])
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("docker compose port returned empty output")
    return output.splitlines()[-1].rsplit(":", 1)[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--age-identity-file", default=None)
    parser.add_argument("--age-passphrase-file", default=None)
    args = parser.parse_args(argv)

    snapshot_dir = Path(args.snapshot)
    if not snapshot_dir.exists():
        sys.stderr.write(f"snapshot path not found: {snapshot_dir}\n")
        return restore_verify.EXIT_INFRA_ERROR
    if not COMPOSE_FILE.exists():
        sys.stderr.write(f"compose file not found: {COMPOSE_FILE}\n")
        return restore_verify.EXIT_INFRA_ERROR

    compose_base: list[str] | None = None
    exit_code = restore_verify.EXIT_INFRA_ERROR
    cleanup_failed = False

    try:
        compose_base = _compose_base()
        _run_compose(compose_base, ["up", "-d", POSTGRES_SERVICE])
        _wait_for_pg_ready(compose_base)
        port = _resolve_host_port(compose_base)
        postgres_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{port}/{POSTGRES_DB}"
        restore_args = ["--snapshot", str(snapshot_dir), f"--postgres-url={postgres_url}"]
        if args.report:
            restore_args.extend(["--report", args.report])
        if args.age_identity_file:
            restore_args.extend(["--age-identity-file", args.age_identity_file])
        if args.age_passphrase_file:
            restore_args.extend(["--age-passphrase-file", args.age_passphrase_file])
        exit_code = restore_verify.main(restore_args)
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return restore_verify.EXIT_INFRA_ERROR
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        sys.stderr.write(f"docker compose command failed: {detail}\n")
        return restore_verify.EXIT_INFRA_ERROR
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return restore_verify.EXIT_INFRA_ERROR
    finally:
        if compose_base is not None:
            cleanup = _run_compose(compose_base, ["down", "-v"], check=False)
            if cleanup.returncode != 0:
                cleanup_failed = True
                detail = (cleanup.stderr or cleanup.stdout).strip() or "docker compose down -v failed"
                sys.stderr.write(f"{detail}\n")

    if cleanup_failed and exit_code == restore_verify.EXIT_OK:
        return restore_verify.EXIT_INFRA_ERROR
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

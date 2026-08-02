"""Runtime contracts for Helm/Postgres-aware backup snapshots (OPS-01 follow-up).

Static Dockerfile + Helm assertions always run. pg_dump behavior is exercised
via subprocess stubs so no live Postgres, Docker, or real secrets are required.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backup_snapshot

ROOT = Path(__file__).resolve().parent.parent
HELM_DIR = ROOT / "deploy" / "helm"
TEMPLATES = HELM_DIR / "templates"
VALUES = HELM_DIR / "values.yaml"
DOCKERFILE = ROOT / "Dockerfile"

_HELM = shutil.which("helm")
requires_helm = pytest.mark.skipif(_HELM is None, reason="helm binary not available")

# Synthetic credentials only — never real environment values.
_FAKE_PASSWORD = "unit-test-db-password-not-real"
_FAKE_USER = "backup_user"


def _make_project_root(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    (project_root / "data" / "tracing").mkdir(parents=True)
    (project_root / "data" / "uploads").mkdir(parents=True)
    (project_root / "data" / "vectordb" / "chroma").mkdir(parents=True)
    (project_root / "alembic" / "versions").mkdir(parents=True)
    (project_root / "data" / "tracing" / "traces.db").write_bytes(b"")
    (project_root / "data" / "uploads" / "doc.txt").write_text("x", encoding="utf-8")
    (project_root / "data" / "vectordb" / "chroma" / "marker").write_text("c", encoding="utf-8")
    (project_root / "alembic" / "versions" / "017_curated_case_status.py").write_text(
        "# migration",
        encoding="utf-8",
    )
    return project_root


def _capture_pg_dump(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> dict:
    """Stub subprocess.run used by _pg_dump; record argv/env without real pg_dump."""
    captured: dict = {"calls": []}

    def _fake_run(cmd, check=True, stdout=None, stderr=None, env=None, **kwargs):  # noqa: ANN001
        record = {"cmd": list(cmd), "env": dict(env) if env is not None else None}
        captured["calls"].append(record)
        captured["cmd"] = record["cmd"]
        captured["env"] = record["env"]
        if fail:
            if stdout is not None:
                stdout.write(b"PARTIAL_DUMP")
                stdout.flush()
            raise subprocess.CalledProcessError(returncode=2, cmd=list(cmd))
        if stdout is not None:
            stdout.write(b"PGDMP_FAKE")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(backup_snapshot.subprocess, "run", _fake_run)
    return captured


def _assert_no_password_leak(*parts: object) -> None:
    blob = " ".join(str(p) for p in parts)
    assert _FAKE_PASSWORD not in blob


# ---------------------------------------------------------------------------
# URL / env resolution contracts
# ---------------------------------------------------------------------------


def test_database_url_env_fallback_when_postgres_url_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@db.example:5432/rag",
    )

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=True,
    )

    components = {c.name: c for c in manifest.components}
    assert components["postgres"].status == "ok"
    assert captured["calls"], "pg_dump subprocess was not invoked"
    cmd_blob = " ".join(captured["cmd"])
    assert "db.example" in cmd_blob
    _assert_no_password_leak(captured["cmd"], components["postgres"].detail)


def test_postgres_url_wins_over_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    monkeypatch.setenv(
        "POSTGRES_URL",
        f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@from-postgres:5432/rag",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@from-database:5432/rag",
    )

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=None,
        skip_chroma=True,
    )

    cmd_blob = " ".join(captured["cmd"])
    assert "from-postgres" in cmd_blob
    assert "from-database" not in cmd_blob


def test_explicit_database_url_argument_wins_over_both_env_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    monkeypatch.setenv(
        "POSTGRES_URL",
        f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@from-postgres:5432/rag",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@from-database:5432/rag",
    )

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@from-arg:5432/rag",
        skip_chroma=True,
    )

    cmd_blob = " ".join(captured["cmd"])
    assert "from-arg" in cmd_blob
    assert "from-postgres" not in cmd_blob
    assert "from-database" not in cmd_blob


def test_sqlalchemy_driver_scheme_normalized_for_pg_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=(
            f"postgresql+asyncpg://{_FAKE_USER}:{_FAKE_PASSWORD}@db.example:5432/rag"
        ),
        skip_chroma=True,
    )

    cmd_blob = " ".join(captured["cmd"])
    assert "asyncpg" not in cmd_blob
    assert re.search(r"postgresql://", cmd_blob)
    assert "db.example" in cmd_blob


def test_password_only_in_child_pgpassword_not_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=(
            f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@db.example:5432/rag?sslmode=require"
        ),
        skip_chroma=True,
    )

    assert captured["env"] is not None
    assert captured["env"].get("PGPASSWORD") == _FAKE_PASSWORD
    for part in captured["cmd"]:
        assert _FAKE_PASSWORD not in part
        assert f":{_FAKE_PASSWORD}@" not in part


def test_query_parameters_survive_normalization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=(
            f"postgresql+psycopg2://{_FAKE_USER}:{_FAKE_PASSWORD}"
            f"@db.example:5432/rag?sslmode=require&application_name=backup"
        ),
        skip_chroma=True,
    )

    cmd_blob = " ".join(captured["cmd"])
    assert "sslmode=require" in cmd_blob
    assert "application_name=backup" in cmd_blob
    assert "psycopg2" not in cmd_blob
    _assert_no_password_leak(cmd_blob)


def test_percent_encoded_userinfo_decoded_once_for_pg_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Encoded @/: in userinfo must not double-encode; password only in env."""
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    # Synthetic percent-encoded credentials only (not real secrets).
    encoded_user = "backup%40ops"
    encoded_password = "p%40ss%3Aword"
    raw_password = "p@ss:word"

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url=(
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@db.example:5432/rag?sslmode=require"
        ),
        skip_chroma=True,
    )

    cmd_blob = " ".join(captured["cmd"])
    # Username re-encoded exactly once (not %2540).
    assert "backup%40ops" in cmd_blob
    assert "backup%2540ops" not in cmd_blob
    assert "asyncpg" not in cmd_blob
    assert "sslmode=require" in cmd_blob
    assert re.search(r"postgresql://", cmd_blob)

    assert captured["env"] is not None
    assert captured["env"].get("PGPASSWORD") == raw_password

    components = {c.name: c for c in manifest.components}
    detail = components["postgres"].detail or ""
    for secret_form in (encoded_password, raw_password):
        assert secret_form not in cmd_blob
        assert secret_form not in detail
        for part in captured["cmd"]:
            assert secret_form not in part
        assert f":{secret_form}@" not in cmd_blob


def test_non_postgres_scheme_rejected_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup"
    captured = _capture_pg_dump(monkeypatch)

    manifest = backup_snapshot.create_snapshot(
        out_dir=out_dir,
        project_root=project_root,
        database_url="mysql://user:pass@host/db",
        skip_chroma=True,
    )

    components = {c.name: c for c in manifest.components}
    assert components["postgres"].status == "failed"
    detail = components["postgres"].detail or ""
    assert "mysql" in detail.lower() or "unsupported" in detail.lower()
    assert not captured["calls"]


def test_partial_dump_removed_and_failure_redacted_nonzero_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = _make_project_root(tmp_path)
    out_dir = tmp_path / "backup-fail"
    _capture_pg_dump(monkeypatch, fail=True)
    monkeypatch.setattr(backup_snapshot, "PROJECT_ROOT", project_root)

    url = f"postgresql://{_FAKE_USER}:{_FAKE_PASSWORD}@db.example:5432/rag"
    rc = backup_snapshot.main(["--out", str(out_dir), "--skip-chroma", "--database-url", url])

    assert rc != 0
    dump_path = out_dir / "postgres" / "postgres.dump"
    assert not dump_path.exists()

    manifest = json.loads((out_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    components = {c["name"]: c for c in manifest["components"]}
    assert components["postgres"]["status"] == "failed"
    detail = components["postgres"]["detail"] or ""
    assert _FAKE_PASSWORD not in detail
    assert _FAKE_PASSWORD not in json.dumps(manifest)


def test_module_help_mentions_database_url_fallback() -> None:
    text = Path(backup_snapshot.__file__).read_text(encoding="utf-8")
    assert "DATABASE_URL" in text
    assert "POSTGRES_URL" in text
    # Help / status must not claim POSTGRES_URL is the only fallback.
    assert "falls back to POSTGRES_URL env)" not in text


# ---------------------------------------------------------------------------
# Dockerfile runtime tool contracts (static; image build is an external gate)
# ---------------------------------------------------------------------------


def test_dockerfile_installs_pg_tools_and_age_as_non_root() -> None:
    """Static contract: image must ship pg_dump/pg_restore + age, run as app.

    Docker build / binary smoke remains an external gate (Docker unavailable
    in this verification environment).
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "postgresql-client" in text
    # age package (encryption) alongside client tools
    assert re.search(r"\bage\b", text)
    assert "--no-install-recommends" in text
    assert "rm -rf /var/lib/apt/lists/*" in text
    assert "USER app" in text
    # Non-root user must remain after package installation layer
    user_idx = text.rfind("USER app")
    apt_idx = text.find("postgresql-client")
    assert apt_idx != -1 and user_idx != -1
    assert apt_idx < user_idx
    assert '"--workers", "1"' in text or "'--workers', '1'" in text


# ---------------------------------------------------------------------------
# Helm backup CronJob env contracts
# ---------------------------------------------------------------------------


def _helm_template(*extra: str) -> subprocess.CompletedProcess[str]:
    assert _HELM is not None
    cmd = [
        _HELM,
        "template",
        "rag-test",
        str(HELM_DIR),
        "--values",
        str(VALUES),
        "--set",
        "env.CORS_ORIGINS=https://support.example.com",
        "--set",
        "postgresql.auth.password=ci-placeholder",
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _cron_by_name(docs: list[dict], name: str) -> dict:
    for doc in docs:
        if doc.get("kind") == "CronJob" and doc["metadata"]["name"] == name:
            return doc
    raise AssertionError(f"CronJob {name!r} not found")


def _postgres_url_env(container: dict) -> dict:
    for item in container.get("env") or []:
        if item.get("name") == "POSTGRES_URL":
            return item
    raise AssertionError("POSTGRES_URL env entry not found on backup container")


@requires_helm
def test_rendered_backup_cronjob_maps_postgres_url_from_secret_database_url() -> None:
    # External existingSecret
    external = _helm_template("--set", "secrets.existingSecret=ci-placeholder")
    assert external.returncode == 0, external.stderr
    snap = _cron_by_name(_docs(external.stdout), "rag-test-backup-snapshot")
    container = snap["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    pg_env = _postgres_url_env(container)
    assert pg_env["valueFrom"]["secretKeyRef"]["name"] == "ci-placeholder"
    assert pg_env["valueFrom"]["secretKeyRef"]["key"] == "DATABASE_URL"

    # Chart-managed secret name
    managed = _helm_template(
        "--set",
        "secrets.existingSecret=",
        "--set",
        "secrets.DATABASE_URL=postgresql://ci:ci@db/rag",
        "--set",
        "secrets.JWT_SECRET=ci-jwt",
        "--set",
        "secrets.SESSION_SECRET_KEY=ci-session",
        "--set",
        "secrets.ADMIN_PASSWORD_HASH=ci-hash",
        "--set",
        "secrets.DB_ENCRYPTION_KEY=ci-enc-key",
    )
    assert managed.returncode == 0, managed.stderr
    snap_m = _cron_by_name(_docs(managed.stdout), "rag-test-backup-snapshot")
    container_m = snap_m["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    pg_env_m = _postgres_url_env(container_m)
    assert pg_env_m["valueFrom"]["secretKeyRef"]["name"] == "rag-test-secrets"
    assert pg_env_m["valueFrom"]["secretKeyRef"]["key"] == "DATABASE_URL"

    # Neither rendered command nor env may contain a literal DSN
    for rendered in (external.stdout, managed.stdout):
        snap_docs = [
            d
            for d in _docs(rendered)
            if d.get("kind") == "CronJob" and d["metadata"]["name"] == "rag-test-backup-snapshot"
        ]
        assert snap_docs
        blob = yaml.dump(snap_docs[0])
        assert "postgresql://" not in blob
        assert "postgres://" not in blob


@requires_helm
def test_restore_verify_has_no_production_db_wiring() -> None:
    result = _helm_template("--set", "secrets.existingSecret=ci-placeholder")
    assert result.returncode == 0, result.stderr
    restore = _cron_by_name(_docs(result.stdout), "rag-test-restore-verify")
    container = restore["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    env_names = {e.get("name") for e in (container.get("env") or [])}
    assert "POSTGRES_URL" not in env_names
    command = container.get("command") or []
    command_blob = " ".join(str(c) for c in command)
    assert "--database-url" not in command_blob
    assert "postgresql://" not in command_blob
    # Source template must not introduce production DSN wiring either
    src = (TEMPLATES / "cronjob-restore-verify.yaml").read_text(encoding="utf-8")
    assert "POSTGRES_URL" not in src
    assert "secretKeyRef" not in src or "DATABASE_URL" not in src

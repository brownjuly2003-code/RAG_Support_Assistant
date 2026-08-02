from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
HELM_DIR = ROOT / "deploy" / "helm"
TEMPLATES = HELM_DIR / "templates"
VALUES = HELM_DIR / "values.yaml"

_HELM = shutil.which("helm")
requires_helm = pytest.mark.skipif(_HELM is None, reason="helm binary not available")

_BASE_SET = [
    "--set",
    "secrets.existingSecret=ci-placeholder",
    "--set",
    "env.CORS_ORIGINS=https://support.example.com",
    "--set",
    "postgresql.auth.password=ci-placeholder",
]


def _load_rendered_yaml(path: Path) -> dict:
    """Parse a Helm template after stripping Go template placeholders."""
    raw = path.read_text(encoding="utf-8")
    # Drop pure control-flow directive lines so structure stays parseable when
    # CronJobs are gated behind persistence conditionals.
    without_control = re.sub(
        r"^\s*\{\{-?\s*(if|else|else if|end|with|range|define|block)[\s\S]*?\}\}\s*$",
        "",
        raw,
        flags=re.MULTILINE,
    )
    # Replace remaining `{{ ... }}` placeholders with a harmless literal so
    # PyYAML can parse the structure for schema-level assertions.
    stripped = re.sub(r"\{\{[^}]*\}\}", "placeholder", without_control)
    return yaml.safe_load(stripped)


def _helm_template(*extra: str) -> subprocess.CompletedProcess[str]:
    assert _HELM is not None
    cmd = [
        _HELM,
        "template",
        "rag-test",
        str(HELM_DIR),
        "--values",
        str(VALUES),
        *_BASE_SET,
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


def test_cronjob_backup_snapshot_shape() -> None:
    doc = _load_rendered_yaml(TEMPLATES / "cronjob-backup-snapshot.yaml")
    assert doc["kind"] == "CronJob"
    assert doc["spec"]["schedule"] == "0 1 * * *"
    containers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    assert containers[0]["command"][:2] == ["python", "scripts/backup_snapshot.py"]


def test_cronjob_backup_integrity_shape() -> None:
    doc = _load_rendered_yaml(TEMPLATES / "cronjob-backup-integrity.yaml")
    assert doc["kind"] == "CronJob"
    assert doc["spec"]["schedule"].startswith("0 5 * * 0")
    containers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    assert containers[0]["command"][:2] == ["python", "scripts/backup_integrity.py"]


def test_cronjob_restore_verify_shape() -> None:
    doc = _load_rendered_yaml(TEMPLATES / "cronjob-restore-verify.yaml")
    assert doc["kind"] == "CronJob"
    assert doc["spec"]["schedule"].startswith("0 4 * * 0")
    containers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    assert containers[0]["command"][0] == "sh"


def test_cronjob_curated_staleness_shape() -> None:
    doc = _load_rendered_yaml(TEMPLATES / "cronjob-curated-staleness.yaml")
    assert doc["kind"] == "CronJob"
    assert doc["spec"]["schedule"].startswith("0 3 * * *")
    containers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    assert containers[0]["command"][:2] == ["python", "scripts/detect_stale_curated_cases.py"]
    assert "--apply" in containers[0]["command"]


def test_storage_cronjobs_use_claim_helpers_not_hardcoded_release_names() -> None:
    """Source contract: claim names must go through helpers, not Release.Name-*.

    Hard-coded ``{{ .Release.Name }}-backups`` / ``-reports`` prevent
    ``existingClaim`` overrides and bypass shared helpers.
    """
    files = {
        "cronjob-backup-snapshot.yaml": ("dataClaimName", "backupsClaimName"),
        "cronjob-backup-integrity.yaml": ("backupsClaimName", "reportsClaimName"),
        "cronjob-restore-verify.yaml": ("backupsClaimName", "reportsClaimName"),
        "cronjob-curated-staleness.yaml": ("reportsClaimName",),
    }
    for filename, helpers in files.items():
        src = (TEMPLATES / filename).read_text(encoding="utf-8")
        for helper in helpers:
            assert helper in src, f"{filename} missing helper {helper}"
        assert "claimName: {{ .Release.Name }}-backups" not in src
        assert "claimName: {{ .Release.Name }}-reports" not in src
        assert "claimName: {{ .Release.Name }}-data" not in src


def test_storage_cronjobs_declare_required_persistence_gates() -> None:
    gates = {
        "cronjob-backup-snapshot.yaml": ("persistence.data.enabled", "persistence.backups.enabled"),
        "cronjob-backup-integrity.yaml": (
            "persistence.backups.enabled",
            "persistence.reports.enabled",
        ),
        "cronjob-restore-verify.yaml": (
            "persistence.backups.enabled",
            "persistence.reports.enabled",
        ),
        "cronjob-curated-staleness.yaml": ("persistence.reports.enabled",),
    }
    for filename, required in gates.items():
        src = (TEMPLATES / filename).read_text(encoding="utf-8")
        for gate in required:
            assert gate in src, f"{filename} missing gate {gate}"


def test_backup_snapshot_shape_includes_data_volume_mount() -> None:
    doc = _load_rendered_yaml(TEMPLATES / "cronjob-backup-snapshot.yaml")
    pod = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    mounts = {m["name"]: m for m in container["volumeMounts"]}
    assert mounts["data"]["mountPath"] == "/app/data"
    assert mounts["data"].get("readOnly") is True or mounts["data"].get("readOnly") == "placeholder"
    assert mounts["backups"]["mountPath"] == "/backups"
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert "data" in volumes
    assert "backups" in volumes


def test_storage_cronjobs_preserve_resources_restart_backoff() -> None:
    for filename in (
        "cronjob-backup-snapshot.yaml",
        "cronjob-backup-integrity.yaml",
        "cronjob-restore-verify.yaml",
        "cronjob-curated-staleness.yaml",
    ):
        doc = _load_rendered_yaml(TEMPLATES / filename)
        job_spec = doc["spec"]["jobTemplate"]["spec"]
        pod = job_spec["template"]["spec"]
        assert job_spec["backoffLimit"] == 6
        assert pod["restartPolicy"] == "OnFailure"
        container = pod["containers"][0]
        assert "resources" in container
        assert "securityContext" in pod or "podSecurityContext" in (
            TEMPLATES / filename
        ).read_text(encoding="utf-8")


@requires_helm
def test_rendered_storage_cronjobs_keep_schedules_commands_and_limits() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)

    snapshot = _cron_by_name(docs, "rag-test-backup-snapshot")
    assert snapshot["spec"]["schedule"] == "0 1 * * *"
    snap_c = snapshot["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert snap_c["command"][:2] == ["python", "scripts/backup_snapshot.py"]
    assert snapshot["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 6
    assert snapshot["spec"]["jobTemplate"]["spec"]["template"]["spec"]["restartPolicy"] == "OnFailure"

    integrity = _cron_by_name(docs, "rag-test-backup-integrity")
    assert integrity["spec"]["schedule"] == "0 5 * * 0"
    int_c = integrity["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert int_c["command"][:2] == ["python", "scripts/backup_integrity.py"]

    restore = _cron_by_name(docs, "rag-test-restore-verify")
    assert restore["spec"]["schedule"] == "0 4 * * 0"
    rest_c = restore["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert rest_c["command"][0] == "sh"

    curated = _cron_by_name(docs, "rag-test-curated-staleness")
    assert curated["spec"]["schedule"] == "0 3 * * *"
    cur_c = curated["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert cur_c["command"][:2] == ["python", "scripts/detect_stale_curated_cases.py"]
    assert "--apply" in cur_c["command"]

    for job in (snapshot, integrity, restore, curated):
        pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert "fsGroup" in pod["securityContext"]
        assert pod["securityContext"]["fsGroupChangePolicy"] == "OnRootMismatch"
        c = pod["containers"][0]
        assert c["securityContext"]["runAsNonRoot"] is True
        assert c["securityContext"]["allowPrivilegeEscalation"] is False
        assert "resources" in c


@requires_helm
def test_rendered_claim_helpers_resolve_existing_and_default_names() -> None:
    default = _helm_template()
    assert default.returncode == 0, default.stderr
    snap = _cron_by_name(_docs(default.stdout), "rag-test-backup-snapshot")
    vols = {
        v["name"]: v for v in snap["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    }
    assert vols["data"]["persistentVolumeClaim"]["claimName"] == "rag-test-data"
    assert vols["backups"]["persistentVolumeClaim"]["claimName"] == "rag-test-backups"

    existing = _helm_template(
        "--set",
        "persistence.data.existingClaim=ops-data",
        "--set",
        "persistence.backups.existingClaim=ops-backups",
        "--set",
        "persistence.reports.existingClaim=ops-reports",
    )
    assert existing.returncode == 0, existing.stderr
    docs = _docs(existing.stdout)
    snap = _cron_by_name(docs, "rag-test-backup-snapshot")
    vols = {
        v["name"]: v for v in snap["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    }
    assert vols["data"]["persistentVolumeClaim"]["claimName"] == "ops-data"
    assert vols["backups"]["persistentVolumeClaim"]["claimName"] == "ops-backups"
    integrity = _cron_by_name(docs, "rag-test-backup-integrity")
    ivols = {
        v["name"]: v for v in integrity["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    }
    assert ivols["reports"]["persistentVolumeClaim"]["claimName"] == "ops-reports"

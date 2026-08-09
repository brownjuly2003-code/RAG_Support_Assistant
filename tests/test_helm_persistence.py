"""Helm durable storage contracts (OPS-01 / P0).

Static/source assertions always run. Helm-render tests skip individually
only when the ``helm`` binary is absent.
"""
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


def _load_values() -> dict:
    return yaml.safe_load(VALUES.read_text(encoding="utf-8"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def _by_kind(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _pvc_names(docs: list[dict]) -> set[str]:
    return {d["metadata"]["name"] for d in _by_kind(docs, "PersistentVolumeClaim")}


def _cronjob_names(docs: list[dict]) -> set[str]:
    return {d["metadata"]["name"] for d in _by_kind(docs, "CronJob")}


def _claim_refs(docs: list[dict]) -> set[str]:
    names: set[str] = set()
    for doc in docs:
        text = yaml.dump(doc)
        for match in re.finditer(r"claimName:\s*(\S+)", text):
            names.add(match.group(1).strip("\"'"))
    return names


# ---------------------------------------------------------------------------
# Static / source contracts (no Helm required)
# ---------------------------------------------------------------------------


def test_values_enable_managed_persistence_stores() -> None:
    values = _load_values()
    persistence = values["persistence"]
    for store, size in (("data", "10Gi"), ("backups", "20Gi"), ("reports", "5Gi")):
        cfg = persistence[store]
        assert cfg["enabled"] is True
        assert cfg["existingClaim"] == ""
        assert "storageClass" in cfg
        assert cfg["accessModes"] == ["ReadWriteOnce"]
        assert cfg["size"] == size


def test_values_define_security_contexts() -> None:
    values = _load_values()
    pod = values["podSecurityContext"]
    container = values["containerSecurityContext"]
    assert pod["runAsNonRoot"] is True
    assert "fsGroup" in pod
    assert pod["fsGroupChangePolicy"] == "OnRootMismatch"
    assert pod["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["runAsNonRoot"] is True
    assert container["allowPrivilegeEscalation"] is False
    assert container["capabilities"]["drop"] == ["ALL"]
    assert "runAsUser" not in pod
    assert "runAsUser" not in container
    assert container.get("readOnlyRootFilesystem") is not True


def test_helm_secret_supports_opencode_zen_api_key() -> None:
    values = _load_values()
    assert values["secrets"]["OPENCODE_ZEN_API_KEY"] == ""
    secret_template = _read(TEMPLATES / "secret.yaml")
    assert '"OPENCODE_ZEN_API_KEY"' in secret_template


def test_helpers_define_claim_name_functions() -> None:
    helpers = _read(TEMPLATES / "_helpers.tpl")
    for name in (
        "rag-support-assistant.dataClaimName",
        "rag-support-assistant.backupsClaimName",
        "rag-support-assistant.reportsClaimName",
    ):
        assert f'define "{name}"' in helpers
    assert "existingClaim" in helpers
    assert "-data" in helpers
    assert "-backups" in helpers
    assert "-reports" in helpers


def test_pvc_template_exists_and_is_conditional() -> None:
    pvc = _read(TEMPLATES / "pvc.yaml")
    assert "kind: PersistentVolumeClaim" in pvc
    assert "persistence.data" in pvc
    assert "persistence.backups" in pvc
    assert "persistence.reports" in pvc
    assert "existingClaim" in pvc
    assert "storageClassName" in pvc
    assert "accessModes" in pvc
    assert "resources:" in pvc
    # No invented default StorageClass; only when configured.
    assert "storageClassName:" in pvc
    assert "helm.sh/resource-policy" not in pvc
    assert "pre-delete" not in pvc
    assert "post-delete" not in pvc


def test_deployment_mounts_data_and_security_and_checksums() -> None:
    dep = _read(TEMPLATES / "deployment.yaml")
    assert "/app/data" in dep
    assert "dataClaimName" in dep or "persistence.data" in dep
    assert "podSecurityContext" in dep
    assert "containerSecurityContext" in dep
    assert "checksum/config" in dep
    assert "checksum/secret" in dep
    assert "persistence.data.enabled" in dep
    assert "fail" in dep
    assert "production" in dep


def test_deployment_readiness_is_storage_aware_when_data_enabled() -> None:
    dep = _read(TEMPLATES / "deployment.yaml")
    assert "readinessProbe:" in dep
    assert "exec:" in dep
    assert "/app/data" in dep
    assert "ismount" in dep or "is_mount" in dep
    assert "/api/health/ready" in dep
    assert "127.0.0.1:8000" in dep or "localhost:8000" in dep
    # Write/delete probe contract
    assert "unlink" in dep or "remove" in dep or ".unlink" in dep
    # Timing preserved
    assert "initialDelaySeconds: 10" in dep
    assert "periodSeconds: 10" in dep
    assert "failureThreshold: 2" in dep
    # Liveness unchanged (HTTP)
    assert "livenessProbe:" in dep
    assert "/api/health/live" in dep


def test_backup_snapshot_template_uses_helpers_and_data_mount() -> None:
    src = _read(TEMPLATES / "cronjob-backup-snapshot.yaml")
    assert "persistence.data.enabled" in src
    assert "persistence.backups.enabled" in src
    assert "dataClaimName" in src
    assert "backupsClaimName" in src
    assert "/app/data" in src
    assert "readOnly: true" in src
    assert "podSecurityContext" in src
    assert "containerSecurityContext" in src
    # No hard-coded release-name claim pattern for backups
    assert "claimName: {{ .Release.Name }}-backups" not in src


def test_backup_integrity_template_conditional_helpers() -> None:
    src = _read(TEMPLATES / "cronjob-backup-integrity.yaml")
    assert "persistence.backups.enabled" in src
    assert "persistence.reports.enabled" in src
    assert "backupsClaimName" in src
    assert "reportsClaimName" in src
    assert "claimName: {{ .Release.Name }}-backups" not in src
    assert "claimName: {{ .Release.Name }}-reports" not in src
    assert "podSecurityContext" in src


def test_restore_verify_template_conditional_helpers() -> None:
    src = _read(TEMPLATES / "cronjob-restore-verify.yaml")
    assert "persistence.backups.enabled" in src
    assert "persistence.reports.enabled" in src
    assert "backupsClaimName" in src
    assert "reportsClaimName" in src
    assert "claimName: {{ .Release.Name }}-backups" not in src
    assert "claimName: {{ .Release.Name }}-reports" not in src
    assert "podSecurityContext" in src


def test_curated_staleness_template_conditional_helpers() -> None:
    src = _read(TEMPLATES / "cronjob-curated-staleness.yaml")
    assert "persistence.reports.enabled" in src
    assert "reportsClaimName" in src
    assert "claimName: {{ .Release.Name }}-reports" not in src
    assert "podSecurityContext" in src


# ---------------------------------------------------------------------------
# Helm-render contracts
# ---------------------------------------------------------------------------


@requires_helm
def test_default_render_creates_three_pvcs_and_resolves_claims() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    pvcs = _pvc_names(docs)
    assert pvcs == {"rag-test-data", "rag-test-backups", "rag-test-reports"}

    for name, size in (
        ("rag-test-data", "10Gi"),
        ("rag-test-backups", "20Gi"),
        ("rag-test-reports", "5Gi"),
    ):
        pvc = next(d for d in _by_kind(docs, "PersistentVolumeClaim") if d["metadata"]["name"] == name)
        assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert pvc["spec"]["resources"]["requests"]["storage"] == size
        assert "storageClassName" not in pvc["spec"]

    refs = _claim_refs(docs)
    # Every PVC reference must resolve to a rendered claim (or known name).
    for ref in refs:
        assert ref in pvcs, f"unresolved claimName {ref!r}; rendered={pvcs}"


@requires_helm
def test_existing_claim_render_skips_managed_pvcs() -> None:
    result = _helm_template(
        "--set",
        "persistence.data.existingClaim=ext-data",
        "--set",
        "persistence.backups.existingClaim=ext-backups",
        "--set",
        "persistence.reports.existingClaim=ext-reports",
    )
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    assert _pvc_names(docs) == set()

    dep = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"] == "rag-test-app")
    volumes = {v["name"]: v for v in dep["spec"]["template"]["spec"]["volumes"]}
    assert volumes["data"]["persistentVolumeClaim"]["claimName"] == "ext-data"

    snapshot = next(
        d for d in _by_kind(docs, "CronJob") if d["metadata"]["name"] == "rag-test-backup-snapshot"
    )
    snap_vols = {
        v["name"]: v for v in snapshot["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    }
    assert snap_vols["data"]["persistentVolumeClaim"]["claimName"] == "ext-data"
    assert snap_vols["backups"]["persistentVolumeClaim"]["claimName"] == "ext-backups"

    integrity = next(
        d for d in _by_kind(docs, "CronJob") if d["metadata"]["name"] == "rag-test-backup-integrity"
    )
    int_vols = {
        v["name"]: v for v in integrity["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    }
    assert int_vols["backups"]["persistentVolumeClaim"]["claimName"] == "ext-backups"
    assert int_vols["reports"]["persistentVolumeClaim"]["claimName"] == "ext-reports"


@requires_helm
def test_production_fails_when_data_persistence_disabled() -> None:
    result = _helm_template("--set", "persistence.data.enabled=false")
    assert result.returncode != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "persistence.data" in combined.lower() or "data persistence" in combined.lower() or "persistence.data.enabled" in combined


@requires_helm
def test_deployment_mounts_data_security_checksums_and_readiness() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    dep = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"] == "rag-test-app")
    pod_spec = dep["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    mounts = {m["name"]: m for m in container["volumeMounts"]}
    assert mounts["data"]["mountPath"] == "/app/data"
    assert mounts["data"].get("readOnly") in (None, False)

    volumes = {v["name"]: v for v in pod_spec["volumes"]}
    assert volumes["data"]["persistentVolumeClaim"]["claimName"] == "rag-test-data"

    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert "fsGroup" in pod_spec["securityContext"]
    assert pod_spec["securityContext"]["fsGroupChangePolicy"] == "OnRootMismatch"
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert "ALL" in container["securityContext"]["capabilities"]["drop"]
    assert "runAsUser" not in pod_spec["securityContext"]
    assert "runAsUser" not in container["securityContext"]

    annotations = dep["spec"]["template"]["metadata"]["annotations"]
    assert "checksum/config" in annotations
    assert "checksum/secret" in annotations
    assert re.fullmatch(r"[0-9a-f]{64}", annotations["checksum/config"])
    assert re.fullmatch(r"[0-9a-f]{64}", annotations["checksum/secret"])

    readiness = container["readinessProbe"]
    assert "exec" in readiness
    assert "httpGet" not in readiness
    cmd = " ".join(readiness["exec"]["command"])
    assert "/app/data" in cmd
    assert "/api/health/ready" in cmd
    assert readiness["initialDelaySeconds"] == 10
    assert readiness["periodSeconds"] == 10
    assert readiness["failureThreshold"] == 2

    liveness = container["livenessProbe"]
    assert liveness["httpGet"]["path"] == "/api/health/live"


@requires_helm
def test_nonproduction_data_disabled_keeps_http_readiness() -> None:
    # Worker is fail-closed without data persistence; disable it explicitly so
    # the historical non-production data-disabled app render remains valid.
    result = _helm_template(
        "--set",
        "env.RAG_ENV=development",
        "--set",
        "persistence.data.enabled=false",
        "--set",
        "worker.enabled=false",
    )
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    assert "rag-test-data" not in _pvc_names(docs)
    dep = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"] == "rag-test-app")
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert "volumeMounts" not in container or "data" not in {
        m["name"] for m in container.get("volumeMounts", [])
    }
    readiness = container["readinessProbe"]
    assert readiness["httpGet"]["path"] == "/api/health/ready"
    assert "exec" not in readiness


@requires_helm
def test_backup_snapshot_mounts_data_readonly() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    job = next(d for d in _by_kind(docs, "CronJob") if d["metadata"]["name"] == "rag-test-backup-snapshot")
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    mounts = {m["name"]: m for m in container["volumeMounts"]}
    assert mounts["data"]["mountPath"] == "/app/data"
    assert mounts["data"]["readOnly"] is True
    assert mounts["backups"]["mountPath"] == "/backups"
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert volumes["data"]["persistentVolumeClaim"]["claimName"] == "rag-test-data"
    assert volumes["backups"]["persistentVolumeClaim"]["claimName"] == "rag-test-backups"
    assert "securityContext" in pod
    assert "securityContext" in container


@requires_helm
def test_storage_dependent_cronjobs_present_by_default() -> None:
    result = _helm_template()
    assert result.returncode == 0, result.stderr
    names = _cronjob_names(_docs(result.stdout))
    for expected in (
        "rag-test-backup-snapshot",
        "rag-test-backup-integrity",
        "rag-test-restore-verify",
        "rag-test-curated-staleness",
    ):
        assert expected in names


@requires_helm
def test_disabling_backups_omits_backup_dependent_jobs_only() -> None:
    result = _helm_template("--set", "persistence.backups.enabled=false")
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    names = _cronjob_names(docs)
    assert "rag-test-backup-snapshot" not in names
    assert "rag-test-backup-integrity" not in names
    assert "rag-test-restore-verify" not in names
    # Reports-only job remains.
    assert "rag-test-curated-staleness" in names
    # Unrelated jobs remain (at least one of the non-storage-gated ones).
    assert any(n.startswith("rag-test-") and "backup" not in n and "restore" not in n for n in names)
    pvcs = _pvc_names(docs)
    assert "rag-test-backups" not in pvcs
    assert "rag-test-data" in pvcs
    assert "rag-test-reports" in pvcs


@requires_helm
def test_disabling_reports_omits_reports_dependent_jobs_only() -> None:
    result = _helm_template("--set", "persistence.reports.enabled=false")
    assert result.returncode == 0, result.stderr
    docs = _docs(result.stdout)
    names = _cronjob_names(docs)
    assert "rag-test-backup-integrity" not in names
    assert "rag-test-restore-verify" not in names
    assert "rag-test-curated-staleness" not in names
    # Snapshot only needs data+backups.
    assert "rag-test-backup-snapshot" in names
    pvcs = _pvc_names(docs)
    assert "rag-test-reports" not in pvcs
    assert "rag-test-data" in pvcs
    assert "rag-test-backups" in pvcs


@requires_helm
def test_storage_class_rendered_when_configured() -> None:
    result = _helm_template(
        "--set",
        "persistence.data.storageClass=fast-ssd",
        "--set",
        "persistence.backups.storageClass=fast-ssd",
        "--set",
        "persistence.reports.storageClass=fast-ssd",
    )
    assert result.returncode == 0, result.stderr
    for pvc in _by_kind(_docs(result.stdout), "PersistentVolumeClaim"):
        assert pvc["spec"]["storageClassName"] == "fast-ssd"

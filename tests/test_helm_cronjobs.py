from __future__ import annotations

from pathlib import Path

import yaml

TEMPLATES = Path(__file__).resolve().parent.parent / "deploy" / "helm" / "templates"


def _load_rendered_yaml(path: Path) -> dict:
    """Parse a Helm template after stripping Go template placeholders."""
    raw = path.read_text(encoding="utf-8")
    # Replace `{{ ... }}` placeholders with a harmless literal so PyYAML can parse
    # the structure for schema-level assertions. Keeps Helm semantics intact.
    import re

    stripped = re.sub(r"\{\{[^}]*\}\}", "placeholder", raw)
    return yaml.safe_load(stripped)


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

from __future__ import annotations

import re
from pathlib import Path

DR_PATH = Path(__file__).resolve().parent.parent / "docs" / "disaster-recovery.md"


def test_dr_doc_contains_all_scenarios() -> None:
    content = DR_PATH.read_text(encoding="utf-8")
    for letter in ("A", "B", "C", "D", "E"):
        assert re.search(rf"Scenario {letter}\b", content), f"Scenario {letter} missing"


def test_dr_doc_references_all_batch_j_scripts() -> None:
    content = DR_PATH.read_text(encoding="utf-8")
    for script in (
        "scripts/backup_snapshot.py",
        "scripts/backup_integrity.py",
        "scripts/restore_verify.py",
        "scripts/post_deploy_smoke.py",
        "scripts/chaos_drill.py",
    ):
        assert script in content, f"expected {script} referenced in DR doc"


def test_dr_doc_declares_rto_rpo_table() -> None:
    content = DR_PATH.read_text(encoding="utf-8")
    assert "| Scenario | Description | RPO | RTO" in content
    assert "`DB_ENCRYPTION_KEY` lost" in content
    assert "irrecoverable" in content.lower()

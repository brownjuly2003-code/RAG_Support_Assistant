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
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EXIT_OK = 0
EXIT_RESTORE_FAILED = 1
EXIT_SMOKE_FAILED = 2
EXIT_INFRA_ERROR = 3


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


def _restore_sqlite(snapshot_dir: Path, component: dict[str, Any], target_root: Path) -> StepResult:
    rel = component.get("path")
    if not rel:
        return StepResult("sqlite", passed=False, detail="manifest missing path")
    source = snapshot_dir / rel
    if not source.exists():
        return StepResult("sqlite", passed=False, detail=f"{rel} missing")
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
    snapshot_dir: Path,
    component: dict[str, Any],
    target_root: Path,
    *,
    relative_target: Path,
    label: str,
) -> StepResult:
    rel = component.get("path")
    if not rel:
        return StepResult(label, passed=False, detail="manifest missing path")
    source = snapshot_dir / rel
    if not source.exists():
        return StepResult(label, passed=False, detail=f"{rel} missing")
    extract_to = target_root / relative_target
    extract_to.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(extract_to)
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


def verify_snapshot(
    snapshot_dir: Path,
    *,
    target_root: Path | None = None,
) -> RestoreReport:
    cleanup_target = False
    if target_root is None:
        target_root = Path(tempfile.mkdtemp(prefix="rag-restore-"))
        cleanup_target = True

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
            report.steps.append(_restore_sqlite(snapshot_dir, components["sqlite_traces"], target_root))
        if components.get("uploads", {}).get("status") == "ok":
            report.steps.append(
                _restore_tarball(
                    snapshot_dir,
                    components["uploads"],
                    target_root,
                    relative_target=Path("data"),
                    label="uploads",
                )
            )
        if components.get("chromadb", {}).get("status") == "ok":
            report.steps.append(
                _restore_tarball(
                    snapshot_dir,
                    components["chromadb"],
                    target_root,
                    relative_target=Path("data") / "vectordb",
                    label="chromadb",
                )
            )

        restore_failed = not all(step.passed for step in report.steps)
        if restore_failed:
            report.exit_code = EXIT_RESTORE_FAILED
            return report

        smoke = _run_layout_smoke(target_root, manifest)
        report.steps.append(smoke)
        if not smoke.passed:
            report.exit_code = EXIT_SMOKE_FAILED
            return report

        report.exit_code = EXIT_OK
        return report
    finally:
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
    args = parser.parse_args(argv)

    snapshot_dir = Path(args.snapshot)
    if not snapshot_dir.exists():
        sys.stderr.write(f"snapshot path not found: {snapshot_dir}\n")
        return EXIT_INFRA_ERROR

    report = verify_snapshot(snapshot_dir)
    markdown = render_report(report)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown)

    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

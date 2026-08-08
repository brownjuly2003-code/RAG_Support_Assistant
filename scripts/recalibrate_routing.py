#!/usr/bin/env python3
"""Plan §6.7: reissue routing-calibration artifact from labelled routes.

Default is readiness / dry-run — never silently upgrades synthetic fixtures to
``source=human-labelled``. Operators pass ``--require-human`` + ``--write`` after
a real dual-annotator sample clears readiness floors.

Examples:

  python scripts/recalibrate_routing.py --mode readiness
  python scripts/recalibrate_routing.py --labels path.jsonl --require-human --write \\
      --out evaluation/calibration/routing_calibration.v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LABELS = PROJECT_ROOT / "evaluation" / "calibration" / "labelled_routes.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "evaluation" / "calibration" / "routing_calibration.v1.json"

# Ensure project root imports work when invoked as a script.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.calibration import (  # noqa: E402
    DEFAULT_HUMAN_MIN_DOUBLE_LABELLED,
    DEFAULT_HUMAN_MIN_ITEMS,
    DEFAULT_HUMAN_MIN_KAPPA,
    DEFAULT_HUMAN_MIN_RAW_AGREEMENT,
    SOURCE_HUMAN,
    SOURCE_SYNTHETIC,
    CalibrationArtifactError,
    assess_human_calibration_readiness,
    load_labelled_routes,
    reissue_calibration_from_labels,
    write_calibration_artifact,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reissue routing-calibration artifact from labelled routes (§6.7)."
    )
    p.add_argument(
        "--mode",
        choices=("readiness", "reissue"),
        default="readiness",
        help="readiness = assess only; reissue = build artifact (needs --write to disk)",
    )
    p.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help=f"JSONL labelled routes (default: {DEFAULT_LABELS})",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output calibration artifact path (default: {DEFAULT_OUT})",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="Persist artifact to --out (reissue mode). Without this, print only.",
    )
    p.add_argument(
        "--require-human",
        action="store_true",
        help="Fail-closed unless sample clears human-labelled readiness floors.",
    )
    p.add_argument(
        "--source",
        type=str,
        default=None,
        help=(
            "Artifact source tag. human-labelled only accepted when readiness "
            "passes; default = human-labelled if ready else synthetic-fixture."
        ),
    )
    p.add_argument("--min-items", type=int, default=DEFAULT_HUMAN_MIN_ITEMS)
    p.add_argument(
        "--min-double-labelled",
        type=int,
        default=DEFAULT_HUMAN_MIN_DOUBLE_LABELLED,
    )
    p.add_argument(
        "--min-raw-agreement",
        type=float,
        default=DEFAULT_HUMAN_MIN_RAW_AGREEMENT,
    )
    p.add_argument("--min-kappa", type=float, default=DEFAULT_HUMAN_MIN_KAPPA)
    p.add_argument("--min-quality", type=int, default=None)
    p.add_argument("--min-factuality", type=int, default=None)
    p.add_argument("--min-relevance", type=float, default=None)
    p.add_argument("--self-rag-min-quality", type=int, default=None)
    p.add_argument("--notes", type=str, default=None)
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path (readiness + artifact summary).",
    )
    return p.parse_args(argv)


def _thresholds_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    thr: dict[str, Any] = {}
    if args.min_quality is not None:
        thr["min_quality"] = int(args.min_quality)
    if args.min_factuality is not None:
        thr["min_factuality"] = int(args.min_factuality)
    if args.min_relevance is not None:
        thr["min_relevance"] = float(args.min_relevance)
    if args.self_rag_min_quality is not None:
        thr["self_rag_min_quality"] = int(args.self_rag_min_quality)
    return thr or None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    labels_path = Path(args.labels)
    if not labels_path.is_file():
        print(f"ERROR: labels file not found: {labels_path}", file=sys.stderr)
        return 2

    try:
        items = load_labelled_routes(labels_path)
    except CalibrationArtifactError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    readiness = assess_human_calibration_readiness(
        items,
        min_items=int(args.min_items),
        min_double_labelled=int(args.min_double_labelled),
        min_raw_agreement=float(args.min_raw_agreement),
        min_kappa=float(args.min_kappa),
    )

    report: dict[str, Any] = {
        "kind": "routing-recalibration",
        "created_at": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "labels_path": str(labels_path),
        "require_human": bool(args.require_human),
        "readiness": readiness.as_dict(),
        "write_requested": bool(args.write),
        "artifact_written": False,
        "artifact_path": None,
        "artifact_source": None,
        "verdict": "READY" if readiness.ready else "NOT_READY",
    }

    print("=== routing recalibration (§6.7) ===")
    print(f"labels: {labels_path} (n={readiness.n_items})")
    print(f"human={readiness.n_human} synthetic={readiness.n_synthetic} unknown={readiness.n_unknown}")
    print(
        f"double_labelled={readiness.n_double_labelled} "
        f"raw_agreement={readiness.raw_agreement} kappa={readiness.cohens_kappa}"
    )
    print(f"ready={readiness.ready} verdict={report['verdict']}")
    if readiness.reasons:
        print("reasons:")
        for reason in readiness.reasons:
            print(f"  - {reason}")

    if args.mode == "readiness":
        if args.require_human and not readiness.ready:
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            return 1
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return 0 if readiness.ready or not args.require_human else 1

    # reissue
    try:
        artifact = reissue_calibration_from_labels(
            items,
            thresholds=_thresholds_from_args(args),
            dataset_path=str(labels_path.as_posix()),
            notes=args.notes,
            require_human=bool(args.require_human),
            source=args.source,
            min_items=int(args.min_items),
            min_double_labelled=int(args.min_double_labelled),
            min_raw_agreement=float(args.min_raw_agreement),
            min_kappa=float(args.min_kappa),
        )
    except CalibrationArtifactError as exc:
        print(f"ERROR: reissue refused: {exc}", file=sys.stderr)
        report["verdict"] = "REFUSED"
        report["error"] = str(exc)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return 1

    report["artifact_source"] = artifact.get("source")
    report["thresholds"] = artifact.get("thresholds")
    report["agreement_report"] = artifact.get("agreement_report")
    report["cost_matrix"] = artifact.get("cost_matrix")
    print(f"artifact source={artifact.get('source')}")
    print(f"thresholds={artifact.get('thresholds')}")

    if args.write:
        out_path = write_calibration_artifact(artifact, Path(args.out))
        report["artifact_written"] = True
        report["artifact_path"] = str(out_path)
        print(f"wrote: {out_path}")
    else:
        print("(dry-run: pass --write to persist artifact)")
        print(json.dumps(artifact, ensure_ascii=False, indent=2))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    # Exit 0 on successful reissue even when synthetic (honest source tag).
    # require-human already fail-closed above.
    if artifact.get("source") == SOURCE_HUMAN:
        report["verdict"] = "HUMAN_REISSUED" if args.write else "HUMAN_READY_DRY_RUN"
    elif artifact.get("source") == SOURCE_SYNTHETIC:
        report["verdict"] = "SYNTHETIC_REISSUED" if args.write else "SYNTHETIC_DRY_RUN"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

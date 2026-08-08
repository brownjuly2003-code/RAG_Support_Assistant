"""Plan §6.4 / §6.7: routing calibration artifact + human recalibration gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.calibration import (
    CALIBRATION_ARTIFACT_KIND,
    CALIBRATION_ARTIFACT_SCHEMA_VERSION,
    SOURCE_HUMAN,
    SOURCE_SYNTHETIC,
    CalibrationArtifactError,
    assess_human_calibration_readiness,
    build_calibration_artifact,
    compute_agreement_report,
    compute_cost_matrix,
    default_routing_thresholds,
    label_source_of,
    load_calibration_artifact,
    load_labelled_routes,
    reissue_calibration_from_labels,
    resolve_routing_thresholds,
    thresholds_from_artifact,
    write_calibration_artifact,
)
from agent.graph import make_route_or_retry_node
from agent.grounding import grounding_allows_auto

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_ARTIFACT = (
    PROJECT_ROOT / "evaluation" / "calibration" / "routing_calibration.v1.json"
)
SEED_LABELS = PROJECT_ROOT / "evaluation" / "calibration" / "labelled_routes.jsonl"


def test_seed_calibration_artifact_loads_and_matches_defaults() -> None:
    assert SEED_ARTIFACT.is_file(), "seed calibration artifact must be committed"
    loaded = load_calibration_artifact(SEED_ARTIFACT)
    assert loaded["kind"] == CALIBRATION_ARTIFACT_KIND
    assert loaded["schema_version"] == CALIBRATION_ARTIFACT_SCHEMA_VERSION
    thr = loaded["thresholds"]
    assert thr["min_quality"] == 80
    assert thr["min_factuality"] == 80
    assert thr["min_relevance"] == 0.8
    assert thr["self_rag_min_quality"] == 70
    assert "labeling_rules" in loaded
    assert loaded["labeling_rules"]["version"] == "1"
    assert "agreement_report" in loaded
    assert "cost_matrix" in loaded
    # Bootstrap is honest: not full human production calibration.
    assert loaded["source"] == "bootstrap-defaults"


def test_build_load_write_roundtrip(tmp_path: Path) -> None:
    artifact = build_calibration_artifact(
        thresholds={
            "min_quality": 85,
            "min_factuality": 82,
            "min_relevance": 0.75,
            "self_rag_min_quality": 65,
        },
        source="unit-test",
        notes="roundtrip",
    )
    path = write_calibration_artifact(artifact, tmp_path / "cal.json")
    loaded = load_calibration_artifact(path)
    resolved = thresholds_from_artifact(loaded)
    assert resolved.min_quality == 85
    assert resolved.min_factuality == 82
    assert resolved.min_relevance == pytest.approx(0.75)
    assert resolved.self_rag_min_quality == 65
    assert resolved.source == "artifact"


def test_load_rejects_bad_kind(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"kind": "nope", "schema_version": 1}), encoding="utf-8")
    with pytest.raises(CalibrationArtifactError, match="routing-calibration"):
        load_calibration_artifact(path)


def test_require_calibration_artifact_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(CalibrationArtifactError, match="not found"):
        resolve_routing_thresholds(
            artifact_path=tmp_path / "missing.json",
            require=True,
        )


def test_require_without_path_fail_closed() -> None:
    settings = SimpleNamespace(
        calibration_artifact_path="",
        require_calibration_artifact=True,
        quality_threshold=80,
        min_factuality_for_auto=80,
        min_relevance_for_auto=0.8,
        self_rag_min_quality=70,
    )
    with pytest.raises(CalibrationArtifactError, match="required"):
        resolve_routing_thresholds(settings, require=True)


def test_resolve_prefers_artifact_over_settings(tmp_path: Path) -> None:
    artifact = build_calibration_artifact(
        thresholds={
            "min_quality": 91,
            "min_factuality": 88,
            "min_relevance": 0.9,
            "self_rag_min_quality": 71,
        }
    )
    path = write_calibration_artifact(artifact, tmp_path / "pref.json")
    settings = SimpleNamespace(
        calibration_artifact_path=str(path),
        require_calibration_artifact=False,
        quality_threshold=10,
        min_factuality_for_auto=10,
        min_relevance_for_auto=0.1,
        self_rag_min_quality=10,
    )
    resolved = resolve_routing_thresholds(settings)
    assert resolved.source == "artifact"
    assert resolved.min_quality == 91
    assert resolved.min_factuality == 88
    assert resolved.min_relevance == pytest.approx(0.9)


def test_resolve_falls_back_to_settings_when_artifact_missing(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(
        calibration_artifact_path=str(tmp_path / "gone.json"),
        require_calibration_artifact=False,
        quality_threshold=77,
        min_factuality_for_auto=66,
        min_relevance_for_auto=0.55,
        self_rag_min_quality=55,
    )
    resolved = resolve_routing_thresholds(settings)
    assert resolved.source == "settings"
    assert resolved.min_quality == 77
    assert resolved.min_factuality == 66
    assert resolved.min_relevance == pytest.approx(0.55)


def test_default_thresholds_match_historical_band() -> None:
    thr = default_routing_thresholds()
    assert thr.min_quality == 80
    assert thr.min_factuality == 80
    assert thr.min_relevance == pytest.approx(0.8)
    assert thr.self_rag_min_quality == 70


def test_agreement_and_cost_matrix_from_seed_labels() -> None:
    assert SEED_LABELS.is_file()
    items = load_labelled_routes(SEED_LABELS)
    assert len(items) >= 8
    agreement = compute_agreement_report(items)
    assert agreement["n_double_labelled"] == len(items)
    assert agreement["raw_agreement"] == pytest.approx(0.9)
    assert agreement["cohens_kappa"] == pytest.approx(0.8)
    cost = compute_cost_matrix(items)
    assert cost["auto_when_human"] == 1
    assert cost["human_when_auto"] == 1
    assert cost["auto_when_auto"] == 3
    assert cost["human_when_human"] == 5


def test_route_or_retry_uses_calibrated_min_factuality() -> None:
    """High min_factuality from calibration forces human on borderline scores."""
    node = make_route_or_retry_node(
        min_quality=80,
        min_relevance=0.8,
        min_factuality=95,
    )
    state = {
        "quality_score": 90,
        "relevance_score": 0.9,
        "iteration": 2,
        "max_iterations": 2,
        "knowledge_gap": False,
        "grounding_status": "verified",
        "factuality_score": 90,
        "claims": [
            {"supported": True, "citation_bound": True, "text": "claim one"},
        ],
        "graded_docs": [{"page_content": "doc"}],
        "judge_status": "ok",
        "trace_id": "t-cal",
    }
    # grounding_allows_auto alone would fail at 95 floor
    assert grounding_allows_auto(state, min_factuality=95) is False
    out = node(state)  # type: ignore[arg-type]
    assert out["route"] == "human"


def test_route_or_retry_auto_when_calibrated_floors_met() -> None:
    node = make_route_or_retry_node(
        min_quality=80,
        min_relevance=0.8,
        min_factuality=80,
    )
    state = {
        "quality_score": 90,
        "relevance_score": 0.9,
        "iteration": 0,
        "max_iterations": 2,
        "knowledge_gap": False,
        "grounding_status": "verified",
        "factuality_score": 100,
        "claims": [
            {"supported": True, "citation_bound": True, "text": "claim one"},
        ],
        "graded_docs": [{"page_content": "doc"}],
        "judge_status": "ok",
        "trace_id": "t-cal-auto",
    }
    out = node(state)  # type: ignore[arg-type]
    assert out["route"] == "auto"


def test_seed_artifact_reproducible_via_resolve() -> None:
    resolved = resolve_routing_thresholds(
        artifact_path=SEED_ARTIFACT,
        require=True,
    )
    assert resolved.source == "artifact"
    assert resolved.min_quality == 80
    assert resolved.min_factuality == 80


# ---------------------------------------------------------------------------
# Plan §6.7: human calibration readiness + reissue (no silent upgrade)
# ---------------------------------------------------------------------------


def _human_rows(n: int = 10, *, disagree_one: bool = True) -> list[dict]:
    """Build a minimal dual-annotator human sample that clears default floors."""
    rows: list[dict] = []
    for i in range(n):
        # Mostly auto agreement; one intentional disagreement like the seed.
        if disagree_one and i == 4:
            label_a, label_b, gold = "auto", "human", "human"
            predicted = "auto"
        elif i % 2 == 0:
            label_a = label_b = gold = predicted = "auto"
        else:
            label_a = label_b = gold = predicted = "human"
        rows.append(
            {
                "case_id": f"human-{i:02d}",
                "label_a": label_a,
                "label_b": label_b,
                "gold_route": gold,
                "predicted_route": predicted,
                "label_source": "human",
                "annotator_a": "ann-a",
                "annotator_b": "ann-b",
                "labelled_at": "2026-08-08T12:00:00+00:00",
            }
        )
    return rows


def test_seed_labels_are_synthetic_and_not_human_ready() -> None:
    items = load_labelled_routes(SEED_LABELS)
    assert all(label_source_of(row) == "synthetic" for row in items)
    readiness = assess_human_calibration_readiness(items)
    assert readiness.ready is False
    assert readiness.n_synthetic == len(items)
    assert any("synthetic" in r for r in readiness.reasons)


def test_seed_cannot_reissue_as_human_labelled() -> None:
    items = load_labelled_routes(SEED_LABELS)
    with pytest.raises(CalibrationArtifactError, match="human-labelled|human calibration"):
        reissue_calibration_from_labels(items, require_human=True)
    with pytest.raises(CalibrationArtifactError, match="refusing source=human-labelled"):
        reissue_calibration_from_labels(items, source=SOURCE_HUMAN)


def test_synthetic_reissue_keeps_synthetic_source(tmp_path: Path) -> None:
    items = load_labelled_routes(SEED_LABELS)
    artifact = reissue_calibration_from_labels(
        items,
        dataset_path=str(SEED_LABELS.as_posix()),
        require_human=False,
    )
    assert artifact["source"] == SOURCE_SYNTHETIC
    assert artifact["source"] != SOURCE_HUMAN
    assert artifact["agreement_report"]["n_double_labelled"] == len(items)
    assert artifact["cost_matrix"]["auto_when_human"] == 1
    path = write_calibration_artifact(artifact, tmp_path / "syn.json")
    loaded = load_calibration_artifact(path)
    assert loaded["source"] == SOURCE_SYNTHETIC
    assert loaded["thresholds"]["min_quality"] == 80


def test_human_sample_readiness_and_reissue(tmp_path: Path) -> None:
    items = _human_rows(10)
    readiness = assess_human_calibration_readiness(items)
    assert readiness.ready is True, readiness.reasons
    artifact = reissue_calibration_from_labels(
        items,
        thresholds={"min_quality": 82, "min_factuality": 80, "min_relevance": 0.8},
        require_human=True,
        dataset_path="evaluation/calibration/human_labels.jsonl",
    )
    assert artifact["source"] == SOURCE_HUMAN
    assert artifact["thresholds"]["min_quality"] == 82
    assert artifact["human_readiness"]["ready"] is True
    assert artifact["agreement_report"]["n_double_labelled"] == 10
    path = write_calibration_artifact(artifact, tmp_path / "human.json")
    loaded = load_calibration_artifact(path)
    assert loaded["source"] == SOURCE_HUMAN
    resolved = thresholds_from_artifact(loaded)
    assert resolved.min_quality == 82
    assert resolved.calibration_source == SOURCE_HUMAN


def test_missing_annotators_blocks_human_ready() -> None:
    items = _human_rows(10)
    del items[0]["annotator_a"]
    readiness = assess_human_calibration_readiness(items)
    assert readiness.ready is False
    assert readiness.missing_annotators >= 1


def test_recalibrate_cli_readiness_on_seed() -> None:
    script = PROJECT_ROOT / "scripts" / "recalibrate_routing.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--mode",
            "readiness",
            "--labels",
            str(SEED_LABELS),
            "--require-human",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "ready=False" in proc.stdout or "NOT_READY" in proc.stdout


def test_recalibrate_cli_reissue_human_write(tmp_path: Path) -> None:
    labels = tmp_path / "human.jsonl"
    out = tmp_path / "out.json"
    rows = _human_rows(10)
    labels.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    script = PROJECT_ROOT / "scripts" / "recalibrate_routing.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--mode",
            "reissue",
            "--labels",
            str(labels),
            "--out",
            str(out),
            "--require-human",
            "--write",
            "--min-quality",
            "81",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.is_file()
    loaded = load_calibration_artifact(out)
    assert loaded["source"] == SOURCE_HUMAN
    assert loaded["thresholds"]["min_quality"] == 81

"""Plan §6.4: routing calibration artifact + threshold resolution."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.calibration import (
    CALIBRATION_ARTIFACT_KIND,
    CALIBRATION_ARTIFACT_SCHEMA_VERSION,
    CalibrationArtifactError,
    build_calibration_artifact,
    compute_agreement_report,
    compute_cost_matrix,
    default_routing_thresholds,
    load_calibration_artifact,
    load_labelled_routes,
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

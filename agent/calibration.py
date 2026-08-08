"""Routing threshold calibration artifact (plan §6.4).

Versioned quality/factuality/relevance floors used for ``route=auto`` decisions
must be reproducible from a durable calibration artifact, not only ad-hoc env
defaults. Full human-labelling DoD (live agreement on production traffic)
remains residual; this module provides the artifact contract, agreement/cost
utilities, seed bootstrap, and fail-closed require path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CALIBRATION_ARTIFACT_KIND = "routing-calibration"
CALIBRATION_ARTIFACT_SCHEMA_VERSION = 1

DEFAULT_MIN_QUALITY = 80
DEFAULT_MIN_FACTUALITY = 80
DEFAULT_MIN_RELEVANCE = 0.8
DEFAULT_SELF_RAG_MIN_QUALITY = 70

DEFAULT_LABELING_RULES: dict[str, Any] = {
    "version": "1",
    "auto_allowed_when": [
        "quality_score >= min_quality",
        "relevance_score >= min_relevance",
        "grounding_status == verified",
        "factuality_score >= min_factuality when claims exist",
        "knowledge_gap is false",
        "retrieval context present",
        "judge_status not in unavailable/error/parse_failure",
        "quality_source is measured (llm), not unmeasured/fixed",
    ],
    "human_required_when": [
        "any auto_allowed_when condition fails",
        "unmeasured agentic terminal without evaluate/grounding",
        "PII refuse or prompt-injection refuse path",
        "LLM budget exhaust / node error",
    ],
    "annotator_guidance": (
        "Given question, answer, citations, and retrieval context, label the "
        "desired terminal route as auto or human. Never label auto for "
        "unmeasured quality, missing citations on substantial claims, or "
        "judge outage. Prefer human on ambiguity (cost of false auto is higher)."
    ),
}


class CalibrationArtifactError(ValueError):
    """Raised when a calibration artifact is missing, invalid, or required."""


@dataclass(frozen=True)
class RoutingThresholds:
    """Resolved floors for auto-route quality gates."""

    min_quality: int
    min_factuality: int
    min_relevance: float
    self_rag_min_quality: int
    source: str
    artifact_path: str | None = None
    artifact_kind: str | None = None
    schema_version: int | None = None
    calibration_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_quality": self.min_quality,
            "min_factuality": self.min_factuality,
            "min_relevance": self.min_relevance,
            "self_rag_min_quality": self.self_rag_min_quality,
            "source": self.source,
            "artifact_path": self.artifact_path,
            "calibration_source": self.calibration_source,
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_thresholds_dict() -> dict[str, Any]:
    return {
        "min_quality": DEFAULT_MIN_QUALITY,
        "min_factuality": DEFAULT_MIN_FACTUALITY,
        "min_relevance": DEFAULT_MIN_RELEVANCE,
        "self_rag_min_quality": DEFAULT_SELF_RAG_MIN_QUALITY,
    }


def build_calibration_artifact(
    *,
    thresholds: Mapping[str, Any] | None = None,
    labeling_rules: Mapping[str, Any] | None = None,
    agreement_report: Mapping[str, Any] | None = None,
    cost_matrix: Mapping[str, Any] | None = None,
    model_versions: Mapping[str, Any] | None = None,
    prompt_versions: Mapping[str, Any] | None = None,
    dataset_path: str | None = None,
    source: str = "bootstrap-defaults",
    notes: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a versioned routing-calibration artifact payload."""
    thr = dict(default_thresholds_dict())
    if thresholds:
        thr.update(dict(thresholds))
    thr = _normalize_thresholds(thr)
    stamp = created_at or _utc_now()
    payload: dict[str, Any] = {
        "schema_version": CALIBRATION_ARTIFACT_SCHEMA_VERSION,
        "kind": CALIBRATION_ARTIFACT_KIND,
        "created_at": stamp.isoformat(),
        "source": source,
        "thresholds": thr,
        "labeling_rules": dict(labeling_rules or DEFAULT_LABELING_RULES),
        "agreement_report": dict(
            agreement_report
            or {
                "n_items": 0,
                "n_double_labelled": 0,
                "raw_agreement": None,
                "cohens_kappa": None,
                "annotators": [],
                "notes": "No double-labelled sample yet; bootstrap defaults only.",
            }
        ),
        "cost_matrix": dict(
            cost_matrix
            or {
                "auto_when_auto": 0,
                "human_when_human": 0,
                "auto_when_human": 0,
                "human_when_auto": 0,
                "notes": (
                    "auto_when_human = false auto (high cost); "
                    "human_when_auto = missed auto (caution cost)."
                ),
            }
        ),
        "model_versions": dict(model_versions or {}),
        "prompt_versions": dict(prompt_versions or {}),
        "dataset_path": dataset_path,
    }
    if notes:
        payload["notes"] = notes
    return payload


def write_calibration_artifact(artifact: Mapping[str, Any], path: Path) -> Path:
    """Persist calibration artifact JSON (UTF-8, trailing newline)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(artifact)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def load_calibration_artifact(path: Path) -> dict[str, Any]:
    """Load and validate a calibration artifact."""
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise CalibrationArtifactError(f"calibration artifact not found: {artifact_path}")
    try:
        raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationArtifactError(
            f"calibration artifact unreadable: {artifact_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise CalibrationArtifactError("calibration artifact must be a JSON object")
    kind = raw.get("kind")
    if kind != CALIBRATION_ARTIFACT_KIND:
        raise CalibrationArtifactError(
            f"calibration artifact kind must be {CALIBRATION_ARTIFACT_KIND!r}, got {kind!r}"
        )
    version = int(raw.get("schema_version") or 0)
    if version != CALIBRATION_ARTIFACT_SCHEMA_VERSION:
        raise CalibrationArtifactError(
            f"unsupported calibration artifact schema_version={version}; "
            f"expected {CALIBRATION_ARTIFACT_SCHEMA_VERSION}"
        )
    thr = raw.get("thresholds")
    if not isinstance(thr, dict):
        raise CalibrationArtifactError("calibration artifact must include thresholds object")
    normalized = _normalize_thresholds(thr)
    out = dict(raw)
    out["thresholds"] = normalized
    out["path"] = str(artifact_path)
    return out


def _normalize_thresholds(raw: Mapping[str, Any]) -> dict[str, Any]:
    try:
        min_quality = int(raw.get("min_quality", DEFAULT_MIN_QUALITY))
        min_factuality = int(raw.get("min_factuality", DEFAULT_MIN_FACTUALITY))
        min_relevance = float(raw.get("min_relevance", DEFAULT_MIN_RELEVANCE))
        self_rag_min_quality = int(
            raw.get("self_rag_min_quality", DEFAULT_SELF_RAG_MIN_QUALITY)
        )
    except (TypeError, ValueError) as exc:
        raise CalibrationArtifactError(f"invalid threshold values: {exc}") from exc
    if not (0 <= min_quality <= 100):
        raise CalibrationArtifactError("min_quality must be in 0..100")
    if not (0 <= min_factuality <= 100):
        raise CalibrationArtifactError("min_factuality must be in 0..100")
    if not (0.0 <= min_relevance <= 1.0):
        raise CalibrationArtifactError("min_relevance must be in 0.0..1.0")
    if not (0 <= self_rag_min_quality <= 100):
        raise CalibrationArtifactError("self_rag_min_quality must be in 0..100")
    return {
        "min_quality": min_quality,
        "min_factuality": min_factuality,
        "min_relevance": min_relevance,
        "self_rag_min_quality": self_rag_min_quality,
    }


def _norm_route(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"auto", "human"}:
        return text
    raise CalibrationArtifactError(f"route label must be auto|human, got {value!r}")


def compute_agreement_report(
    items: Sequence[Mapping[str, Any]],
    *,
    annotator_a_key: str = "label_a",
    annotator_b_key: str = "label_b",
) -> dict[str, Any]:
    """Agreement between two annotators on auto/human labels.

    Items missing either label are ignored for double-labelled stats.
    Cohen's kappa is computed for binary auto/human when both labels exist.
    """
    pairs: list[tuple[str, str]] = []
    for item in items:
        if annotator_a_key not in item or annotator_b_key not in item:
            continue
        try:
            a = _norm_route(item[annotator_a_key])
            b = _norm_route(item[annotator_b_key])
        except CalibrationArtifactError:
            continue
        pairs.append((a, b))

    n = len(pairs)
    if n == 0:
        return {
            "n_items": len(items),
            "n_double_labelled": 0,
            "raw_agreement": None,
            "cohens_kappa": None,
            "annotators": [annotator_a_key, annotator_b_key],
        }

    agree = sum(1 for a, b in pairs if a == b)
    raw = agree / n

    # Cohen's kappa for two categories.
    labels = ("auto", "human")
    pa = {lab: sum(1 for a, _ in pairs if a == lab) / n for lab in labels}
    pb = {lab: sum(1 for _, b in pairs if b == lab) / n for lab in labels}
    p_e = sum(pa[lab] * pb[lab] for lab in labels)
    if abs(1.0 - p_e) < 1e-12:
        kappa: float | None = 1.0 if raw == 1.0 else 0.0
    else:
        kappa = (raw - p_e) / (1.0 - p_e)

    return {
        "n_items": len(items),
        "n_double_labelled": n,
        "raw_agreement": round(raw, 6),
        "cohens_kappa": round(float(kappa), 6) if kappa is not None else None,
        "annotators": [annotator_a_key, annotator_b_key],
    }


def compute_cost_matrix(
    items: Sequence[Mapping[str, Any]],
    *,
    predicted_key: str = "predicted_route",
    gold_key: str = "gold_route",
) -> dict[str, Any]:
    """Confusion-style cost matrix of predicted vs gold auto/human routes."""
    counts = {
        "auto_when_auto": 0,
        "human_when_human": 0,
        "auto_when_human": 0,
        "human_when_auto": 0,
        "skipped": 0,
    }
    for item in items:
        if predicted_key not in item or gold_key not in item:
            counts["skipped"] += 1
            continue
        try:
            pred = _norm_route(item[predicted_key])
            gold = _norm_route(item[gold_key])
        except CalibrationArtifactError:
            counts["skipped"] += 1
            continue
        key = f"{pred}_when_{gold}"
        if key in counts:
            counts[key] += 1
        else:
            counts["skipped"] += 1
    counts["notes"] = (
        "auto_when_human = false auto (high cost); "
        "human_when_auto = missed auto (caution cost)."
    )
    return counts


def thresholds_from_artifact(artifact: Mapping[str, Any]) -> RoutingThresholds:
    thr = _normalize_thresholds(artifact.get("thresholds") or {})
    return RoutingThresholds(
        min_quality=int(thr["min_quality"]),
        min_factuality=int(thr["min_factuality"]),
        min_relevance=float(thr["min_relevance"]),
        self_rag_min_quality=int(thr["self_rag_min_quality"]),
        source="artifact",
        artifact_path=str(artifact.get("path") or "") or None,
        artifact_kind=str(artifact.get("kind") or CALIBRATION_ARTIFACT_KIND),
        schema_version=int(artifact.get("schema_version") or CALIBRATION_ARTIFACT_SCHEMA_VERSION),
        calibration_source=str(artifact.get("source") or "") or None,
    )


def default_routing_thresholds(*, source: str = "defaults") -> RoutingThresholds:
    thr = default_thresholds_dict()
    return RoutingThresholds(
        min_quality=int(thr["min_quality"]),
        min_factuality=int(thr["min_factuality"]),
        min_relevance=float(thr["min_relevance"]),
        self_rag_min_quality=int(thr["self_rag_min_quality"]),
        source=source,
    )


def resolve_routing_thresholds(
    settings: Any | None = None,
    *,
    artifact_path: Path | str | None = None,
    require: bool | None = None,
) -> RoutingThresholds:
    """Resolve routing floors from calibration artifact and/or settings.

    Priority:
    1. Explicit ``artifact_path`` (or settings.calibration_artifact_path) when
       the file exists → thresholds from artifact.
    2. If require is set (or settings.require_calibration_artifact) and the
       artifact is missing/unusable → ``CalibrationArtifactError``.
    3. Else settings quality_threshold / min_factuality_for_auto / ... when set.
    4. Else hard defaults matching historical QUALITY_THRESHOLD=80 band.
    """
    path: Path | None = None
    require_flag = bool(require) if require is not None else False

    if artifact_path is not None and str(artifact_path).strip():
        path = Path(artifact_path)
    elif settings is not None:
        configured = getattr(settings, "calibration_artifact_path", None)
        if configured is not None and str(configured).strip():
            path = Path(str(configured))
        if require is None:
            require_flag = bool(getattr(settings, "require_calibration_artifact", False))

    if path is not None:
        try:
            loaded = load_calibration_artifact(path)
            return thresholds_from_artifact(loaded)
        except CalibrationArtifactError:
            if require_flag:
                raise
            # Fall through to settings/defaults when not required.
        except OSError as exc:
            if require_flag:
                raise CalibrationArtifactError(str(exc)) from exc

    if require_flag and path is None:
        raise CalibrationArtifactError(
            "calibration artifact required but no path configured (plan §6.4)"
        )
    if require_flag and path is not None:
        # Path set but load failed — already re-raised above when require_flag.
        # If we got here without path file, still fail.
        if not path.is_file():
            raise CalibrationArtifactError(f"calibration artifact not found: {path}")

    # Settings / hard defaults.
    min_quality = DEFAULT_MIN_QUALITY
    min_factuality = DEFAULT_MIN_FACTUALITY
    min_relevance = DEFAULT_MIN_RELEVANCE
    self_rag_min_quality = DEFAULT_SELF_RAG_MIN_QUALITY
    source = "defaults"

    if settings is not None:
        source = "settings"
        try:
            min_quality = int(getattr(settings, "quality_threshold", min_quality) or min_quality)
        except (TypeError, ValueError):
            pass
        try:
            min_factuality = int(
                getattr(settings, "min_factuality_for_auto", min_factuality) or min_factuality
            )
        except (TypeError, ValueError):
            pass
        try:
            min_relevance = float(
                getattr(settings, "min_relevance_for_auto", min_relevance) or min_relevance
            )
        except (TypeError, ValueError):
            pass
        try:
            self_rag_min_quality = int(
                getattr(settings, "self_rag_min_quality", self_rag_min_quality)
                or self_rag_min_quality
            )
        except (TypeError, ValueError):
            pass

    thr = _normalize_thresholds(
        {
            "min_quality": min_quality,
            "min_factuality": min_factuality,
            "min_relevance": min_relevance,
            "self_rag_min_quality": self_rag_min_quality,
        }
    )
    return RoutingThresholds(
        min_quality=int(thr["min_quality"]),
        min_factuality=int(thr["min_factuality"]),
        min_relevance=float(thr["min_relevance"]),
        self_rag_min_quality=int(thr["self_rag_min_quality"]),
        source=source,
    )


def load_labelled_routes(path: Path) -> list[dict[str, Any]]:
    """Load JSONL dual-annotator / gold route labels for calibration utilities."""
    items: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CalibrationArtifactError(
                f"invalid labelled route JSONL at line {line_no}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise CalibrationArtifactError(
                f"labelled route line {line_no} must be a JSON object"
            )
        items.append(row)
    return items

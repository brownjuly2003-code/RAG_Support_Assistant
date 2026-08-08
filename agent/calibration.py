"""Routing threshold calibration artifact (plan §6.4 / §6.7).

Versioned quality/factuality/relevance floors used for ``route=auto`` decisions
must be reproducible from a durable calibration artifact, not only ad-hoc env
defaults.

§6.4: artifact contract, agreement/cost utilities, seed bootstrap, require path.
§6.7: human-label provenance gate + recalibrate/reissue path. Synthetic fixtures
must never claim ``source=human-labelled``; full production DoD still needs a
real dual-annotator sample that clears readiness floors.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CALIBRATION_ARTIFACT_KIND = "routing-calibration"
CALIBRATION_ARTIFACT_SCHEMA_VERSION = 1

SOURCE_BOOTSTRAP = "bootstrap-defaults"
SOURCE_SYNTHETIC = "synthetic-fixture"
SOURCE_HUMAN = "human-labelled"

LABEL_SOURCE_HUMAN = "human"
LABEL_SOURCE_SYNTHETIC = "synthetic"

DEFAULT_MIN_QUALITY = 80
DEFAULT_MIN_FACTUALITY = 80
DEFAULT_MIN_RELEVANCE = 0.8
DEFAULT_SELF_RAG_MIN_QUALITY = 70

# §6.7 readiness floors for claiming human-labelled calibration DoD (local gate).
# Production operators may raise these via CLI; they must not be silently bypassed.
DEFAULT_HUMAN_MIN_ITEMS = 10
DEFAULT_HUMAN_MIN_DOUBLE_LABELLED = 8
DEFAULT_HUMAN_MIN_RAW_AGREEMENT = 0.8
DEFAULT_HUMAN_MIN_KAPPA = 0.6

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


def label_source_of(item: Mapping[str, Any]) -> str:
    """Return normalized label provenance: human | synthetic | unknown."""
    raw = item.get("label_source")
    if raw is None:
        # Legacy bootstrap rows without provenance → treat as synthetic.
        return LABEL_SOURCE_SYNTHETIC
    text = str(raw).strip().lower()
    if text in {LABEL_SOURCE_HUMAN, LABEL_SOURCE_SYNTHETIC}:
        return text
    return "unknown"


@dataclass(frozen=True)
class HumanCalibrationReadiness:
    """Whether a labelled set may honestly claim human-labelled calibration."""

    ready: bool
    n_items: int
    n_human: int
    n_synthetic: int
    n_unknown: int
    n_double_labelled: int
    raw_agreement: float | None
    cohens_kappa: float | None
    missing_annotators: int
    missing_gold: int
    reasons: tuple[str, ...] = field(default_factory=tuple)
    min_items: int = DEFAULT_HUMAN_MIN_ITEMS
    min_double_labelled: int = DEFAULT_HUMAN_MIN_DOUBLE_LABELLED
    min_raw_agreement: float = DEFAULT_HUMAN_MIN_RAW_AGREEMENT
    min_kappa: float = DEFAULT_HUMAN_MIN_KAPPA

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_human_calibration_readiness(
    items: Sequence[Mapping[str, Any]],
    *,
    min_items: int = DEFAULT_HUMAN_MIN_ITEMS,
    min_double_labelled: int = DEFAULT_HUMAN_MIN_DOUBLE_LABELLED,
    min_raw_agreement: float = DEFAULT_HUMAN_MIN_RAW_AGREEMENT,
    min_kappa: float = DEFAULT_HUMAN_MIN_KAPPA,
    annotator_a_key: str = "label_a",
    annotator_b_key: str = "label_b",
    gold_key: str = "gold_route",
) -> HumanCalibrationReadiness:
    """Fail-closed readiness for ``source=human-labelled`` claims (plan §6.7).

    Synthetic / unknown provenance rows block readiness. Dual-annotator agreement
    and gold labels must clear floors. This is a local DoD gate — not a claim
    that production traffic has been re-labelled.
    """
    reasons: list[str] = []
    n = len(items)
    n_human = 0
    n_synthetic = 0
    n_unknown = 0
    missing_annotators = 0
    missing_gold = 0

    for item in items:
        src = label_source_of(item)
        if src == LABEL_SOURCE_HUMAN:
            n_human += 1
        elif src == LABEL_SOURCE_SYNTHETIC:
            n_synthetic += 1
        else:
            n_unknown += 1

        # Human rows need stable annotator identities (not only label_a/b values).
        if src == LABEL_SOURCE_HUMAN:
            ann_a = str(item.get("annotator_a") or "").strip()
            ann_b = str(item.get("annotator_b") or "").strip()
            if not ann_a or not ann_b:
                missing_annotators += 1
            if gold_key not in item or not str(item.get(gold_key) or "").strip():
                missing_gold += 1

    agreement = compute_agreement_report(
        items,
        annotator_a_key=annotator_a_key,
        annotator_b_key=annotator_b_key,
    )
    n_double = int(agreement.get("n_double_labelled") or 0)
    raw = agreement.get("raw_agreement")
    kappa = agreement.get("cohens_kappa")
    raw_f = float(raw) if raw is not None else None
    kappa_f = float(kappa) if kappa is not None else None

    if n < int(min_items):
        reasons.append(f"n_items={n} < min_items={min_items}")
    if n_synthetic > 0:
        reasons.append(f"synthetic rows present: {n_synthetic}")
    if n_unknown > 0:
        reasons.append(f"unknown label_source rows present: {n_unknown}")
    if n_human != n or n_human == 0:
        reasons.append(f"not all rows are human-labelled (human={n_human}/{n})")
    if missing_annotators > 0:
        reasons.append(f"missing annotator_a/annotator_b on {missing_annotators} human rows")
    if missing_gold > 0:
        reasons.append(f"missing gold_route on {missing_gold} human rows")
    if n_double < int(min_double_labelled):
        reasons.append(
            f"n_double_labelled={n_double} < min_double_labelled={min_double_labelled}"
        )
    if raw_f is None or raw_f < float(min_raw_agreement):
        reasons.append(
            f"raw_agreement={raw_f} < min_raw_agreement={min_raw_agreement}"
        )
    if kappa_f is None or kappa_f < float(min_kappa):
        reasons.append(f"cohens_kappa={kappa_f} < min_kappa={min_kappa}")

    ready = not reasons
    return HumanCalibrationReadiness(
        ready=ready,
        n_items=n,
        n_human=n_human,
        n_synthetic=n_synthetic,
        n_unknown=n_unknown,
        n_double_labelled=n_double,
        raw_agreement=raw_f,
        cohens_kappa=kappa_f,
        missing_annotators=missing_annotators,
        missing_gold=missing_gold,
        reasons=tuple(reasons),
        min_items=int(min_items),
        min_double_labelled=int(min_double_labelled),
        min_raw_agreement=float(min_raw_agreement),
        min_kappa=float(min_kappa),
    )


def reissue_calibration_from_labels(
    items: Sequence[Mapping[str, Any]],
    *,
    thresholds: Mapping[str, Any] | None = None,
    dataset_path: str | None = None,
    model_versions: Mapping[str, Any] | None = None,
    prompt_versions: Mapping[str, Any] | None = None,
    labeling_rules: Mapping[str, Any] | None = None,
    notes: str | None = None,
    require_human: bool = False,
    source: str | None = None,
    min_items: int = DEFAULT_HUMAN_MIN_ITEMS,
    min_double_labelled: int = DEFAULT_HUMAN_MIN_DOUBLE_LABELLED,
    min_raw_agreement: float = DEFAULT_HUMAN_MIN_RAW_AGREEMENT,
    min_kappa: float = DEFAULT_HUMAN_MIN_KAPPA,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Rebuild calibration artifact from labelled routes (plan §6.7).

    Always recomputes agreement_report and cost_matrix from the sample.
    When ``require_human`` is True, fail-closed unless readiness passes and
    force ``source=human-labelled``. Synthetic samples may reissue only as
    ``synthetic-fixture`` / ``bootstrap-defaults`` (never silently upgraded).
    """
    readiness = assess_human_calibration_readiness(
        items,
        min_items=min_items,
        min_double_labelled=min_double_labelled,
        min_raw_agreement=min_raw_agreement,
        min_kappa=min_kappa,
    )
    if require_human and not readiness.ready:
        raise CalibrationArtifactError(
            "human calibration not ready: " + "; ".join(readiness.reasons)
        )

    if source is None:
        source = SOURCE_HUMAN if readiness.ready else SOURCE_SYNTHETIC
    source_norm = str(source).strip().lower()
    if source_norm in {SOURCE_HUMAN, "human", "human_labelled"}:
        source_norm = SOURCE_HUMAN
    if source_norm == SOURCE_HUMAN and not readiness.ready:
        raise CalibrationArtifactError(
            "refusing source=human-labelled: " + "; ".join(readiness.reasons)
        )
    if source_norm not in {
        SOURCE_HUMAN,
        SOURCE_SYNTHETIC,
        SOURCE_BOOTSTRAP,
        "unit-test",
        "defaults",
    } and not source_norm.startswith("operator:"):
        # Allow operator-tagged sources; still block bare human claim above.
        pass

    agreement = compute_agreement_report(items)
    cost = compute_cost_matrix(items)
    # Attach readiness snapshot for audit (not part of schema-critical fields).
    agreement_out = dict(agreement)
    agreement_out["human_readiness"] = {
        "ready": readiness.ready,
        "reasons": list(readiness.reasons),
        "n_human": readiness.n_human,
        "n_synthetic": readiness.n_synthetic,
    }

    default_notes = (
        "Human-labelled calibration artifact (plan §6.7). Thresholds and "
        "agreement/cost recomputed from dual-annotator sample."
        if source_norm == SOURCE_HUMAN
        else (
            "Recalibrated from labelled routes that do not clear human-DoD "
            "readiness (synthetic or incomplete). Not full production calibration."
        )
    )
    artifact = build_calibration_artifact(
        thresholds=thresholds,
        labeling_rules=labeling_rules,
        agreement_report=agreement_out,
        cost_matrix=cost,
        model_versions=model_versions
        or {
            "generator": "settings:ollama_model_name",
            "judge": "settings:judge via provider registry",
            "note": (
                "pin concrete model ids at human re-calibration time"
                if source_norm == SOURCE_HUMAN
                else "bootstrap/synthetic — pin model ids when human re-calibrating"
            ),
        },
        prompt_versions=prompt_versions
        or {
            "evaluate": "agent/prompts.py:evaluate",
            "verify_facts": "agent/prompts.py:verify",
        },
        dataset_path=dataset_path,
        source=source_norm,
        notes=notes if notes is not None else default_notes,
        created_at=created_at,
    )
    artifact["human_readiness"] = readiness.as_dict()
    return artifact


def write_labelled_routes(items: Sequence[Mapping[str, Any]], path: Path) -> Path:
    """Persist labelled routes JSONL (UTF-8, LF, trailing newline)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(row), ensure_ascii=False, sort_keys=True) for row in items]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return target

"""Contract tests for the version-controlled Grafana operations dashboard."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DASHBOARD_PATH = (
    Path(__file__).resolve().parent.parent
    / "monitoring"
    / "grafana"
    / "rag-support-operations.json"
)

EXPECTED_METRICS = (
    "rag_ingestion_queue_oldest_seconds",
    "rag_index_lifecycle_failures_total",
    "rag_auto_responses_total",
    "rag_escalation_delivery_total",
    "rag_safety_blocks_total",
    "rag_orphan_work_inflight",
    "rag_tenant_access_denials_total",
)

COUNTER_GROUP_BY = {
    "rag_index_lifecycle_failures_total": "operation",
    "rag_auto_responses_total": "verification",
    "rag_escalation_delivery_total": "outcome",
    "rag_safety_blocks_total": "action",
    "rag_tenant_access_denials_total": "resource",
}

GAUGE_METRICS = {
    "rag_ingestion_queue_oldest_seconds",
    "rag_orphan_work_inflight",
}

FORBIDDEN_IDENTITY_TOKENS = (
    "tenant_id",
    "ticket_id",
    "session_id",
    "trace_id",
    "job_id",
    "resource_id",
    "payload",
)


def _load_dashboard() -> dict[str, Any]:
    assert DASHBOARD_PATH.is_file(), f"missing dashboard artifact: {DASHBOARD_PATH}"
    raw = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "\r" not in raw, "dashboard JSON must use LF line endings"
    doc = json.loads(raw)
    assert isinstance(doc, dict)
    return doc


def _iter_panels(doc: dict[str, Any]) -> list[dict[str, Any]]:
    panels = doc.get("panels")
    assert isinstance(panels, list), "dashboard must define a top-level panels list"
    out: list[dict[str, Any]] = []
    for panel in panels:
        assert isinstance(panel, dict)
        # Skip pure layout/row placeholders if present.
        if panel.get("type") in {"row", "text"}:
            continue
        out.append(panel)
    return out


def _panel_exprs(panel: dict[str, Any]) -> list[str]:
    exprs: list[str] = []
    for target in panel.get("targets") or []:
        if not isinstance(target, dict):
            continue
        expr = target.get("expr")
        if isinstance(expr, str) and expr.strip():
            exprs.append(expr)
    return exprs


def _all_exprs(panels: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for panel in panels:
        out.extend(_panel_exprs(panel))
    return out


def _find_panel_for_metric(
    panels: list[dict[str, Any]], metric: str
) -> dict[str, Any]:
    matches = [p for p in panels if any(metric in e for e in _panel_exprs(p))]
    assert len(matches) == 1, f"expected exactly one panel for {metric}, got {len(matches)}"
    return matches[0]


def _grid_rect(panel: dict[str, Any]) -> tuple[int, int, int, int]:
    grid = panel.get("gridPos")
    assert isinstance(grid, dict), f"panel {panel.get('id')} missing gridPos"
    for key in ("x", "y", "w", "h"):
        assert key in grid, f"panel {panel.get('id')} gridPos missing {key}"
        assert isinstance(grid[key], int)
        assert grid[key] >= 0
    x, y, w, h = grid["x"], grid["y"], grid["w"], grid["h"]
    assert w > 0 and h > 0
    return x, y, x + w, y + h


def _rects_overlap(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def _datasource_refs(obj: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        if "datasource" in obj:
            found.append(obj["datasource"])
        for value in obj.values():
            found.extend(_datasource_refs(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_datasource_refs(item))
    return found


def _blob(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=True)


def _threshold_steps(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Return absolute threshold steps from panel fieldConfig.defaults."""
    field_config = panel.get("fieldConfig")
    assert isinstance(field_config, dict), f"panel {panel.get('id')} missing fieldConfig"
    defaults = field_config.get("defaults")
    assert isinstance(defaults, dict), f"panel {panel.get('id')} missing fieldConfig.defaults"
    thresholds = defaults.get("thresholds")
    assert isinstance(thresholds, dict), f"panel {panel.get('id')} missing thresholds"
    assert thresholds.get("mode") == "absolute", (
        f"panel {panel.get('id')} thresholds.mode must be absolute"
    )
    steps = thresholds.get("steps")
    assert isinstance(steps, list) and steps, (
        f"panel {panel.get('id')} must define non-empty threshold steps"
    )
    for step in steps:
        assert isinstance(step, dict), f"panel {panel.get('id')} has non-object threshold step"
        assert "color" in step and "value" in step
    return steps


def _first_step_color(steps: list[dict[str, Any]]) -> str:
    color = steps[0].get("color")
    assert isinstance(color, str) and color, "base threshold step must have a color"
    return color


def _first_colored_step(
    steps: list[dict[str, Any]], color: str
) -> dict[str, Any]:
    matches = [
        step
        for step in steps
        if isinstance(step.get("color"), str)
        and step["color"].lower() == color.lower()
        and step.get("value") is not None
    ]
    assert matches, f"no non-base {color!r} threshold step found"
    return matches[0]


def test_dashboard_is_importable_model_with_stable_metadata() -> None:
    doc = _load_dashboard()

    # Importable dashboard model, not an API export envelope.
    assert "dashboard" not in doc or not isinstance(doc.get("dashboard"), dict)
    assert "meta" not in doc
    assert doc.get("uid") == "rag-support-operations"

    title = doc.get("title")
    assert isinstance(title, str) and title.strip()
    description = doc.get("description")
    assert isinstance(description, str) and description.strip()

    tags = doc.get("tags")
    assert isinstance(tags, list)
    tag_set = {str(t).lower() for t in tags}
    assert "operations" in tag_set or "ops" in tag_set
    assert "rag" in tag_set

    assert doc.get("refresh") == "30s"
    time_range = doc.get("time")
    assert isinstance(time_range, dict)
    assert time_range.get("from") == "now-6h"
    assert time_range.get("to") == "now"


def test_prometheus_datasource_is_portable_via_input() -> None:
    doc = _load_dashboard()
    inputs = doc.get("__inputs")
    assert isinstance(inputs, list) and inputs, "missing __inputs for portable import"

    prom_inputs = [
        item
        for item in inputs
        if isinstance(item, dict) and item.get("name") == "DS_PROMETHEUS"
    ]
    assert len(prom_inputs) == 1
    prom_input = prom_inputs[0]
    assert prom_input.get("type") == "datasource"
    assert prom_input.get("pluginId") == "prometheus"

    panels = _iter_panels(doc)
    assert panels, "dashboard must contain data panels"
    for panel in panels:
        refs = _datasource_refs(panel)
        assert refs, f"panel {panel.get('id')} has no datasource reference"
        for ref in refs:
            if isinstance(ref, str):
                assert ref == "${DS_PROMETHEUS}" or ref == "DS_PROMETHEUS"
            elif isinstance(ref, dict):
                uid = ref.get("uid")
                assert uid in {"${DS_PROMETHEUS}", "DS_PROMETHEUS"}
                assert ref.get("type", "prometheus") == "prometheus"
            else:
                raise AssertionError(f"unexpected datasource ref: {ref!r}")


def test_exactly_seven_non_overlapping_panels_cover_all_metrics() -> None:
    doc = _load_dashboard()
    panels = _iter_panels(doc)
    assert len(panels) == 7

    ids = [panel.get("id") for panel in panels]
    assert all(isinstance(i, int) for i in ids)
    assert len(set(ids)) == 7

    rects = [_grid_rect(panel) for panel in panels]
    for i, left in enumerate(rects):
        for right in rects[i + 1 :]:
            assert not _rects_overlap(left, right), "panel grid positions overlap"

    exprs = "\n".join(_all_exprs(panels))
    for metric in EXPECTED_METRICS:
        assert metric in exprs, f"missing metric expression for {metric}"


def test_counter_panels_use_adaptive_range_and_bounded_grouping() -> None:
    doc = _load_dashboard()
    panels = _iter_panels(doc)

    for metric, label in COUNTER_GROUP_BY.items():
        panel = _find_panel_for_metric(panels, metric)
        exprs = _panel_exprs(panel)
        assert exprs, f"{metric} panel has no PromQL"
        joined = "\n".join(exprs)
        assert f"increase({metric}[$__rate_interval])" in joined.replace(" ", "") or (
            f"increase({metric}[$__rate_interval])" in joined
        ) or re.search(
            rf"increase\s*\(\s*{re.escape(metric)}\s*\[\s*\$__rate_interval\s*\]\s*\)",
            joined,
        ), f"{metric} must use increase(...[$__rate_interval])"
        assert re.search(
            rf"\bby\s*\(\s*{re.escape(label)}\s*\)", joined
        ), f"{metric} must aggregate only by ({label})"
        # Reject additional group-by labels.
        for by_match in re.finditer(r"\bby\s*\(([^)]*)\)", joined):
            labels = [part.strip() for part in by_match.group(1).split(",") if part.strip()]
            assert labels == [label], (
                f"{metric} must group only by {label}, found {labels}"
            )


def test_gauge_panels_remain_label_free() -> None:
    doc = _load_dashboard()
    panels = _iter_panels(doc)

    for metric in GAUGE_METRICS:
        panel = _find_panel_for_metric(panels, metric)
        for expr in _panel_exprs(panel):
            assert metric in expr
            # No label selector braces on the gauge metric itself.
            assert not re.search(
                rf"{re.escape(metric)}\s*\{{", expr
            ), f"{metric} must remain label-free, got: {expr}"
            assert "by (" not in expr and "by(" not in expr


def test_queue_orphan_and_unverified_context_encoded() -> None:
    doc = _load_dashboard()
    panels = _iter_panels(doc)
    blob = _blob(doc)

    # Queue age: Base green, yellow warning exactly at 300 seconds.
    queue_panel = _find_panel_for_metric(panels, "rag_ingestion_queue_oldest_seconds")
    queue_blob = json.dumps(queue_panel, ensure_ascii=True)
    unit = str(queue_panel.get("fieldConfig", {})).lower() + str(
        queue_panel.get("options", {})
    ).lower()
    assert "s" in unit or "second" in unit or '"unit": "s"' in queue_blob.lower()
    queue_steps = _threshold_steps(queue_panel)
    assert _first_step_color(queue_steps).lower() == "green"
    assert queue_steps[0].get("value") is None, "queue Base step covers -inf (value null)"
    yellow = _first_colored_step(queue_steps, "yellow")
    assert yellow.get("value") == 300, (
        f"queue yellow warning must start at 300, got {yellow.get('value')!r}"
    )

    # Orphan inflight is an integer gauge: Base green, first red at 1 (not 0).
    # Grafana activates a step at value met-or-exceeded; red@0 paints healthy zero red.
    orphan_panel = _find_panel_for_metric(panels, "rag_orphan_work_inflight")
    orphan_steps = _threshold_steps(orphan_panel)
    assert _first_step_color(orphan_steps).lower() == "green"
    assert orphan_steps[0].get("value") is None, "orphan Base step covers -inf (value null)"
    orphan_red = _first_colored_step(orphan_steps, "red")
    assert orphan_red.get("value") == 1, (
        f"orphan first red step must start at 1 (zero stays green), "
        f"got {orphan_red.get('value')!r}"
    )

    # Auto-response increase(...) can be fractional: Base green, red > 0 (never 0).
    # Unverified series keep an explicit fixed-red override; description says Zero target.
    auto_panel = _find_panel_for_metric(panels, "rag_auto_responses_total")
    auto_desc = str(auto_panel.get("description") or "")
    assert "Zero target" in auto_desc, (
        "auto-response panel description must retain the phrase 'Zero target'"
    )
    auto_steps = _threshold_steps(auto_panel)
    assert _first_step_color(auto_steps).lower() == "green"
    assert auto_steps[0].get("value") is None, "auto Base step covers -inf (value null)"
    auto_red = _first_colored_step(auto_steps, "red")
    red_value = auto_red.get("value")
    assert isinstance(red_value, (int, float)) and not isinstance(red_value, bool), (
        f"auto red threshold must be numeric, got {red_value!r}"
    )
    assert red_value > 0, (
        f"auto red threshold must be strictly greater than zero "
        f"(increase can be fractional; red@0 paints healthy zero red), got {red_value!r}"
    )

    overrides = (auto_panel.get("fieldConfig") or {}).get("overrides") or []
    assert isinstance(overrides, list) and overrides, (
        "auto-response panel must define field overrides for unverified series"
    )
    unverified_fixed_red = False
    for override in overrides:
        if not isinstance(override, dict):
            continue
        matcher = override.get("matcher") or {}
        if not isinstance(matcher, dict) or matcher.get("id") != "byRegexp":
            continue
        options = str(matcher.get("options") or "")
        if "unverified" not in options.lower():
            continue
        for prop in override.get("properties") or []:
            if not isinstance(prop, dict) or prop.get("id") != "color":
                continue
            value = prop.get("value")
            if not isinstance(value, dict):
                continue
            if (
                value.get("mode") == "fixed"
                and str(value.get("fixedColor", "")).lower() == "red"
            ):
                unverified_fixed_red = True
    assert unverified_fixed_red, (
        "auto-response panel must keep a byRegexp override that fixes unverified color to red"
    )

    # Threshold / context evidence should also be present at dashboard scope.
    assert "300" in blob
    assert "unverified" in blob.lower()


def test_no_high_cardinality_identity_selectors_or_grafana_alerts() -> None:
    doc = _load_dashboard()
    blob = _blob(doc).lower()

    for token in FORBIDDEN_IDENTITY_TOKENS:
        assert token not in blob, f"forbidden identity token present: {token}"

    # Free-form reason selectors/variables are forbidden; bounded metric labels
    # for other signals are allowed only through their declared group-by.
    assert "reason=" not in blob
    assert re.search(r"\breason\b", blob) is None or "reason" not in [
        str(v.get("name", "")).lower()
        for v in (doc.get("templating", {}) or {}).get("list", [])
        if isinstance(v, dict)
    ]

    # No Grafana-native alert rules on the dashboard; Prometheus owns alerts.
    assert "alert" not in doc
    for panel in _iter_panels(doc):
        assert "alert" not in panel

    # No placeholders / deployment-specific live wiring.
    for forbidden in ("todo", "placeholder", "http://", "https://", "changeme"):
        assert forbidden not in blob

"""Validate monitoring/alert_rules.yml structure and metric references."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)


ALERT_RULES_FILE = Path(__file__).resolve().parent.parent / "monitoring" / "alert_rules.yml"


@pytest.fixture(scope="module")
def rules_doc() -> dict:
    assert ALERT_RULES_FILE.exists(), f"missing {ALERT_RULES_FILE}"
    with ALERT_RULES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_yaml_is_valid_and_has_groups(rules_doc: dict) -> None:
    assert "groups" in rules_doc
    assert isinstance(rules_doc["groups"], list)
    assert len(rules_doc["groups"]) >= 3


def test_every_alert_has_required_fields(rules_doc: dict) -> None:
    for group in rules_doc["groups"]:
        assert "name" in group
        assert "rules" in group
        for rule in group["rules"]:
            if "alert" not in rule:
                continue
            assert "expr" in rule, f"{rule['alert']} missing expr"
            assert "for" in rule, f"{rule['alert']} missing for"
            assert "labels" in rule, f"{rule['alert']} missing labels"
            assert "severity" in rule["labels"], f"{rule['alert']} missing severity"
            assert rule["labels"]["severity"] in ("info", "warning", "critical")
            assert "annotations" in rule, f"{rule['alert']} missing annotations"
            assert "summary" in rule["annotations"], f"{rule['alert']} missing summary"


def test_expressions_reference_declared_metrics(rules_doc: dict) -> None:
    """Each rag_* metric in expr must be declared in monitoring/prometheus.py."""
    prom_file = ALERT_RULES_FILE.parent / "prometheus.py"
    prom_source = prom_file.read_text(encoding="utf-8")

    declared = set(re.findall(r'"(rag_[a-z_]+)"', prom_source))
    suffix_variants = {"", "_bucket", "_sum", "_count", "_total"}

    referenced = set(re.findall(r"\brag_[a-z_]+\b", _flatten_exprs(rules_doc)))

    missing: list[str] = []
    for name in referenced:
        found = False
        for suf in sorted(suffix_variants, key=len, reverse=True):
            if suf and name.endswith(suf):
                base = name[: -len(suf)]
                if base in declared or name in declared:
                    found = True
                    break
        if not found and name not in declared:
            if name not in declared:
                missing.append(name)

    assert not missing, f"Undeclared metrics in alert_rules.yml: {missing}"


def test_for_durations_are_reasonable(rules_doc: dict) -> None:
    """`for: 0s` or missing -> false positives; `for: >1h` -> alert fatigue."""
    for group in rules_doc["groups"]:
        for rule in group["rules"]:
            if "alert" not in rule:
                continue
            dur = rule.get("for", "0s")
            assert dur.endswith(("s", "m", "h"))
            num = int(dur[:-1])
            unit = dur[-1]
            sec = {"s": 1, "m": 60, "h": 3600}[unit]
            total_sec = num * sec
            assert 30 <= total_sec <= 7200, (
                f"{rule['alert']} has unreasonable for={dur}"
            )


def _flatten_exprs(rules_doc: dict) -> str:
    """Concat all `expr:` strings for regex scanning."""
    out: list[str] = []
    for group in rules_doc["groups"]:
        for rule in group["rules"]:
            expr = rule.get("expr", "")
            if isinstance(expr, str):
                out.append(expr)
    return "\n".join(out)

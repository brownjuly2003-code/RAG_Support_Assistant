#!/usr/bin/env python3
"""Phase 0 (adaptive-retrieval) labeling — T0.1.

Encodes the manual ``query_class`` / ``needs_factcard`` annotation for every
curated eval case and emits ``phase0_labels.jsonl`` plus the class/flag
proportions used by the Phase-0 gate.

Taxonomy
--------
``query_class`` (one of four):
  * ``simple``         — yes/no or single short answer ("Можно ли…", "Нужно ли…",
                          off-topic refusals).
  * ``factual``        — single specific value lookup (a number, date, period,
                          single party): "Какой срок…", "Сколько…", "Кто согласует…".
  * ``enumeration``    — answer is a list (fields / docs / data / evidence /
                          parameters / conditions / steps / causes / actions).
  * ``multi-condition``— conditional / procedural reasoning, escalation logic,
                          checklists ("Когда…", "В каких случаях…", "Что проверить…").

``needs_factcard`` (bool): TRUE only when the answer is an enumerable list of the
fact-card schema types (fields / required documents / required data / evidence /
parameters / required contents / escalation-events-conditions). Enumerations of
STEPS / CAUSES / ACTIONS / exclusions are ``enumeration`` class but
``needs_factcard=False`` (the card schema does not store procedures).

The labels are authored by hand (judgment over each query) and pinned here so the
result is reproducible and auditable; this script only validates them against the
eval files and prints proportions.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evaluation"
OUT = Path(__file__).resolve().parent / "phase0_labels.jsonl"

# case_id -> (query_class, needs_factcard)
LABELS: dict[str, tuple[str, bool]] = {
    # ---- aircargo (tenant=aircargo) ----
    "aircargo-probation-data": ("enumeration", True),
    "aircargo-probation-extend": ("simple", False),
    "aircargo-probation-dismissal": ("multi-condition", False),
    "aircargo-dismissal-check": ("multi-condition", False),
    "aircargo-dismissal-lawyer": ("multi-condition", False),
    "aircargo-dismissal-order": ("simple", False),
    "aircargo-leave-sources": ("multi-condition", False),
    "aircargo-leave-compensation": ("simple", False),
    "aircargo-leave-risk": ("multi-condition", False),
    "aircargo-matliab-check": ("multi-condition", False),
    "aircargo-matliab-disputed": ("multi-condition", False),
    "aircargo-templates-choose": ("multi-condition", False),
    "aircargo-templates-checklist": ("multi-condition", False),
    "aircargo-templates-insufficient": ("multi-condition", False),
    "aircargo-secret-check": ("multi-condition", False),
    "aircargo-secret-not-auto": ("multi-condition", False),
    "aircargo-secret-disclosure": ("multi-condition", False),
    "aircargo-pdp-scope": ("multi-condition", False),
    "aircargo-pdp-data": ("enumeration", True),
    "aircargo-pdp-uncertain": ("multi-condition", False),
    "aircargo-claims-delay": ("enumeration", True),
    "aircargo-claims-damage": ("enumeration", True),
    "aircargo-claims-lawyer": ("multi-condition", False),
    "aircargo-claims-forbidden": ("multi-condition", False),
    "aircargo-expedition-vs-carrier": ("factual", False),
    "aircargo-expedition-mawb-hawb": ("enumeration", True),
    "aircargo-expedition-risks": ("multi-condition", False),
    "aircargo-road-cutoff": ("multi-condition", False),
    "aircargo-road-penalty": ("simple", False),
    "aircargo-road-seal": ("enumeration", True),
    "aircargo-road-driver-pdn": ("multi-condition", False),
    "aircargo-business-trip-advance-report": ("enumeration", True),
    "aircargo-business-trip-foreign-approval": ("factual", False),
    "aircargo-remote-work-monitoring-limits": ("multi-condition", False),
    "aircargo-remote-work-equipment-compensation": ("factual", False),
    "aircargo-maternity-duration-normal": ("factual", False),
    "aircargo-maternity-dismissal-ban": ("simple", False),
    "aircargo-internal-transfer-consent": ("multi-condition", False),
    "aircargo-internal-transfer-documents": ("enumeration", True),
    "aircargo-contract-termination-open-awb": ("multi-condition", False),
    "aircargo-contract-termination-fields": ("enumeration", True),
    "aircargo-road-contract-aircargo-fields": ("enumeration", True),
    "aircargo-dangerous-goods-fields": ("enumeration", True),
    "aircargo-dangerous-goods-clearance": ("multi-condition", False),
    "aircargo-customs-clearance-fields": ("enumeration", True),
    "aircargo-customs-special-cargo-manual-check": ("multi-condition", False),
    "aircargo-waybill-first-mile-fields": ("enumeration", True),
    "aircargo-waybill-escalation-events": ("enumeration", True),
    "aircargo-trade-compliance-hold": ("multi-condition", False),
    "aircargo-trade-compliance-screening": ("enumeration", True),
    "aircargo-incident-response-bridge": ("multi-condition", False),
    "aircargo-incident-response-required-fields": ("enumeration", True),
    "aircargo-access-control-need-to-know": ("factual", False),
    "aircargo-access-control-review": ("enumeration", True),
    "aircargo-employment-contract-essential-terms": ("enumeration", True),
    "aircargo-employment-contract-special-form": ("multi-condition", False),
    "aircargo-driver-job-documents": ("enumeration", True),
    "aircargo-driver-dangerous-goods-refusal": ("simple", False),
    "aircargo-sick-leave-required-fields": ("enumeration", True),
    "aircargo-sick-leave-lawyer-escalation": ("multi-condition", False),
    "aircargo-cargo-loss-evidence-bundle": ("enumeration", True),
    "aircargo-cargo-loss-required-fields": ("enumeration", True),
    "aircargo-late-delivery-reply-evidence": ("enumeration", True),
    "aircargo-late-delivery-reply-no-admission": ("multi-condition", False),
    "aircargo-driver-hours-required-fields": ("enumeration", True),
    "aircargo-driver-hours-terminal-discrepancy": ("multi-condition", False),
    "aircargo-warehouse-3pl-required-fields": ("enumeration", True),
    "aircargo-warehouse-3pl-escalation": ("multi-condition", False),
    "aircargo-perishable-temperature-controls": ("enumeration", True),
    "aircargo-perishable-special-cargo-evidence": ("enumeration", True),
    "aircargo-oversized-permit-route": ("enumeration", True),
    "aircargo-oversized-manual-check": ("multi-condition", False),
    "aircargo-data-retention-legal-hold": ("multi-condition", False),
    "aircargo-data-retention-required-fields": ("enumeration", True),
    "aircargo-subject-rights-third-party-masking": ("multi-condition", False),
    "aircargo-subject-rights-required-fields": ("enumeration", True),
    "aircargo-customs-broker-evidence": ("enumeration", True),
    "aircargo-customs-broker-escalation": ("enumeration", True),
    "aircargo-salary-payment-dates": ("factual", False),
    "aircargo-salary-bonus-conditions": ("multi-condition", False),
    "aircargo-overtime-limits": ("factual", False),
    "aircargo-overtime-protected-categories": ("enumeration", True),
    "aircargo-harassment-complaint-data": ("enumeration", True),
    "aircargo-harassment-investigation-timeline": ("factual", False),
    "aircargo-conflict-interest-disclosure": ("enumeration", True),
    "aircargo-conflict-interest-sanctions": ("multi-condition", False),
    "aircargo-cargo-insurance-evidence": ("enumeration", True),
    "aircargo-cargo-insurance-operational-limits": ("multi-condition", False),
    "aircargo-fuel-supply-evidence": ("enumeration", True),
    "aircargo-fuel-supply-required-fields": ("enumeration", True),
    "aircargo-gps-monitoring-required-fields": ("enumeration", True),
    "aircargo-gps-monitoring-scope": ("factual", False),
    "aircargo-weight-control-required-fields": ("enumeration", True),
    "aircargo-weight-control-discrepancy": ("multi-condition", False),
    "aircargo-cross-border-required-fields": ("enumeration", True),
    "aircargo-cross-border-special-cargo": ("enumeration", True),
    "aircargo-breach-notification-required-fields": ("enumeration", True),
    "aircargo-breach-notification-participants": ("multi-condition", False),
    "aircargo-cross-border-pdn-required-fields": ("enumeration", True),
    "aircargo-cross-border-pdn-no-transfer": ("multi-condition", False),
    # ---- curated (tenant=default) ----
    "warranty-period": ("factual", False),
    "warranty-excluded": ("enumeration", False),  # list of exclusions, not card schema
    "warranty-how-to-claim": ("enumeration", False),  # steps
    "warranty-receipt-storage": ("factual", False),
    "warranty-no-receipt-where": ("simple", False),
    "returns-window": ("factual", False),
    "returns-refund-timeline": ("factual", False),
    "returns-no-receipt": ("simple", False),
    "returns-different-card": ("simple", False),
    "returns-no-packaging": ("simple", False),
    "error-e10": ("multi-condition", False),
    "error-e20": ("enumeration", False),  # causes
    "error-e25": ("simple", False),
    "error-e30": ("simple", False),
    "error-e20-clog-vs-pump": ("multi-condition", False),
    "error-e25-reset-steps": ("enumeration", False),  # steps
    "error-e30-actions": ("enumeration", False),  # actions
    "off-topic-wifi": ("simple", False),
    "off-topic-price": ("simple", False),
    "off-topic-delivery": ("simple", False),
    "warranty-start-date": ("factual", False),
    "warranty-use-instruction": ("simple", False),
    "warranty-opened-case": ("simple", False),
    "warranty-liquid-damage": ("simple", False),
    "warranty-service-documents": ("enumeration", True),  # which docs to prepare
    "returns-required-documents": ("enumeration", True),  # required documents
    "returns-item-used": ("simple", False),
    "returns-same-account": ("factual", False),
    "returns-after-acceptance": ("factual", False),
    "returns-window-from-purchase": ("factual", False),
    "error-e10-water-pressure": ("multi-condition", False),
    "error-e20-hose-kink": ("simple", False),
    "error-e20-filter-or-pump": ("enumeration", False),  # which units to check (diagnostic)
    "error-e25-factory-reset": ("multi-condition", False),
    "error-e30-service-center": ("factual", False),
}

CLASSES = ("simple", "factual", "enumeration", "multi-condition")
SOURCES = (
    ("curated_cases_aircargo.jsonl", "aircargo"),
    ("curated_cases.jsonl", "curated"),
)


def load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fn, src in SOURCES:
        for raw in (EVAL / fn).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            d = json.loads(line)
            cid = d["case_id"]
            if cid not in LABELS:
                raise SystemExit(f"UNLABELED case: {cid} ({fn})")
            qc, fc = LABELS[cid]
            rows.append(
                {
                    "case_id": cid,
                    "source": src,
                    "tenant_id": d.get("tenant_id", "default"),
                    "query": d["query"],
                    "query_class": qc,
                    "needs_factcard": fc,
                }
            )
    ids = {str(r["case_id"]) for r in rows}
    extra = set(LABELS) - ids
    if extra:
        raise SystemExit(f"LABELS references unknown case_ids: {sorted(extra)}")
    return rows


def print_stats(rows: list[dict[str, object]], label: str) -> None:
    n = len(rows)
    cc = Counter(r["query_class"] for r in rows)
    fc = sum(bool(r["needs_factcard"]) for r in rows)
    print(f"\n== {label} (n={n}) ==")
    for k in CLASSES:
        c = cc.get(k, 0)
        print(f"  {k:<16} {c:>3}  ({100 * c / n:.0f}%)")
    print(f"  needs_factcard   {fc:>3}  ({100 * fc / n:.0f}%)")


def main() -> int:
    rows = load_rows()
    print_stats(rows, "ALL")
    print_stats([r for r in rows if r["source"] == "aircargo"], "aircargo")
    print_stats([r for r in rows if r["source"] == "curated"], "curated")
    with OUT.open("w", encoding="utf-8", newline="\n") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 5 (adaptive-retrieval, Track F): offline delta D2 vs D2+factcard.

Closes the plan's ship-gate (docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md
T5.1). Reuses the validated A/B scorer ``_kw_status`` from
``scripts/ab_remote_contextual.py`` (answer_contains keyword coverage in the
retrieved top-k → FULL/PART/MISS) so the factcard arm is measured on the exact
same yardstick as the D2 production baseline.

Inputs (all already produced by the existing harness / scripts):
  --d2      ab_candidates_phase2_D2.json  (per-case D2 post-rerank+parent-expand
            candidates; produce via:  pools C → rerank C → expand --label D2)
  --cases   evaluation/curated_cases_aircargo.jsonl  (query + expected.answer_contains)
  --labels  evaluation/adaptive_retrieval/phase0_labels.jsonl  (gold needs_factcard)
  factcard collection  <prefix>_<tenant>_factcards  (build with scripts/build_factcards.py
            --docs-dir data/uploads/aircargo --tenant aircargo)

The composite arm routes a case to the factcard lane iff its GOLD needs_factcard
label is true (else it stays on D2) — this is the CEILING of auto-routing (perfect
classifier). With gold routing, non-needs cases are D2 by construction, so the
composite can only regress where factcard < D2 on a needs_factcard case. Hence
SHIP-iff: composite FULL ≥ D2 FULL on the needs subset AND the residual MISS
closes AND no net-negative FULL downgrade. Real-classifier impact (R1 needs_factcard
CV F1 ≈ 0.871) is a separate, documented discount on top of this ceiling.

Heavy step: factcard retrieval embeds the query with BGE-M3 → run on Mac (MPS).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ab_remote_contextual import _kw_status  # noqa: E402

RESIDUAL_MISS = "aircargo-customs-clearance-fields"


def _load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _counts(statuses: list[str]) -> dict[str, int]:
    out = {"FULL": 0, "PART": 0, "MISS": 0}
    for s in statuses:
        out[s] += 1
    return out


def _fmt(c: dict[str, int]) -> str:
    n = c["FULL"] + c["PART"] + c["MISS"]
    pct = 100 * c["FULL"] / max(n, 1)
    return f"FULL {c['FULL']}/{n} ({pct:.0f}%) · PART {c['PART']} · MISS {c['MISS']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d2", default=str(PROJECT_ROOT / ".tmp" / "ab_candidates_phase2_D2.json"))
    parser.add_argument(
        "--cases", default=str(PROJECT_ROOT / "evaluation" / "curated_cases_aircargo.jsonl")
    )
    parser.add_argument(
        "--labels",
        default=str(PROJECT_ROOT / "evaluation" / "adaptive_retrieval" / "phase0_labels.jsonl"),
    )
    parser.add_argument("--tenant", default="aircargo")
    parser.add_argument("--k", type=int, default=3, help="factcard top-k")
    parser.add_argument("--out", default=str(PROJECT_ROOT / ".tmp" / "phase5_factcard_delta.md"))
    args = parser.parse_args(argv)

    from vectordb.manager import get_factcard_documents

    d2_rows = json.loads(Path(args.d2).read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in _load_jsonl(Path(args.cases))}
    needs = {r["case_id"]: bool(r.get("needs_factcard")) for r in _load_jsonl(Path(args.labels))}

    lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line, flush=True)
        lines.append(line)

    # Per-case: D2 status (recomputed from candidates with the canonical scorer),
    # factcard status, gold needs_factcard.
    per_case: list[dict] = []
    missing_label = 0
    for row in d2_rows:
        cid = row["case_id"]
        kws = row["kws"]
        rerank_k = int(row.get("rerank_k", 5))
        d2_status = _kw_status(kws, row["cands"][:rerank_k])

        case = cases.get(cid)
        query = case["query"] if case else row.get("query", "")
        fc_docs = get_factcard_documents(query, tenant_id=args.tenant, k=args.k)
        fc_texts = [getattr(d, "page_content", "") for d in fc_docs]
        fc_status = _kw_status(kws, fc_texts)

        if cid not in needs:
            missing_label += 1
        nf = needs.get(cid, False)
        per_case.append(
            {"case_id": cid, "needs_factcard": nf, "d2": d2_status, "factcard": fc_status}
        )

    n = len(per_case)
    needs_rows = [p for p in per_case if p["needs_factcard"]]
    nn_rows = [p for p in per_case if not p["needs_factcard"]]

    emit("# Phase 5 — offline delta: D2 vs D2+factcard (gold-routing ceiling)")
    emit()
    emit(f"- cases scored: **{n}** · needs_factcard (gold): **{len(needs_rows)}** · "
         f"non-needs: {len(nn_rows)} · factcard top-k={args.k} · tenant={args.tenant}")
    if missing_label:
        emit(f"- ⚠ {missing_label} case(s) had no phase0 label → treated as non-needs")
    emit()

    # Sanity: overall D2 should reproduce the documented baseline.
    d2_all = _counts([p["d2"] for p in per_case])
    emit(f"**D2 baseline (all):** {_fmt(d2_all)}  ← sanity vs documented FULL 96/PART 3/MISS 1")
    emit()

    # Composite: route gold-needs → factcard, else D2.
    composite = [(p["factcard"] if p["needs_factcard"] else p["d2"]) for p in per_case]
    comp_all = _counts(composite)
    emit(f"**Composite D2+factcard (gold routing, all):** {_fmt(comp_all)}")
    emit(f"**Δ FULL (composite − D2), all:** {comp_all['FULL'] - d2_all['FULL']:+d}")
    emit()

    # The decisive subset: needs_factcard.
    d2_needs = _counts([p["d2"] for p in needs_rows])
    fc_needs = _counts([p["factcard"] for p in needs_rows])
    emit("## needs_factcard subset (the only place composite differs from D2)")
    emit()
    emit(f"- D2 on needs:       {_fmt(d2_needs)}")
    emit(f"- factcard on needs: {_fmt(fc_needs)}")
    emit(f"- **Δ FULL on needs (factcard − D2): {fc_needs['FULL'] - d2_needs['FULL']:+d}**")
    emit()

    # Transition matrix on needs subset (where the gain/regression lives).
    trans: dict[tuple[str, str], list[str]] = {}
    for p in needs_rows:
        trans.setdefault((p["d2"], p["factcard"]), []).append(p["case_id"])
    emit("### transitions on needs_factcard (D2 → factcard)")
    emit()
    improved = sum(len(v) for (a, b), v in trans.items() if _rank(b) > _rank(a))
    regressed_ids = [i for (a, b), v in trans.items() if _rank(b) < _rank(a) for i in v]
    for (a, b), ids in sorted(trans.items()):
        tag = "" if a == b else (" ⬆" if _rank(b) > _rank(a) else " ⬇ REGRESS")
        shown = ", ".join(i.removeprefix("aircargo-") for i in ids) if a != b else f"{len(ids)} cases"
        emit(f"- {a} → {b}{tag}: {shown}")
    emit()
    emit(f"- improved: **{improved}** · regressed: **{len(regressed_ids)}**"
         + (f" ({', '.join(i.removeprefix('aircargo-') for i in regressed_ids)})" if regressed_ids else ""))
    emit()

    # Residual MISS focus.
    rm = next((p for p in per_case if p["case_id"] == RESIDUAL_MISS), None)
    if rm:
        closed = rm["factcard"] == "FULL" and rm["d2"] != "FULL"
        emit(f"## residual MISS `{RESIDUAL_MISS}`: D2={rm['d2']} → factcard={rm['factcard']}"
             + ("  ✅ CLOSED by factcard" if closed else ""))
        emit()

    # Misrouting illustration: route EVERYTHING to factcard (no router).
    fc_all = _counts([p["factcard"] for p in per_case])
    emit(f"**All-factcard (no router, illustrates misrouting cost):** {_fmt(fc_all)}  "
         f"(Δ FULL vs D2: {fc_all['FULL'] - d2_all['FULL']:+d})")
    emit()

    # Decision.
    delta_needs = fc_needs["FULL"] - d2_needs["FULL"]
    miss_closed = bool(rm and rm["factcard"] == "FULL" and rm["d2"] != "FULL")
    ship = delta_needs > 0 and len(regressed_ids) == 0
    borderline = delta_needs == 0 and miss_closed and len(regressed_ids) == 0
    emit("## Decision (gold-routing ceiling)")
    emit()
    if ship:
        verdict = "SHIP-eligible (ceiling positive; discount by R1 needs_factcard F1≈0.871 before default flip)"
    elif borderline:
        verdict = "BORDERLINE (no net FULL gain but MISS closes, no regressions) — judgement call"
    else:
        verdict = "NO-SHIP (ceiling shows no net gain or has regressions — auto-routing not justified)"
    emit(f"- ΔFULL(needs)={delta_needs:+d} · regressions={len(regressed_ids)} · "
         f"residual-MISS-closed={miss_closed}")
    emit(f"- **VERDICT: {verdict}**")
    emit()

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[phase5] saved -> {args.out}", flush=True)
    return 0


def _rank(status: str) -> int:
    return {"MISS": 0, "PART": 1, "FULL": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())

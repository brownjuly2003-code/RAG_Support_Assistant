"""Pure-logic tests for scripts/ab_context_precision.py (no models, no network).

Exercises the offline knob-sweep core: candidate slicing, the reused RAGAS
context_precision / context_recall + FULL/PART/MISS aggregation, the SHIP
verdict boundaries, grid construction and markdown rendering. The heavy
embed+rerank and the external-mistral grade/judge layers are NOT touched here.
"""
from __future__ import annotations

import scripts.ab_context_precision as ab


def _arm(name="t", k=5, window=0, max_chars=0, grade=False):
    return ab.Arm(name=name, rerank_k=k, window=window, max_chars=max_chars, grade=grade)


def test_mock_rows_shape():
    rows = ab.mock_rows()
    assert len(rows) == 3
    for row in rows:
        assert {"case_id", "query", "kws", "cands", "cand_sources"} <= set(row)
        assert len(row["cands"]) == len(row["cand_sources"])


def test_final_texts_slices_to_rerank_k():
    exp = ab.NullExpander()
    row = ab.mock_rows()[0]  # 4 candidates
    assert len(ab.final_texts_for_case(row, _arm(k=2), exp, None)) == 2
    assert len(ab.final_texts_for_case(row, _arm(k=10), exp, None)) == 4


def test_evaluate_arm_aggregate_ranges_and_counts():
    rows = ab.mock_rows()
    res = ab.evaluate_arm(rows, _arm(k=5), ab.NullExpander(), None)
    agg = res["aggregate"]
    assert agg["num_cases"] == 3
    assert 0.0 <= agg["context_precision"] <= 1.0
    assert 0.0 <= agg["context_recall"] <= 1.0
    assert agg["FULL"] + agg["PART"] + agg["MISS"] == 3
    # mock-full has both kws in a top doc -> at least one FULL; mock-miss has none.
    assert agg["FULL"] >= 1
    assert agg["MISS"] >= 1
    assert len(res["per_case"]) == 3


def test_smaller_k_does_not_lower_rank_weighted_precision_on_mock():
    # Dropping the low-rank IRRELEVANT/noise tail must not reduce precision.
    exp = ab.NullExpander()
    rows = ab.mock_rows()
    p5 = ab.evaluate_arm(rows, _arm(k=5), exp, None)["aggregate"]["context_precision"]
    p2 = ab.evaluate_arm(rows, _arm(k=2), exp, None)["aggregate"]["context_precision"]
    assert p2 >= p5 - 1e-9


def test_build_grid_grade_toggle():
    assert all(a.grade is False for a in ab.build_grid(with_grade=False))
    assert len(ab.build_grid(with_grade=True)) > len(ab.build_grid(with_grade=False))
    assert any(a.grade for a in ab.build_grid(with_grade=True))
    assert any(a.name == ab.BASELINE_ARM for a in ab.build_grid(with_grade=False))


def _mk_arm_result(name, prec, recall, full, miss):
    return {
        "arm": name,
        "aggregate": {
            "context_precision": prec, "context_recall": recall,
            "FULL": full, "PART": 0, "MISS": miss, "num_cases": 100,
        },
    }


def test_verdict_baseline_and_ship_and_no_ship():
    crit = ab.ShipCriteria()
    base = _mk_arm_result("prod", 0.51, 0.92, 96, 1)
    assert ab.verdict_for_arm(base, base, crit)[0] == "BASELINE"

    ship = _mk_arm_result("k3", 0.51 + crit.min_precision_gain + 0.01, 0.91, 96, 1)
    assert ab.verdict_for_arm(ship, base, crit)[0] == "SHIP-CANDIDATE"

    # precision gain big enough, but recall breaches the floor -> no-ship
    recall_break = _mk_arm_result("k3", 0.70, 0.85, 96, 1)
    assert ab.verdict_for_arm(recall_break, base, crit)[0] == "no-ship"

    # FULL regression -> no-ship even with a precision lift
    full_break = _mk_arm_result("no-expand", 0.70, 0.95, 90, 1)
    assert ab.verdict_for_arm(full_break, base, crit)[0] == "no-ship"

    # MISS regression -> no-ship
    miss_break = _mk_arm_result("k3", 0.70, 0.95, 96, 3)
    assert ab.verdict_for_arm(miss_break, base, crit)[0] == "no-ship"


def test_render_markdown_has_table_and_baseline_row():
    rows = ab.mock_rows()
    report = ab.run(
        rows,
        grid=ab.build_grid(with_grade=False),
        expander=ab.NullExpander(),
        with_grade=False,
        stub_grade=False,
        with_judge=False,
        mode="mock",
        rerank_artifact="mock",
    )
    md = ab.render_markdown(report)
    assert "| arm | rerank_k |" in md
    assert "BASELINE" in md
    # baseline row is first in the arms list
    assert report["arms"][0]["arm"] == ab.BASELINE_ARM

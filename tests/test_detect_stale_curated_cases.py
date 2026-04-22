from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import detect_stale_curated_cases as detector


def _case(case_id: str, **overrides):
    base = {
        "case_id": case_id,
        "tenant_id": "acme",
        "input": {"query": "q"},
        "expected": {
            "route": "auto",
            "min_quality": 80,
            "min_factuality": 80,
            "answer_contains": ["42"],
        },
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_is_case_age_stale_returns_true_for_old_case() -> None:
    now = datetime.now(timezone.utc)
    case = _case("c1", created_at=(now - timedelta(days=400)).isoformat())
    assert detector.is_case_age_stale(case, now=now, stale_days=180) is True


def test_is_case_age_stale_returns_false_for_young_case() -> None:
    now = datetime.now(timezone.utc)
    case = _case("c2", created_at=(now - timedelta(days=30)).isoformat())
    assert detector.is_case_age_stale(case, now=now, stale_days=180) is False


def test_compare_verdicts_detects_route_drift() -> None:
    case = _case("c3")
    rerun = {"route": "escalate", "quality_score": 90, "factuality_score": 90, "answer": "42"}
    decision = detector.compare_verdicts(case, rerun)
    assert decision.is_stale is True
    assert decision.reason == "route_drift"


def test_compare_verdicts_detects_quality_drop() -> None:
    case = _case("c4")
    rerun = {"route": "auto", "quality_score": 50, "factuality_score": 90, "answer": "42"}
    decision = detector.compare_verdicts(case, rerun, quality_delta=10)
    assert decision.is_stale is True
    assert decision.reason == "quality_drop"


def test_compare_verdicts_detects_missing_phrases() -> None:
    case = _case("c5")
    rerun = {"route": "auto", "quality_score": 90, "factuality_score": 90, "answer": "no number"}
    decision = detector.compare_verdicts(case, rerun)
    assert decision.is_stale is True
    assert decision.reason == "answer_contains_missing"
    assert decision.diff["missing"] == ["42"]


def test_compare_verdicts_returns_fresh_when_matching() -> None:
    case = _case("c6")
    rerun = {"route": "auto", "quality_score": 90, "factuality_score": 90, "answer": "the answer is 42"}
    decision = detector.compare_verdicts(case, rerun)
    assert decision.is_stale is False
    assert decision.reason is None


@pytest.mark.asyncio
async def test_run_detection_writes_rows_only_when_apply_true(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    jsonl = tmp_path / "curated.jsonl"
    old = _case("old", created_at=(now - timedelta(days=400)).isoformat())
    jsonl.write_text(json.dumps(old) + "\n", encoding="utf-8")

    async def _rerun(case: dict) -> dict:
        return {"route": "escalate", "quality_score": 50, "factuality_score": 90, "answer": "no"}

    captured_sql: list[tuple[str, dict]] = []

    class _Session:
        async def execute(self, statement, params=None):
            captured_sql.append((" ".join(str(statement).split()).upper(), dict(params or {})))

            class _Result:
                def mappings(self):
                    return self

                def all(self):
                    return []

            return _Result()

        async def commit(self):
            return None

    decisions = await detector.run_detection(
        jsonl_path=jsonl,
        rerun_fn=_rerun,
        session=_Session(),
        stale_days=180,
        now=now,
        apply_to_db=True,
    )

    assert len(decisions) == 1
    assert decisions[0].is_stale is True
    inserts = [sql for sql, _ in captured_sql if sql.startswith("INSERT INTO CURATED_CASE_STATUS")]
    assert len(inserts) == 1


@pytest.mark.asyncio
async def test_run_detection_skips_young_cases(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    jsonl = tmp_path / "curated.jsonl"
    young = _case("young", created_at=(now - timedelta(days=30)).isoformat())
    jsonl.write_text(json.dumps(young) + "\n", encoding="utf-8")

    async def _rerun(case: dict) -> dict:
        raise AssertionError("rerun should not be called for young cases")

    decisions = await detector.run_detection(
        jsonl_path=jsonl,
        rerun_fn=_rerun,
        stale_days=180,
        now=now,
    )
    assert decisions == []


def test_load_curated_cases_ignores_bad_lines(tmp_path: Path) -> None:
    jsonl = tmp_path / "curated.jsonl"
    jsonl.write_text(
        json.dumps(_case("ok")) + "\n" + "not-json\n" + "\n",
        encoding="utf-8",
    )
    cases = detector.load_curated_cases(jsonl)
    assert len(cases) == 1
    assert cases[0]["case_id"] == "ok"


def test_main_cli_writes_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jsonl = tmp_path / "curated.jsonl"
    now = datetime.now(timezone.utc)
    old = _case("cli-old", created_at=(now - timedelta(days=400)).isoformat())
    jsonl.write_text(json.dumps(old) + "\n", encoding="utf-8")

    report_path = tmp_path / "out.md"
    rc = detector.main(
        [
            "--jsonl",
            str(jsonl),
            "--stale-days",
            "180",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 0
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "Curated staleness report" in text
    assert "evaluated: 1" in text

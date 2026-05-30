from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from auth.jwt_handler import create_access_token


ADMIN_HEADERS = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


def _make_cases(module):
    return [
        module.CuratedCase(
            case_id="case-router-reset",
            tenant_id="acme",
            query="How do I reset the router?",
            expected=module.CaseExpectation(
                answer_contains=["reset"],
                answer_not_contains=["unknown"],
                route="auto",
                min_quality=80,
                min_factuality=90,
                citations_min_count=1,
            ),
        ),
        module.CuratedCase(
            case_id="case-warranty",
            tenant_id="acme",
            query="Is the repair covered by warranty?",
            expected=module.CaseExpectation(
                answer_contains=["warranty"],
                route="auto",
                min_quality=70,
                min_factuality=70,
            ),
        ),
        module.CuratedCase(
            case_id="case-hours",
            tenant_id="beta",
            query="What are your support hours?",
            expected=module.CaseExpectation(
                answer_contains=["hours"],
                route="auto",
                min_quality=70,
                min_factuality=70,
                citations_min_count=1,
            ),
        ),
    ]


def _executor_factory(module):
    outputs = {
        ("baseline", "case-router-reset"): module.CaseRunResult(
            answer="Use the reset button to reset the router.",
            quality_score=92,
            factuality_score=96,
            citations=[{"doc_id": "kb-router"}],
            duration_ms=1200,
            cost_usd=0.011,
            route="auto",
            trace_id="trace-baseline-router",
        ),
        ("baseline", "case-warranty"): module.CaseRunResult(
            answer="I am not sure.",
            quality_score=55,
            factuality_score=45,
            citations=[],
            duration_ms=900,
            cost_usd=0.008,
            route="human",
            trace_id="trace-baseline-warranty",
        ),
        ("baseline", "case-hours"): module.CaseRunResult(
            answer="Support hours are 9-5.",
            quality_score=87,
            factuality_score=91,
            citations=[{"doc_id": "kb-hours"}],
            duration_ms=700,
            cost_usd=0.006,
            route="auto",
            trace_id="trace-baseline-hours",
        ),
        ("candidate", "case-router-reset"): module.CaseRunResult(
            answer="Contact support.",
            quality_score=40,
            factuality_score=50,
            citations=[],
            duration_ms=1100,
            cost_usd=0.005,
            route="human",
            trace_id="trace-candidate-router",
        ),
        ("candidate", "case-warranty"): module.CaseRunResult(
            answer="The warranty covers the repair.",
            quality_score=84,
            factuality_score=88,
            citations=[{"doc_id": "kb-warranty"}],
            duration_ms=980,
            cost_usd=0.009,
            route="auto",
            trace_id="trace-candidate-warranty",
        ),
        ("candidate", "case-hours"): module.CaseRunResult(
            answer="Support hours are 9-5 on weekdays.",
            quality_score=90,
            factuality_score=92,
            citations=[{"doc_id": "kb-hours"}, {"doc_id": "kb-schedule"}],
            duration_ms=640,
            cost_usd=0.007,
            route="auto",
            trace_id="trace-candidate-hours",
        ),
    }

    def _executor(case, experiment_id):
        return outputs[(experiment_id, case.case_id)]

    return _executor


class _FakeSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb
        return None


def _write_experiment_yaml(tmp_path: Path, experiment_id: str) -> None:
    experiments_dir = tmp_path / "evaluation" / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": experiment_id,
        "name": "regression candidate",
        "created_at": "2026-04-21T00:00:00+00:00",
        "created_by": "system",
        "description": "candidate",
        "prompt_overrides": {},
        "settings_overrides": {},
        "parent_experiment_id": None,
        "status": "draft",
        "tags": [],
    }
    (experiments_dir / f"{experiment_id}.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )


def test_run_regression_cases_aggregates_pass_rates_and_diffs() -> None:
    from scripts import regression_eval

    cases = _make_cases(regression_eval)
    report = regression_eval.run_regression_cases(
        cases,
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
        dataset_path=Path("evaluation/curated_cases.jsonl"),
        tenant="all",
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert report["aggregate"]["baseline_pass_rate"] == pytest.approx(2 / 3, abs=0.0001)
    assert report["aggregate"]["candidate_pass_rate"] == pytest.approx(2 / 3, abs=0.0001)
    assert report["aggregate"]["regressions"] == 1
    assert report["aggregate"]["new_passes"] == 1
    assert report["aggregate"]["neutral"] == 1

    hours_case = next(item for item in report["cases"] if item["case_id"] == "case-hours")
    assert hours_case["diff"]["answer_changed"] is True
    assert hours_case["diff"]["quality_delta"] == 3
    assert hours_case["diff"]["factuality_delta"] == 1
    assert hours_case["diff"]["route_changed"] is False
    assert hours_case["diff"]["citations_delta"] == 1
    assert hours_case["diff"]["cost_delta"] == pytest.approx(0.001)


def test_run_regression_cases_detects_regressions() -> None:
    from scripts import regression_eval

    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
    )

    assert [item["case_id"] for item in report["regressions"]] == ["case-router-reset"]
    assert "route expected 'auto'" in report["regressions"][0]["why_failed"][0]


def test_run_regression_cases_detects_new_passes() -> None:
    from scripts import regression_eval

    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
    )

    assert [item["case_id"] for item in report["new_passes"]] == ["case-warranty"]


def test_run_regression_cases_sets_exit_code_one_when_regressions_exceed_gate() -> None:
    from scripts import regression_eval

    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=0,
        min_pass_rate=0.5,
    )

    assert report["gate"]["passed"] is False
    assert report["exit_code"] == 1
    assert "max regressions" in report["gate"]["reasons"][0]


def test_run_regression_cases_sets_exit_code_zero_when_candidate_passes_gate() -> None:
    from scripts import regression_eval

    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
    )

    assert report["gate"]["passed"] is True
    assert report["exit_code"] == 0


def test_evaluate_case_output_requires_one_answer_contains_any_match() -> None:
    from scripts import regression_eval

    expected = regression_eval.CaseExpectation(
        answer_contains=["чек"],
        answer_contains_any=[["сервис", "поддерж"]],
    )
    result = regression_eval.CaseRunResult(
        answer="Чек нужен, но куда обращаться не указано.",
        quality_score=90,
        factuality_score=90,
        route="auto",
    )

    passed, failures = regression_eval._evaluate_case_output(result, expected)

    assert passed is False
    assert failures == ["answer missing one of ['сервис', 'поддерж']"]


def test_evaluate_case_output_accepts_answer_contains_any_alternative() -> None:
    from scripts import regression_eval

    expected = regression_eval.CaseExpectation(
        answer_contains=["чек"],
        answer_contains_any=[["сервис", "поддерж"]],
    )
    result = regression_eval.CaseRunResult(
        answer="Если чек утерян, обратитесь в службу поддержки.",
        quality_score=90,
        factuality_score=90,
        route="auto",
    )

    passed, failures = regression_eval._evaluate_case_output(result, expected)

    assert passed is True
    assert failures == []


def test_mock_provider_result_includes_answer_contains_any_representative() -> None:
    from scripts import regression_eval

    case = regression_eval.CuratedCase(
        case_id="case-support-or-service",
        tenant_id="default",
        query="Where should I go?",
        expected=regression_eval.CaseExpectation(
            answer_contains=["чек"],
            answer_contains_any=[["сервис", "поддерж"]],
        ),
    )

    result = regression_eval._build_mock_provider_result(
        case,
        "mistral-small-latest",
        {
            "provider_id": "mistral",
            "model_name": "mistral-small-latest",
            "input_price_per_1m_tokens": 0.1,
            "output_price_per_1m_tokens": 0.2,
        },
    )

    assert "чек" in result.answer
    assert "сервис" in result.answer


def test_sample_cases_is_deterministic_for_seed() -> None:
    from scripts import regression_eval

    cases = [
        regression_eval.CuratedCase(
            case_id=f"case-{idx}",
            tenant_id="acme",
            query=f"q-{idx}",
            expected=regression_eval.CaseExpectation(),
        )
        for idx in range(10)
    ]

    first = regression_eval.sample_cases(cases, max_cases=4, seed=42)
    second = regression_eval.sample_cases(cases, max_cases=4, seed=42)

    assert [item.case_id for item in first] == [item.case_id for item in second]


def test_wall_clock_duration_fills_missing_trace_duration(monkeypatch) -> None:
    from scripts import regression_eval

    monkeypatch.setattr(regression_eval.time, "perf_counter", lambda: 12.345)

    result = regression_eval.CaseRunResult(answer="ok", duration_ms=None)
    measured = regression_eval._with_wall_clock_duration(result, started_at=10.0)

    assert measured.duration_ms == 2345
    assert result.duration_ms is None


def test_wall_clock_duration_preserves_trace_duration(monkeypatch) -> None:
    from scripts import regression_eval

    monkeypatch.setattr(regression_eval.time, "perf_counter", lambda: 99.0)

    result = regression_eval.CaseRunResult(answer="ok", duration_ms=1234)
    measured = regression_eval._with_wall_clock_duration(result, started_at=10.0)

    assert measured.duration_ms == 1234


def test_write_report_files_emits_valid_json_sidecar(tmp_path: Path) -> None:
    from scripts import regression_eval

    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    markdown_path, json_path = regression_eval.write_report_files(
        report,
        project_root=tmp_path,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert markdown_path.exists()
    assert json_path.exists()
    assert payload["baseline"] == "baseline"
    assert payload["candidate"] == "candidate"
    assert payload["aggregate"]["regressions"] == 1
    assert payload["gate"]["passed"] is True
    assert payload["cases"][0]["baseline"]["answer"]


def test_persist_regression_result_adds_eval_result_row() -> None:
    from scripts import regression_eval

    class _FakeSession:
        def __init__(self) -> None:
            self.added = []
            self.commit_calls = 0

        def add(self, obj) -> None:
            self.added.append(obj)

        async def commit(self) -> None:
            self.commit_calls += 1

    fake_session = _FakeSession()
    report = regression_eval.run_regression_cases(
        _make_cases(regression_eval),
        baseline="baseline",
        candidate="candidate",
        executor=_executor_factory(regression_eval),
        max_regressions=2,
        min_pass_rate=0.5,
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    asyncio.run(
        regression_eval.persist_regression_result(
            session_factory=_FakeSessionFactory(fake_session),
            report=report,
            report_path=Path("reports/regression/report.json"),
        )
    )

    assert fake_session.commit_calls == 1
    assert len(fake_session.added) == 1
    row = fake_session.added[0]
    assert row.kind == "regression"
    assert row.run_id == report["run_id"]
    assert row.baseline_experiment_id == "baseline"
    assert row.candidate_experiment_id == "candidate"
    assert row.report_path == "reports/regression/report.json"


def test_admin_regression_run_endpoint_queues_job(
    client_with_key,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app

    experiment_id = "2026-04-21-regression"
    _write_experiment_yaml(tmp_path, experiment_id)

    scheduled = []

    def _fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return None

    monkeypatch.setattr(api_app.asyncio, "create_task", _fake_create_task)

    response = client_with_key.post(
        f"/api/admin/experiments/{experiment_id}/regression-run?baseline=current",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["job_id"].startswith("regression-")
    assert len(scheduled) == 1


def test_admin_regression_run_detail_returns_persisted_report(
    client_with_key,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app

    async def _fake_get_regression_run_row(run_id: str):
        _ = run_id
        return {
            "run_id": "regression-123",
            "created_at": "2026-04-21T12:00:00+00:00",
            "value": 0.75,
            "sample_size": 4,
            "drift_alert": True,
            "baseline_experiment_id": "current",
            "candidate_experiment_id": "2026-04-21-regression",
            "report_path": "reports/regression/report.json",
        }

    monkeypatch.setattr(api_app, "_get_regression_run_row", _fake_get_regression_run_row)
    monkeypatch.setattr(
        api_app,
        "_read_regression_report_assets",
        lambda report_path: ({"run_id": "regression-123", "aggregate": {"regressions": 2}}, "# report"),
    )

    response = client_with_key.get(
        "/api/admin/regression-runs/regression-123",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "regression-123"
    assert payload["result"] == "fail"
    assert payload["report"]["aggregate"]["regressions"] == 2
    assert payload["report_markdown"] == "# report"

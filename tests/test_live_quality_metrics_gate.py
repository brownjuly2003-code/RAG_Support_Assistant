"""Plan §5.5: live quality metrics gate scaffold (×3 DoD thresholds)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.live_quality_metrics_gate import (
    FORBIDDEN_LIVE_FLAGS,
    MIN_RUNS,
    OPT_IN_ENV,
    PLAN_THRESHOLDS,
    REQUIRED_LIVE_FLAGS,
    aggregate_metric_runs,
    assess_readiness,
    build_live_metrics_commands,
    evaluate_aggregate_against_dod,
    is_live_opt_in,
    main,
    validate_live_command,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "live-quality-metrics-gate.yml"


def test_plan_thresholds_match_section_5_dod() -> None:
    assert PLAN_THRESHOLDS["context_precision"] == 0.63
    assert PLAN_THRESHOLDS["context_recall"] == 0.97
    assert PLAN_THRESHOLDS["full_rate"] == 0.97
    assert PLAN_THRESHOLDS["miss_count_max"] == 1
    assert PLAN_THRESHOLDS["faithfulness"] == 0.90
    assert PLAN_THRESHOLDS["answer_relevancy"] == 0.92
    assert PLAN_THRESHOLDS["unverified_auto_rate"] == 0.0
    assert MIN_RUNS == 3


def test_live_commands_are_multi_run_and_forbid_mock() -> None:
    cmds = build_live_metrics_commands(runs=3, max_cases=10, base_seed=7)
    assert len(cmds) == 3
    seeds = []
    for cmd in cmds:
        assert "--mock-experiment-runtime" not in cmd
        for flag in REQUIRED_LIVE_FLAGS:
            assert flag in cmd
        assert validate_live_command(cmd) == []
        # seed argument present and distinct across runs
        idx = cmd.index("--seed")
        seeds.append(int(cmd[idx + 1]))
    assert len(set(seeds)) == 3
    bad = list(cmds[0]) + ["--mock-experiment-runtime"]
    assert any("forbidden" in r for r in validate_live_command(bad))
    for flag in FORBIDDEN_LIVE_FLAGS:
        assert flag == "--mock-experiment-runtime"


def test_opt_in_env_and_cli() -> None:
    assert is_live_opt_in(env={}, cli_live=False) is False
    assert is_live_opt_in(env={OPT_IN_ENV: "1"}, cli_live=False) is True
    assert is_live_opt_in(env={}, cli_live=True) is True
    assert is_live_opt_in(env={OPT_IN_ENV: "false"}, cli_live=False) is False


def test_aggregate_requires_min_runs() -> None:
    runs = [
        {
            "context_precision": 0.7,
            "context_recall": 0.98,
            "full_rate": 0.98,
            "miss_count": 0,
            "faithfulness": 0.91,
            "answer_relevancy": 0.93,
            "unverified_auto_rate": 0.0,
        }
    ]
    agg = aggregate_metric_runs(runs)
    assert agg["n_runs"] == 1
    assert agg["min_runs_met"] is False
    verdict = evaluate_aggregate_against_dod(agg)
    assert verdict["passed"] is False
    assert any("min_runs" in r for r in verdict["reasons"])


def test_aggregate_passes_when_floors_and_three_runs_clear() -> None:
    base = {
        "context_precision": 0.70,
        "context_recall": 0.98,
        "full_rate": 0.99,
        "miss_count": 0,
        "faithfulness": 0.95,
        "answer_relevancy": 0.94,
        "unverified_auto_rate": 0.0,
    }
    runs = [dict(base) for _ in range(3)]
    # slight variance still above floors
    runs[1]["context_precision"] = 0.65
    runs[2]["faithfulness"] = 0.91
    agg = aggregate_metric_runs(runs)
    assert agg["n_runs"] == 3
    assert agg["min_runs_met"] is True
    assert "context_precision" in agg["means"]
    assert "context_precision" in agg["ci95_half_width"]
    verdict = evaluate_aggregate_against_dod(agg)
    assert verdict["passed"] is True
    assert verdict["reasons"] == []


def test_aggregate_fails_on_unverified_auto_or_low_faithfulness() -> None:
    base = {
        "context_precision": 0.80,
        "context_recall": 0.99,
        "full_rate": 0.99,
        "miss_count": 0,
        "faithfulness": 0.95,
        "answer_relevancy": 0.95,
        "unverified_auto_rate": 0.0,
    }
    runs = [dict(base) for _ in range(3)]
    runs[0]["unverified_auto_rate"] = 0.01
    agg = aggregate_metric_runs(runs)
    verdict = evaluate_aggregate_against_dod(agg)
    assert verdict["passed"] is False
    assert any("unverified_auto_rate" in r for r in verdict["reasons"])

    runs2 = [dict(base) for _ in range(3)]
    runs2[0]["faithfulness"] = 0.5
    runs2[1]["faithfulness"] = 0.5
    runs2[2]["faithfulness"] = 0.5
    verdict2 = evaluate_aggregate_against_dod(aggregate_metric_runs(runs2))
    assert verdict2["passed"] is False
    assert any("faithfulness" in r for r in verdict2["reasons"])


def test_readiness_without_opt_in_is_skipped_not_release_pass() -> None:
    dataset = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
    result = assess_readiness(
        mode="readiness",
        live_requested=False,
        env={},
        dataset=dataset,
    )
    assert result.verdict == "SKIPPED_NO_OPT_IN"
    assert result.release_passed is False
    assert result.evidence_valid is False
    assert result.release_eligible_to_attempt is False
    assert result.min_runs == MIN_RUNS
    report = result.to_report()
    assert report["kind"] == "live-quality-metrics-gate"
    assert report["gate"]["passed"] is False
    assert report["thresholds"]["context_precision"] == 0.63


def test_readiness_opt_in_without_secrets_fail_closed() -> None:
    dataset = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
    result = assess_readiness(
        mode="live",
        live_requested=True,
        env={OPT_IN_ENV: "1"},
        dataset=dataset,
    )
    assert result.opt_in is True
    assert result.verdict == "FAIL_NO_CREDENTIALS"
    assert result.release_eligible_to_attempt is False


def test_readiness_opt_in_with_secret_ready() -> None:
    dataset = PROJECT_ROOT / "evaluation" / "curated_cases.jsonl"
    result = assess_readiness(
        mode="live",
        live_requested=True,
        env={OPT_IN_ENV: "1", "MISTRAL_API_KEY": "test-not-changeme"},
        dataset=dataset,
        runs=3,
    )
    assert result.release_eligible_to_attempt is True
    assert result.verdict in {"READY", "READY_NOT_EXECUTED"}
    assert len(result.commands) == 3
    assert all("--release-gate" in c for c in result.commands)


def test_main_readiness_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "ready.json"
    code = main(["--mode", "readiness", "--write-report", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["kind"] == "live-quality-metrics-gate"
    assert payload["release_passed"] is False
    assert payload["gate"]["passed"] is False
    assert payload["gate"]["verdict"] == "SKIPPED_NO_OPT_IN"
    assert payload["min_runs"] == 3


def test_main_mode_live_fail_closed_without_keys(
    tmp_path: Path, monkeypatch
) -> None:
    for key in (
        "MISTRAL_API_KEY",
        "GRACEKELLY_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        OPT_IN_ENV,
    ):
        monkeypatch.delenv(key, raising=False)
    out = tmp_path / "live.json"
    code = main(["--mode", "live", "--write-report", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "FAIL_NO_CREDENTIALS"
    assert payload["release_passed"] is False


def test_workflow_exists_and_defaults_to_readiness() -> None:
    assert WORKFLOW.is_file()
    text = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["name"]
    # PyYAML parses bare `on:` as boolean True.
    on_block = data.get("on") if "on" in data else data.get(True)
    assert isinstance(on_block, dict)
    dispatch = on_block["workflow_dispatch"]["inputs"]
    assert dispatch["enable_live"]["default"] is False
    assert "live_quality_metrics_gate.py" in text
    assert "--mode readiness" in text
    assert "RAG_LIVE_QUALITY_METRICS_GATE" in text

"""Plan §5.5: live quality metrics gate (×3 DoD thresholds)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import live_quality_metrics_gate as gate_mod
from scripts.live_quality_metrics_gate import (
    FORBIDDEN_LIVE_FLAGS,
    MIN_RUNS,
    OPT_IN_ENV,
    PLAN_THRESHOLDS,
    REQUIRED_LIVE_FLAGS,
    aggregate_metric_runs,
    assess_readiness,
    build_live_metrics_commands,
    detect_provider_secrets,
    evaluate_aggregate_against_dod,
    is_live_opt_in,
    main,
    validate_live_command,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "live-quality-metrics-gate.yml"

PASSING_SECTION5_METRICS = {
    "context_precision": 0.70,
    "context_recall": 0.98,
    "full_rate": 0.99,
    "miss_count": 0.0,
    "faithfulness": 0.95,
    "answer_relevancy": 0.94,
    "unverified_auto_rate": 0.0,
}


def _rel_to_workspace(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def _write_section5_sidecar(
    path: Path,
    metrics: dict[str, float],
    *,
    mode: str = "experiment-regression",
    evidence_valid: bool = True,
    release_passed: bool = True,
    extra: dict | None = None,
) -> None:
    payload: dict = {
        "mode": mode,
        "evidence_valid": evidence_valid,
        "release_passed": release_passed,
        "gate": {
            "passed": bool(release_passed and evidence_valid),
            "metrics_passed": True,
            "evidence_valid": evidence_valid,
            "release_passed": release_passed,
            "verdict": "PASS" if (release_passed and evidence_valid) else "FAIL",
            "reasons": [],
        },
        "aggregate": dict(metrics),
    }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _child_summary_stdout(report_json: str, *, extra_lines: list[str] | None = None) -> str:
    summary = json.dumps(
        {
            "run_id": "synthetic",
            "exit_code": 0,
            "report_json": report_json,
            "gate": {"release_passed": True, "evidence_valid": True},
        },
        ensure_ascii=False,
    )
    lines = list(extra_lines or [])
    lines.append(summary)
    return "\n".join(lines) + "\n"


def _enable_live_env(monkeypatch) -> None:
    monkeypatch.setenv(OPT_IN_ENV, "1")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-not-changeme")
    for key in (
        "GRACEKELLY_API_KEY",
        "OPENCODE_ZEN_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _install_child_runner(monkeypatch, responses: list) -> list[list[str]]:
    """Monkeypatch live child runner; record argv lists (no real subprocess)."""
    seen: list[list[str]] = []
    queue = list(responses)

    def _fake(cmd, *, cwd=PROJECT_ROOT):  # noqa: ANN001
        assert cwd == PROJECT_ROOT or Path(cwd) == PROJECT_ROOT
        seen.append(list(cmd))
        assert "--mock-experiment-runtime" not in cmd
        for flag in REQUIRED_LIVE_FLAGS:
            assert flag in cmd
        if not queue:
            raise AssertionError("unexpected extra child invocation")
        item = queue.pop(0)
        if hasattr(gate_mod, "LiveChildCapture"):
            if isinstance(item, gate_mod.LiveChildCapture):
                return item
            returncode, stdout, stderr = item
            return gate_mod.LiveChildCapture(
                returncode=int(returncode),
                stdout=str(stdout),
                stderr=str(stderr),
            )
        return item

    monkeypatch.setattr(gate_mod, "run_live_subprocess", _fake)
    return seen


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


def test_detect_provider_secrets_accepts_opencode_zen_key() -> None:
    assert detect_provider_secrets({"OPENCODE_ZEN_API_KEY": "zen-test-key"}) == [
        "OPENCODE_ZEN_API_KEY"
    ]


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
        "OPENCODE_ZEN_API_KEY",
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
    steps = data["jobs"]["live-quality-metrics-gate"]["steps"]
    live = next(step for step in steps if step.get("name") == "Quality metrics gate opt-in attempt")
    assert "OPENCODE_ZEN_API_KEY" in (live.get("env") or {})


def test_live_execute_three_passing_sidecars_dod_pass(
    tmp_path: Path, monkeypatch
) -> None:
    """Exact report_json sidecars with all §5 floors → DOD_PASS."""
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    stdout_marker = "UNIQUE_STDOUT_MARKER_56_QA_PASS"
    stderr_marker = "UNIQUE_STDERR_MARKER_56_QA_PASS"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        metrics = dict(PASSING_SECTION5_METRICS)
        metrics["context_precision"] = 0.70 + i * 0.01
        _write_section5_sidecar(path, metrics)
        rel = _rel_to_workspace(path)
        # Unique stream markers must never appear in the final gate report.
        stdout = stdout_marker + "\n" + _child_summary_stdout(rel)
        responses.append((0, stdout, stderr_marker if i == 0 else ""))

    seen = _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        [
            "--mode",
            "live",
            "--execute",
            "--runs",
            "3",
            "--write-report",
            str(out),
        ]
    )
    assert code == 0
    assert len(seen) == 3
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "DOD_PASS"
    assert payload["evidence_valid"] is True
    assert payload["release_passed"] is True
    assert payload["gate"]["passed"] is True
    assert payload["gate"]["release_passed"] is True
    assert payload["aggregate"]["n_runs"] == 3
    assert payload["dod_result"]["passed"] is True
    # No raw child streams in the final report.
    dumped = json.dumps(payload)
    assert stdout_marker not in dumped
    assert stderr_marker not in dumped
    assert "Please reset" not in dumped


def test_live_execute_threshold_miss_dod_fail(tmp_path: Path, monkeypatch) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        metrics = dict(PASSING_SECTION5_METRICS)
        # All three runs below faithfulness floor → aggregate mean fails DoD.
        metrics["faithfulness"] = 0.50
        _write_section5_sidecar(path, metrics)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "DOD_FAIL"
    assert payload["evidence_valid"] is True
    assert payload["release_passed"] is False
    assert payload["gate"]["passed"] is False
    assert any("faithfulness" in r for r in payload["reasons"])


def test_live_execute_missing_canonical_metric_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        metrics = dict(PASSING_SECTION5_METRICS)
        if i == 1:
            del metrics["context_recall"]
        _write_section5_sidecar(path, metrics)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False
    assert payload["gate"]["passed"] is False
    assert payload["gate"]["verdict"] != "DOD_PASS"
    assert any("context_recall" in r or "metric" in r.lower() for r in payload["reasons"])


def test_live_execute_malformed_child_summary_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    path = tmp_path / "sidecars" / "run_0.json"
    _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
    # One good + two malformed summaries.
    good = (0, _child_summary_stdout(_rel_to_workspace(path)), "")
    responses = [
        good,
        (0, "not-json-at-all\nstill-not-json\n", ""),
        (0, json.dumps({"exit_code": 0}) + "\n", ""),  # missing report_json
    ]
    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False
    assert payload["gate"]["verdict"] != "DOD_PASS"


def test_live_execute_missing_sidecar_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    missing = tmp_path / "sidecars" / "does_not_exist.json"
    # Point at a path inside workspace that is not a file.
    rel = _rel_to_workspace(tmp_path / "sidecars") + "/does_not_exist.json"
    assert not missing.exists()
    responses = [
        (0, _child_summary_stdout(rel), ""),
        (0, _child_summary_stdout(rel), ""),
        (0, _child_summary_stdout(rel), ""),
    ]
    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False


def test_live_execute_nonzero_child_fail_closed_even_if_sidecar_green(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    stdout_marker = "UNIQUE_STDOUT_MARKER_56_QA_NZ"
    stderr_marker = "UNIQUE_STDERR_MARKER_56_QA_NZ"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        stdout = stdout_marker + "\n" + _child_summary_stdout(_rel_to_workspace(path))
        # Middle child non-zero even though sidecar is green.
        rc = 2 if i == 1 else 0
        responses.append((rc, stdout, stderr_marker if rc else ""))

    seen = _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    # Fail-fast: stop after the first invalid child (run index 1).
    assert len(seen) == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False
    assert payload["gate"]["passed"] is False
    # Must not leak raw child stream content into the report.
    dumped = json.dumps(payload)
    assert stdout_marker not in dumped
    assert stderr_marker not in dumped
    assert "child boom" not in dumped


def test_live_execute_mock_or_invalid_evidence_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        if i == 0:
            _write_section5_sidecar(
                path,
                PASSING_SECTION5_METRICS,
                mode="mock-experiment-regression",
                evidence_valid=False,
                release_passed=False,
            )
        else:
            _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False
    assert payload["gate"]["verdict"] != "DOD_PASS"


def test_live_execute_report_path_outside_workspace_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    # Absolute path outside PROJECT_ROOT (sibling of the workspace).
    outside_path = (
        PROJECT_ROOT.resolve().parent / "_not_in_rag_workspace_56" / "x.json"
    )
    try:
        outside_path.resolve().relative_to(PROJECT_ROOT.resolve())
        raise AssertionError("fixture path unexpectedly inside workspace")
    except ValueError:
        pass

    responses = [
        (0, _child_summary_stdout(str(outside_path)), ""),
        (0, _child_summary_stdout(str(outside_path)), ""),
        (0, _child_summary_stdout(str(outside_path)), ""),
    ]
    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False
    assert any(
        "outside" in r.lower() or "workspace" in r.lower() or "report_json" in r.lower()
        for r in payload["reasons"]
    )


def test_live_execute_uses_exact_report_json_not_newest_file(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    # Decoy files that would win a "newest file" or glob heuristic.
    decoy_a = reports_dir / "zzz_newest_decoy.json"
    decoy_b = reports_dir / "aaa_other_decoy.json"
    bad = dict(PASSING_SECTION5_METRICS)
    bad["faithfulness"] = 0.1
    bad["context_precision"] = 0.1
    _write_section5_sidecar(decoy_a, bad)
    _write_section5_sidecar(decoy_b, bad)

    responses = []
    for i in range(3):
        path = reports_dir / f"exact_run_{i}.json"
        _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        # Multi-line stdout: noise + JSON summary last.
        stdout = _child_summary_stdout(
            _rel_to_workspace(path),
            extra_lines=["progress: ok", "noise {not json}", '{"status":"partial"}'],
        )
        responses.append((0, stdout, ""))

    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "DOD_PASS"
    assert payload["release_passed"] is True
    # Means must reflect exact sidecars (passing), not decoys.
    assert payload["aggregate"]["means"]["faithfulness"] >= 0.90


def test_live_execute_malformed_sidecar_json_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if i == 0:
            path.write_text("{not-valid-json", encoding="utf-8")
        else:
            _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_passed"] is False
    assert payload["evidence_valid"] is False


def test_live_execute_missing_evidence_fields_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    """Sidecar with green metrics but missing honesty flags must not release-pass."""
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        if i == 0:
            # Green metrics only — no mode / evidence_valid / release_passed / gate.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"aggregate": dict(PASSING_SECTION5_METRICS)}, indent=2)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    seen = _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    assert len(seen) == 1  # fail-fast on first invalid evidence
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert out.is_file()
    assert payload["evidence_valid"] is False
    assert payload["release_passed"] is False
    assert payload["gate"]["passed"] is False
    assert payload["gate"]["verdict"] != "DOD_PASS"
    assert any(
        "missing" in r.lower() or "mode" in r.lower() or "evidence" in r.lower()
        for r in payload["reasons"]
    )


def test_live_execute_contradictory_evidence_flags_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    """Top-level vs gate honesty flags must not contradict."""
    _enable_live_env(monkeypatch)
    reports_dir = tmp_path / "sidecars"
    responses = []
    for i in range(3):
        path = reports_dir / f"run_{i}.json"
        if i == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "mode": "experiment-regression",
                "evidence_valid": True,
                "release_passed": True,
                "gate": {
                    "passed": False,  # contradicts top-level release honesty
                    "metrics_passed": True,
                    "evidence_valid": True,
                    "release_passed": False,
                    "verdict": "FAIL",
                    "reasons": [],
                },
                "aggregate": dict(PASSING_SECTION5_METRICS),
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            _write_section5_sidecar(path, PASSING_SECTION5_METRICS)
        responses.append((0, _child_summary_stdout(_rel_to_workspace(path)), ""))

    seen = _install_child_runner(monkeypatch, responses)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    assert len(seen) == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert out.is_file()
    assert report["evidence_valid"] is False
    assert report["release_passed"] is False
    assert report["gate"]["passed"] is False
    assert report["gate"]["verdict"] != "DOD_PASS"
    assert any(
        "release" in r.lower() or "false" in r.lower() or "gate" in r.lower()
        for r in report["reasons"]
    )


def test_live_execute_runner_exception_fail_closed_no_marker_leak(
    tmp_path: Path, monkeypatch
) -> None:
    """Child runner exceptions convert to sanitized fail-closed report."""
    _enable_live_env(monkeypatch)
    marker = "MARKER_EXC_SECRET_PAYLOAD_56_QA"
    seen: list[list[str]] = []

    def _raising_runner(cmd, *, cwd=PROJECT_ROOT):  # noqa: ANN001
        seen.append(list(cmd))
        raise RuntimeError(marker)

    monkeypatch.setattr(gate_mod, "run_live_subprocess", _raising_runner)
    out = tmp_path / "gate.json"
    code = main(
        ["--mode", "live", "--execute", "--runs", "3", "--write-report", str(out)]
    )
    assert code == 1
    assert len(seen) == 1  # fail-fast: no remaining paid children
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["evidence_valid"] is False
    assert payload["release_passed"] is False
    assert payload["gate"]["passed"] is False
    assert payload["gate"]["verdict"] != "DOD_PASS"
    dumped = json.dumps(payload)
    assert marker not in dumped
    assert any("RuntimeError" in r for r in payload["reasons"])

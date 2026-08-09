"""Plan §7.6: live provider gate scaffold — policy, readiness, workflow contract."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.live_provider_gate import (
    FORBIDDEN_LIVE_FLAGS,
    OPT_IN_ENV,
    REQUIRED_LIVE_FLAGS,
    assess_readiness,
    build_live_regression_command,
    detect_provider_secrets,
    is_live_opt_in,
    main,
    validate_live_command,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "live-provider-gate.yml"


def test_live_command_forbids_mock_and_requires_release_flags() -> None:
    cmd = build_live_regression_command(max_cases=5)
    assert "--mock-experiment-runtime" not in cmd
    for flag in REQUIRED_LIVE_FLAGS:
        assert flag in cmd
    assert validate_live_command(cmd) == []
    bad = list(cmd) + ["--mock-experiment-runtime"]
    reasons = validate_live_command(bad)
    assert any("forbidden" in r for r in reasons)
    for flag in FORBIDDEN_LIVE_FLAGS:
        assert flag in {"--mock-experiment-runtime"}


def test_opt_in_env_and_cli() -> None:
    assert is_live_opt_in(env={}, cli_live=False) is False
    assert is_live_opt_in(env={OPT_IN_ENV: "1"}, cli_live=False) is True
    assert is_live_opt_in(env={}, cli_live=True) is True
    assert is_live_opt_in(env={OPT_IN_ENV: "false"}, cli_live=False) is False


def test_detect_provider_secrets_accepts_opencode_zen_key() -> None:
    assert detect_provider_secrets({"OPENCODE_ZEN_API_KEY": "zen-test-key"}) == [
        "OPENCODE_ZEN_API_KEY"
    ]


def test_readiness_without_opt_in_is_skipped_not_release_pass(
    tmp_path: Path,
) -> None:
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
    report = result.to_report()
    assert report["kind"] == "live-provider-gate"
    assert report["gate"]["passed"] is False
    assert report["gate"]["verdict"] == "SKIPPED_NO_OPT_IN"


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
    )
    assert result.release_eligible_to_attempt is True
    assert result.verdict in {"READY", "READY_NOT_EXECUTED"}
    assert "--release-gate" in result.command
    assert "--allow-paid-apis" in result.command
    assert "--mock-experiment-runtime" not in result.command


def test_main_readiness_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "ready.json"
    code = main(
        [
            "--mode",
            "readiness",
            "--write-report",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["kind"] == "live-provider-gate"
    assert payload["release_passed"] is False
    assert payload["gate"]["passed"] is False


def test_main_readiness_mode_never_requires_secrets(tmp_path: Path) -> None:
    """Default readiness path is a successful scaffold run (not release PASS)."""
    out = tmp_path / "ready2.json"
    code = main(["--mode", "readiness", "--write-report", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "SKIPPED_NO_OPT_IN"
    assert payload["gate"]["passed"] is False


def test_main_mode_live_implies_opt_in_and_fail_closed_without_keys(
    tmp_path: Path, monkeypatch
) -> None:
    # --mode live requests live; without keys → fail-closed (not silent PASS).
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GRACEKELLY_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv(OPT_IN_ENV, raising=False)
    out = tmp_path / "live.json"
    code = main(["--mode", "live", "--write-report", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "FAIL_NO_CREDENTIALS"
    assert payload["release_passed"] is False


def test_main_live_opt_in_no_keys_exits_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GRACEKELLY_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv(OPT_IN_ENV, "1")
    out = tmp_path / "fail.json"
    code = main(["--mode", "live", "--live", "--write-report", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["gate"]["verdict"] == "FAIL_NO_CREDENTIALS"


def test_workflow_scaffold_exists_and_is_opt_in() -> None:
    assert WORKFLOW.is_file()
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["name"] == "Live Provider Gate"
    on = data[True] if True in data else data["on"]
    assert "schedule" in on
    assert "workflow_dispatch" in on
    inputs = on["workflow_dispatch"]["inputs"]
    assert inputs["enable_live"]["default"] is False

    job = data["jobs"]["live-provider-gate"]
    steps = job["steps"]
    by_name = {s.get("name"): s for s in steps if s.get("name")}

    ready = by_name["Live gate readiness (scaffold, no live calls)"]
    assert "live_provider_gate.py" in ready["run"]
    assert "--mode readiness" in ready["run"]

    live = by_name["Live gate opt-in attempt"]
    assert "enable_live" in str(live.get("if", ""))
    assert "workflow_dispatch" in str(live.get("if", ""))
    live_run = str(live.get("run", ""))
    assert "--mode live" in live_run
    assert "--mock-experiment-runtime" not in live_run
    env = live.get("env") or {}
    assert env.get("RAG_LIVE_PROVIDER_GATE") == "1"
    assert "OPENCODE_ZEN_API_KEY" in env

    upload = by_name["Upload live gate reports"]
    assert "actions/upload-artifact@" in str(upload.get("uses", ""))

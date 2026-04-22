from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import chaos_drill


def test_ollama_timeout_drill_records_failures() -> None:
    report = chaos_drill.run_drill(fault="ollama_timeout", iterations=4)
    assert report.acceptance_passed is True
    assert sum(1 for e in report.events if e.kind == "ollama_call") == 4


def test_ollama_down_drill_records_connection_errors() -> None:
    report = chaos_drill.run_drill(fault="ollama_down", iterations=3)
    assert report.acceptance_passed is True
    assert all(e.detail == "connection refused" for e in report.events if e.kind == "ollama_call")


def test_postgres_unavailable_drill_sets_acceptance() -> None:
    report = chaos_drill.run_drill(fault="postgres_unavailable", iterations=2)
    assert report.acceptance_passed is True
    assert any(e.kind == "postgres_query" for e in report.events)


def test_redis_unavailable_drill_marks_degradation() -> None:
    report = chaos_drill.run_drill(fault="redis_unavailable", iterations=2)
    assert report.acceptance_passed is True
    assert any(e.kind == "redis_call" for e in report.events)


def test_network_slow_drill_applies_latency() -> None:
    report = chaos_drill.run_drill(
        fault="network_slow",
        iterations=3,
        extra_latency_ms=150.0,
    )
    assert report.acceptance_passed is True
    assert sum(1 for e in report.events if e.kind == "http_slow") == 3


def test_network_flaky_drill_produces_eventual_success() -> None:
    report = chaos_drill.run_drill(
        fault="network_flaky",
        iterations=10,
        failure_rate=0.5,
        seed=42,
    )
    assert report.acceptance_passed is True
    successes = [e for e in report.events if e.kind == "http_flaky" and "succeeded=True" in e.detail]
    assert len(successes) >= 1


def test_unsupported_fault_raises() -> None:
    with pytest.raises(ValueError):
        chaos_drill.run_drill(fault="cosmic_rays")


def test_render_report_and_cli(tmp_path: Path) -> None:
    report_path = tmp_path / "chaos.md"
    rc = chaos_drill.main(
        [
            "--fault",
            "ollama_timeout",
            "--iterations",
            "3",
            "--report",
            str(report_path),
        ]
    )
    assert rc == 0
    assert report_path.exists()
    markdown = report_path.read_text(encoding="utf-8")
    assert "Chaos drill" in markdown
    assert "ollama_timeout" in markdown

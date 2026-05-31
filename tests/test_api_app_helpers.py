from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def test_serialize_regression_job_normalizes_timestamps() -> None:
    import api.app as app_module

    created_at = datetime(2026, 5, 31, 12, 30, tzinfo=timezone.utc)

    payload = app_module._serialize_regression_job(
        {
            "run_id": "run-1",
            "created_at": created_at,
            "started_at": None,
            "finished_at": "already-serialized",
        }
    )

    assert payload == {
        "run_id": "run-1",
        "created_at": "2026-05-31T12:30:00+00:00",
        "started_at": None,
        "finished_at": "already-serialized",
    }


def test_read_regression_report_assets_reads_json_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.app as app_module

    report_dir = tmp_path / "reports" / "regression"
    report_dir.mkdir(parents=True)
    json_path = report_dir / "run-1.json"
    json_path.write_text('{"gate":{"passed":true}}', encoding="utf-8")
    json_path.with_suffix(".md").write_text("# Regression report\n", encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    report, markdown = app_module._read_regression_report_assets(
        "reports/regression/run-1.json"
    )

    assert report == {"gate": {"passed": True}}
    assert markdown == "# Regression report\n"


def test_read_regression_report_assets_handles_missing_or_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.app as app_module

    invalid_path = tmp_path / "broken.json"
    invalid_path.write_text("{not-json", encoding="utf-8")
    invalid_path.with_suffix(".md").write_text("fallback markdown", encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    assert app_module._read_regression_report_assets(None) == (None, None)
    assert app_module._read_regression_report_assets("missing.json") == (None, None)
    assert app_module._read_regression_report_assets("broken.json") == (
        None,
        "fallback markdown",
    )


def test_serialize_regression_row_sets_result_and_defaults() -> None:
    import api.app as app_module

    row = {
        "run_id": "abc",
        "drift_alert": True,
        "created_at": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "candidate_experiment_id": "candidate-a",
        "value": "0.875",
        "sample_size": "8",
    }

    payload = app_module._serialize_regression_row(row)

    assert payload["run_id"] == "abc"
    assert payload["status"] == "completed"
    assert payload["result"] == "fail"
    assert payload["baseline"] == "current"
    assert payload["candidate"] == "candidate-a"
    assert payload["candidate_pass_rate"] == 0.875
    assert payload["sample_size"] == 8


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Embedding dimension 1024 does not match collection dimension 3", True),
        ("Expected dimension 3, got 1024", True),
        ("connection timeout while probing vector store", False),
    ],
)
def test_is_embedding_dimension_error_matches_expected_messages(
    message: str,
    expected: bool,
) -> None:
    import api.app as app_module

    assert app_module._is_embedding_dimension_error(RuntimeError(message)) is expected


def test_extract_route_template_prefers_path_format_then_path() -> None:
    import api.app as app_module

    request = SimpleNamespace(
        scope={"route": SimpleNamespace(path_format="/api/items/{item_id}", path="/api/items/1")}
    )
    assert app_module._extract_route_template(request) == "/api/items/{item_id}"

    request = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/items/1")})
    assert app_module._extract_route_template(request) == "/api/items/1"

    request = SimpleNamespace(scope={})
    assert app_module._extract_route_template(request) == "unknown"

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.jwt_handler import create_access_token


ADMIN_HEADERS = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


def _project_settings(project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_root=project_root,
        data_dir=project_root / "data",
        ensure_dirs=lambda: None,
    )


def _write_experiment_yaml(project_root: Path, experiment_id: str, **overrides: object) -> Path:
    experiments_dir = project_root / "evaluation" / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": experiment_id,
        "name": "test experiment",
        "created_at": "2026-04-21T00:00:00+00:00",
        "created_by": "system",
        "description": "test description",
        "prompt_overrides": {"qa": "Override prompt: {question}"},
        "settings_overrides": {"retrieval_top_k": 9},
        "parent_experiment_id": None,
        "status": "draft",
        "tags": ["test"],
    }
    payload.update(overrides)
    path = experiments_dir / f"{experiment_id}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
    return path


def test_experiment_model_validates_slug() -> None:
    schema = importlib.import_module("evaluation.experiment_schema")

    with pytest.raises(ValidationError):
        schema.Experiment(
            id="Invalid Slug",
            name="bad",
            created_at=datetime.now(timezone.utc),
            created_by="system",
            description="bad id",
            prompt_overrides={},
            settings_overrides={},
            parent_experiment_id=None,
            status="draft",
            tags=[],
        )


def test_experiment_new_creates_yaml_from_current(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("scripts.experiment_new")
    monkeypatch.setattr(module, "get_settings", lambda: _project_settings(tmp_path))
    monkeypatch.setenv("USEREMAIL", "qa@example.com")

    with patch.object(
        sys,
        "argv",
        [
            "experiment_new.py",
            "--name",
            "test-concise",
            "--from",
            "current",
            "--description",
            "registry smoke test",
        ],
    ):
        assert module.main() == 0

    experiment_files = sorted((tmp_path / "evaluation" / "experiments").glob("*.yaml"))
    assert len(experiment_files) == 1

    payload = yaml.safe_load(experiment_files[0].read_text(encoding="utf-8"))
    assert payload["id"].endswith("-test-concise")
    assert payload["created_by"] == "qa@example.com"
    assert payload["status"] == "draft"
    assert "qa" in payload["prompt_overrides"]
    assert "retrieval_top_k" in payload["settings_overrides"]


def test_experiment_new_from_parent_copies_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parent_id = "2026-04-20-parent-registry"
    _write_experiment_yaml(
        tmp_path,
        parent_id,
        prompt_overrides={"qa": "Parent prompt"},
        settings_overrides={"retrieval_top_k": 11, "hybrid_search": False},
    )

    module = importlib.import_module("scripts.experiment_new")
    monkeypatch.setattr(module, "get_settings", lambda: _project_settings(tmp_path))

    with patch.object(
        sys,
        "argv",
        [
            "experiment_new.py",
            "--name",
            "child-registry",
            "--from",
            parent_id,
            "--description",
            "child",
        ],
    ):
        assert module.main() == 0

    experiment_files = sorted((tmp_path / "evaluation" / "experiments").glob("*.yaml"))
    assert len(experiment_files) == 2

    child_payload = yaml.safe_load(experiment_files[-1].read_text(encoding="utf-8"))
    assert child_payload["parent_experiment_id"] == parent_id
    assert child_payload["prompt_overrides"] == {"qa": "Parent prompt"}
    assert child_payload["settings_overrides"] == {"retrieval_top_k": 11, "hybrid_search": False}


def test_experiment_apply_dry_run_does_not_write_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_id = "2026-04-21-dry-run-test"
    _write_experiment_yaml(tmp_path, experiment_id)

    module = importlib.import_module("scripts.experiment_apply")
    monkeypatch.setattr(module, "get_settings", lambda: _project_settings(tmp_path))

    override_path = tmp_path / "config" / "experiment_override.yaml"
    with patch.object(sys, "argv", ["experiment_apply.py", experiment_id, "--mode", "dry-run"]):
        assert module.main() == 0

    assert not override_path.exists()
    assert "retrieval_top_k" in capsys.readouterr().out


def test_experiment_apply_stage_creates_override_yaml_and_settings_reads_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-21-stage-test"
    _write_experiment_yaml(
        tmp_path,
        experiment_id,
        settings_overrides={"retrieval_top_k": 13, "hybrid_search": False},
    )

    module = importlib.import_module("scripts.experiment_apply")
    monkeypatch.setattr(module, "get_settings", lambda: _project_settings(tmp_path))

    with patch.object(sys, "argv", ["experiment_apply.py", experiment_id, "--mode", "stage"]):
        assert module.main() == 0

    override_path = tmp_path / "config" / "experiment_override.yaml"
    assert override_path.exists()

    settings_module = importlib.import_module("config.settings")
    monkeypatch.setenv("EXPERIMENT_ID", experiment_id)
    monkeypatch.delenv("RAG_RETRIEVAL_TOP_K", raising=False)
    monkeypatch.setattr(settings_module, "_settings", None)
    monkeypatch.setattr(settings_module, "EXPERIMENT_OVERRIDE_PATH", override_path, raising=False)

    settings = settings_module.get_settings()
    assert settings.retrieval_top_k == 13
    assert settings.hybrid_search is False


def test_get_prompt_returns_override_from_experiment() -> None:
    schema = importlib.import_module("evaluation.experiment_schema")
    registry = importlib.import_module("agent.prompt_registry")

    experiment = schema.Experiment(
        id="2026-04-21-prompt-override",
        name="prompt override",
        created_at=datetime.now(timezone.utc),
        created_by="system",
        description="prompt override",
        prompt_overrides={"qa": "Experiment QA prompt: {question}"},
        settings_overrides={},
        parent_experiment_id=None,
        status="draft",
        tags=[],
    )

    assert registry.get_prompt("qa", experiment) == "Experiment QA prompt: {question}"
    assert registry.get_prompt("qa") != "Experiment QA prompt: {question}"


def test_admin_experiments_list_and_detail(
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-21-admin-list"
    _write_experiment_yaml(tmp_path, experiment_id, status="running")

    response = client_with_key.get("/api/admin/experiments", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["experiments"] == [
        {
            "id": experiment_id,
            "name": "test experiment",
            "status": "running",
            "latest_eval_link": None,
        }
    ]

    detail = client_with_key.get(f"/api/admin/experiments/{experiment_id}", headers=ADMIN_HEADERS)

    assert detail.status_code == 200
    assert detail.json()["id"] == experiment_id
    assert detail.json()["status"] == "running"


def test_admin_experiment_archive_updates_status(
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-21-admin-archive"
    path = _write_experiment_yaml(tmp_path, experiment_id, status="completed")

    response = client_with_key.post(f"/api/admin/experiments/{experiment_id}/archive", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "archived", "id": experiment_id}

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["status"] == "archived"

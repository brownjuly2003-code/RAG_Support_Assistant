from __future__ import annotations

import importlib
import importlib.util
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


class _AsyncMappingResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_AsyncMappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _ExperimentControlSession:
    def __init__(
        self,
        *,
        regression_rows: list[dict[str, object]] | None = None,
        deployment_rows: list[dict[str, object]] | None = None,
        assignment_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.regression_rows = regression_rows or []
        self.deployment_rows = deployment_rows or []
        self.assignment_rows = assignment_rows or []
        self.commits = 0

    async def __aenter__(self) -> "_ExperimentControlSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement, params: dict[str, object] | None = None) -> _AsyncMappingResult:
        sql = str(statement)
        values = dict(params or {})
        normalized = " ".join(sql.split()).upper()

        if "FROM EVAL_RESULTS" in normalized:
            experiment_id = values.get("experiment_id")
            rows = [
                dict(row)
                for row in self.regression_rows
                if experiment_id is None or row.get("candidate_experiment_id") == experiment_id
            ]
            return _AsyncMappingResult(rows[:1])

        if normalized.startswith("INSERT INTO EXPERIMENT_DEPLOYMENTS"):
            self.deployment_rows.append(dict(values))
            return _AsyncMappingResult()

        if normalized.startswith("UPDATE EXPERIMENT_DEPLOYMENTS"):
            for row in self.deployment_rows:
                if values.get("experiment_id") and row.get("experiment_id") != values["experiment_id"]:
                    continue
                if values.get("regression_run_id") and row.get("regression_run_id") != values["regression_run_id"]:
                    continue
                row.update(values)
            return _AsyncMappingResult()

        if "FROM EXPERIMENT_DEPLOYMENTS" in normalized:
            experiment_id = values.get("experiment_id")
            rows = [
                dict(row)
                for row in self.deployment_rows
                if experiment_id is None or row.get("experiment_id") == experiment_id
            ]
            if "ROLLED_BACK_AT IS NULL" in normalized:
                rows = [row for row in rows if row.get("rolled_back_at") is None]
            return _AsyncMappingResult(rows[:1] if "LIMIT" in normalized else rows)

        if normalized.startswith("DELETE FROM EXPERIMENT_ASSIGNMENTS"):
            tenant_id = values.get("tenant_id")
            self.assignment_rows = [
                row for row in self.assignment_rows if row.get("tenant_id") != tenant_id
            ]
            return _AsyncMappingResult()

        if normalized.startswith("INSERT INTO EXPERIMENT_ASSIGNMENTS"):
            self.assignment_rows.append(dict(values))
            return _AsyncMappingResult()

        if "FROM EXPERIMENT_ASSIGNMENTS" in normalized:
            experiment_id = values.get("experiment_id")
            rows = [
                dict(row)
                for row in self.assignment_rows
                if experiment_id is None or row.get("experiment_id") == experiment_id
            ]
            return _AsyncMappingResult(rows)

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self) -> None:
        self.commits += 1


def test_experiment_deployments_migration_upgrade_creates_table_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "015_experiment_deployments.py"
    )
    spec = importlib.util.spec_from_file_location("migration_015_experiment_deployments", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    table_calls: list[str] = []
    index_calls: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(module.op, "create_table", lambda name, *args, **kwargs: table_calls.append(name))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table_name, columns, **kwargs: index_calls.append((table_name, tuple(columns))),
    )

    module.upgrade()

    assert table_calls == ["experiment_deployments"]
    assert ("experiment_deployments", ("experiment_id",)) in index_calls
    assert ("experiment_deployments", ("deployed_at",)) in index_calls
    assert ("experiment_deployments", ("rolled_back_at",)) in index_calls


def test_experiment_deployments_migration_downgrade_drops_table_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "015_experiment_deployments.py"
    )
    spec = importlib.util.spec_from_file_location("migration_015_experiment_deployments", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "drop_index", lambda name, table_name=None: events.append(("drop_index", name)))
    monkeypatch.setattr(module.op, "drop_table", lambda name: events.append(("drop_table", name)))

    module.downgrade()

    assert ("drop_table", "experiment_deployments") in events


def test_admin_experiment_deploy_blocks_without_green_regression(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-22-deploy-blocked"
    _write_experiment_yaml(tmp_path, experiment_id, status="running")
    monkeypatch.setattr("db.engine.async_session", lambda: _ExperimentControlSession())

    response = client_with_key.post(
        f"/api/admin/experiments/{experiment_id}/deploy",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert "regression" in response.json()["detail"]


def test_admin_experiment_deploy_updates_status_and_writes_runtime_file(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-22-deploy-green"
    experiment_path = _write_experiment_yaml(tmp_path, experiment_id, status="running")
    session = _ExperimentControlSession(
        regression_rows=[
            {
                "run_id": "regression-green-1",
                "candidate_experiment_id": experiment_id,
                "drift_alert": False,
            }
        ]
    )
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.post(
        f"/api/admin/experiments/{experiment_id}/deploy",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deployed"
    assert payload["deployment"]["regression_run_id"] == "regression-green-1"
    assert yaml.safe_load(experiment_path.read_text(encoding="utf-8"))["status"] == "deployed"

    deployed_path = tmp_path / "config" / "deployed_experiment.yaml"
    assert deployed_path.exists()
    assert yaml.safe_load(deployed_path.read_text(encoding="utf-8"))["experiment_id"] == experiment_id


def test_admin_experiment_rollback_marks_deployment_and_clears_runtime_file(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-22-rollback"
    experiment_path = _write_experiment_yaml(tmp_path, experiment_id, status="deployed")
    deployed_path = tmp_path / "config" / "deployed_experiment.yaml"
    deployed_path.parent.mkdir(parents=True, exist_ok=True)
    deployed_path.write_text(
        yaml.safe_dump({"experiment_id": experiment_id}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    session = _ExperimentControlSession(
        deployment_rows=[
            {
                "experiment_id": experiment_id,
                "regression_run_id": "regression-green-1",
                "staged_at": "2026-04-22T10:00:00+00:00",
                "deployed_at": "2026-04-22T10:05:00+00:00",
                "rolled_back_at": None,
            }
        ]
    )
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    response = client_with_key.post(
        f"/api/admin/experiments/{experiment_id}/rollback",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
    assert yaml.safe_load(experiment_path.read_text(encoding="utf-8"))["status"] == "completed"
    assert not deployed_path.exists()
    assert session.deployment_rows[0]["rolled_back_at"] is not None


def test_admin_experiment_assignments_upsert_and_list(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
    tmp_path: Path,
) -> None:
    experiment_id = "2026-04-22-assignment"
    _write_experiment_yaml(tmp_path, experiment_id, status="running")
    session = _ExperimentControlSession()
    monkeypatch.setattr("db.engine.async_session", lambda: session)

    create = client_with_key.post(
        f"/api/admin/experiments/{experiment_id}/assignments",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "acme", "rollout_percentage": 25},
    )

    assert create.status_code == 200
    assert create.json()["assignment"]["tenant_id"] == "acme"
    assert create.json()["assignment"]["rollout_percentage"] == 25

    listing = client_with_key.get(
        f"/api/admin/experiments/{experiment_id}/assignments",
        headers=ADMIN_HEADERS,
    )

    assert listing.status_code == 200
    assert listing.json()["assignments"] == [
        {
            "tenant_id": "acme",
            "experiment_id": experiment_id,
            "rollout_percentage": 25,
            "rolled_out_at": listing.json()["assignments"][0]["rolled_out_at"],
        }
    ]

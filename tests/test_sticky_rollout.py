from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import prompt_registry


def _write_experiment_yaml(project_root: Path, experiment_id: str, **overrides) -> Path:
    experiments_dir = project_root / "evaluation" / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": experiment_id,
        "name": "sticky-test",
        "created_at": "2026-04-23T00:00:00+00:00",
        "created_by": "tests",
        "description": "sticky rollout",
        "prompt_overrides": {"qa": f"STICKY {experiment_id} {{question}}"},
        "settings_overrides": {},
        "parent_experiment_id": None,
        "status": "running",
        "tags": [],
    }
    payload.update(overrides)
    path = experiments_dir / f"{experiment_id}.yaml"
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    return path


@pytest.fixture(autouse=True)
def _reset_cache():
    prompt_registry.clear_assignment_cache()
    yield
    prompt_registry.clear_assignment_cache()


def _fake_settings(tmp_path: Path, *, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        experiment_assignment_enabled=enabled,
        project_root=tmp_path,
    )


def test_resolver_returns_none_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-off"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 100)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=False))

    assert prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-1") is None


def test_resolver_returns_experiment_at_full_rollout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-full"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 100)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    exp = prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-1")
    assert exp is not None
    assert exp.id == experiment_id


def test_resolver_returns_none_when_rollout_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-zero"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 0)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    assert prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-1") is None


def test_resolver_is_sticky_for_same_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-deterministic"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 50)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    first = prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-42")
    second = prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-42")
    assert (first is None) == (second is None)


def test_resolver_bucket_distribution_respects_rollout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-distrib"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 25)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    exposed = 0
    total = 1000
    for index in range(total):
        result = prompt_registry.resolve_active_experiment(
            tenant_id="acme", user_id=f"u-{index}"
        )
        if result is not None:
            exposed += 1

    ratio = exposed / total
    assert 0.15 < ratio < 0.35


def test_resolver_returns_none_when_yaml_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_registry.set_assignment_cache_entry("acme", "missing-yaml", 100)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    assert prompt_registry.resolve_active_experiment(tenant_id="acme", user_id="u-1") is None


def test_resolver_ignores_tenant_without_assignment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    experiment_id = "2026-04-23-sticky-other"
    _write_experiment_yaml(tmp_path, experiment_id)
    prompt_registry.set_assignment_cache_entry("acme", experiment_id, 100)

    monkeypatch.setattr("config.settings.get_settings", lambda: _fake_settings(tmp_path, enabled=True))

    assert prompt_registry.resolve_active_experiment(tenant_id="unknown-tenant", user_id="u-1") is None


@pytest.mark.asyncio
async def test_refresh_cache_from_db_populates_cache() -> None:
    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def all(self):
            return list(self._rows)

    class _Session:
        async def execute(self, statement, params=None):
            return _Result(
                [
                    {"tenant_id": "acme", "experiment_id": "exp-1", "rollout_percentage": 50},
                    {"tenant_id": "widgets", "experiment_id": "exp-2", "rollout_percentage": 100},
                ]
            )

    count = await prompt_registry.refresh_assignment_cache_from_db(_Session())
    assert count == 2
    assert prompt_registry._ASSIGNMENTS_CACHE["acme"]["rollout_percentage"] == 50
    assert prompt_registry._ASSIGNMENTS_CACHE["widgets"]["experiment_id"] == "exp-2"

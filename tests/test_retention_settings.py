from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_NAME = "VECTORDB_RETENTION_MAX_VERSIONS"


def test_retention_budget_default_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.delenv(_ENV_NAME, raising=False)
    assert Settings().vectordb_retention_max_versions == 2

    monkeypatch.setenv(_ENV_NAME, "4")
    assert Settings().vectordb_retention_max_versions == 4


@pytest.mark.parametrize("raw_value", ["", "three", "2.5"])
def test_retention_budget_rejects_malformed_env_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv(_ENV_NAME, raw_value)

    with pytest.raises(RuntimeError, match=_ENV_NAME):
        Settings()


@pytest.mark.parametrize("raw_value", ["-1", "0", "1"])
def test_retention_budget_validation_rejects_values_below_two_before_io(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv(_ENV_NAME, raw_value)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: pytest.fail("invalid retention budget reached network I/O"),
    )

    with pytest.raises(RuntimeError, match=_ENV_NAME):
        Settings().validate()


def test_retention_budget_is_documented_for_operators() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    config_docs = (PROJECT_ROOT / "docs" / "CONFIGURATION.md").read_text(
        encoding="utf-8"
    )

    assert f"{_ENV_NAME}=2" in env_example
    assert f"`{_ENV_NAME}`" in config_docs

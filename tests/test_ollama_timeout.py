from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def _reset_graph_state():
    import agent.graph as graph

    graph._default_breaker = None
    yield
    graph._default_breaker = None


def test_default_timeout_is_60_seconds(monkeypatch, _reset_graph_state) -> None:
    monkeypatch.delenv("OLLAMA_REQUEST_TIMEOUT_SEC", raising=False)

    import config.settings as settings_module

    settings_module._settings = None
    captured_kwargs: dict[str, object] = {}

    def fake_ollama(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()

    import agent.graph as graph

    monkeypatch.setattr("langchain_community.llms.Ollama", fake_ollama)

    graph.LocalOllamaLLM(model_name="test-model", breaker=None)

    timeout = captured_kwargs.get("timeout") or captured_kwargs.get("request_timeout")
    assert timeout == pytest.approx(60.0)


def test_custom_timeout_from_env(monkeypatch, _reset_graph_state) -> None:
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SEC", "15.5")

    import config.settings as settings_module

    settings_module._settings = None
    captured_kwargs: dict[str, object] = {}

    def fake_ollama(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()

    import agent.graph as graph

    monkeypatch.setattr("langchain_community.llms.Ollama", fake_ollama)

    graph.LocalOllamaLLM(model_name="test-model", breaker=None)

    timeout = captured_kwargs.get("timeout") or captured_kwargs.get("request_timeout")
    assert timeout == pytest.approx(15.5)


def test_timeout_setting_reachable_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SEC", "120")

    import config.settings as settings_module

    settings_module._settings = None

    settings = settings_module.get_settings()

    assert settings.ollama_request_timeout_sec == pytest.approx(120.0)

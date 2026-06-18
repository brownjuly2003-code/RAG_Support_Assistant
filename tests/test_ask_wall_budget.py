from __future__ import annotations

import time
from types import SimpleNamespace

import pytest


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "agentic_mode": False,
        "ask_budget_sec": 0.0,
        "quality_threshold": 80,
        "online_evaluators_enabled": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_ask_returns_degraded_result_when_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dogfood finding #3: a slow/flapping provider must not hang ask() forever
    once a wall-budget is configured — it returns a graceful timeout result."""
    import agent.graph as graph

    # ask() does a local `from config.settings import get_settings`, so the budget
    # must be patched at the source module, not on graph.
    monkeypatch.setattr(
        "config.settings.get_settings", lambda: _settings(ask_budget_sec=0.2), raising=False
    )

    def _slow_pipeline(**kwargs):
        time.sleep(2.0)
        return {"answer": "too late", "route": "auto", "quality_score": 90}

    monkeypatch.setattr(graph, "run_qa_pipeline", _slow_pipeline, raising=False)

    session = graph.ConversationSession(retriever=object(), llm=None)
    started = time.perf_counter()
    result = session.ask("долгий вопрос", tenant_id="acme")
    elapsed = time.perf_counter() - started

    assert result["route"] == "timeout"
    assert result["error"] is True
    assert result["quality_score"] == 0
    assert "прервана" in result["answer"]
    # returned well before the 2s pipeline would have finished
    assert elapsed < 1.5
    # degraded answer is still recorded in history
    assert session.history[-1]["content"] == result["answer"]


def test_ask_returns_normal_result_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings", lambda: _settings(ask_budget_sec=5.0), raising=False
    )
    monkeypatch.setattr(
        graph,
        "run_qa_pipeline",
        lambda **kwargs: {"answer": "ok", "route": "auto", "quality_score": 88},
        raising=False,
    )

    session = graph.ConversationSession(retriever=object(), llm=None)
    result = session.ask("быстрый вопрос")

    assert result["answer"] == "ok"
    assert result["route"] == "auto"


def test_ask_budget_off_by_default_uses_blocking_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    monkeypatch.setattr("config.settings.get_settings", lambda: _settings(), raising=False)
    calls = {"n": 0}

    def _pipeline(**kwargs):
        calls["n"] += 1
        return {"answer": "direct", "route": "auto", "quality_score": 80}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)

    session = graph.ConversationSession(retriever=object(), llm=None)
    result = session.ask("вопрос")

    assert result["answer"] == "direct"
    assert calls["n"] == 1


def test_ask_budget_sec_default_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_ASK_BUDGET_SEC", raising=False)
    from config.settings import Settings

    assert Settings().ask_budget_sec == 0.0

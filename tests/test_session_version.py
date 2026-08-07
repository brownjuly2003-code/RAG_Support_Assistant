"""3.1i — optimistic session version + sticky identity into normal pipeline."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "agentic_mode": False,
        "ask_budget_sec": 0.0,
        "quality_threshold": 80,
        "online_evaluators_enabled": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_mutation_version_starts_at_zero_and_advances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: _settings(),
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "run_qa_pipeline",
        lambda **kwargs: {"answer": "ok", "route": "auto", "quality_score": 80},
        raising=False,
    )
    session = graph.ConversationSession(retriever=object(), llm=None)
    assert session.mutation_version == 0

    result = session.ask("q1")
    assert result["route"] == "auto"
    assert result["session_version"] == 1
    assert session.mutation_version == 1

    result2 = session.ask("q2", expected_version=1)
    assert result2["route"] == "auto"
    assert result2["session_version"] == 2
    assert session.mutation_version == 2


def test_expected_version_mismatch_is_conflict_not_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    calls: list[str] = []

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: _settings(),
        raising=False,
    )

    def _pipeline(**kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs.get("question") or ""))
        return {"answer": "ok", "route": "auto", "quality_score": 80}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)
    session.ask("first")  # version → 1

    conflict = session.ask("stale", expected_version=0)
    assert conflict["route"] == "conflict"
    assert conflict.get("error") is True
    assert conflict.get("error_node") == "session_version"
    assert conflict["session_version"] == 1
    assert conflict["route"] != "auto"
    assert calls == ["first"]  # pipeline must not run on conflict
    assert session.history  # prior history preserved
    assert all(m.get("content") != "stale" for m in session.history if m.get("role") == "user")


def test_expected_version_match_runs_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: _settings(),
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "run_qa_pipeline",
        lambda **kwargs: {"answer": f"ans-{kwargs['question']}", "route": "auto", "quality_score": 80},
        raising=False,
    )
    session = graph.ConversationSession(retriever=object(), llm=None)
    assert session.mutation_version == 0
    r = session.ask("ok", expected_version=0)
    assert r["route"] == "auto"
    assert r["answer"] == "ans-ok"
    assert r["session_version"] == 1


def test_ask_forwards_user_and_session_id_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sticky experiment residual: normal path must receive identity keys."""
    import agent.graph as graph

    seen: dict[str, Any] = {}

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: _settings(),
        raising=False,
    )

    def _pipeline(**kwargs: Any) -> dict[str, Any]:
        seen["user_id"] = kwargs.get("user_id")
        seen["session_id"] = kwargs.get("session_id")
        seen["tenant_id"] = kwargs.get("tenant_id")
        return {"answer": "ok", "route": "auto", "quality_score": 80}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)
    session.ask(
        "q",
        tenant_id="acme",
        user_id="user-42",
        session_id="sess-99",
    )
    assert seen == {
        "user_id": "user-42",
        "session_id": "sess-99",
        "tenant_id": "acme",
    }


def test_invalid_expected_version_type_is_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: _settings(),
        raising=False,
    )
    monkeypatch.setattr(
        graph,
        "run_qa_pipeline",
        lambda **kwargs: {"answer": "ok", "route": "auto", "quality_score": 80},
        raising=False,
    )
    session = graph.ConversationSession(retriever=object(), llm=None)
    result = session.ask("q", expected_version="not-an-int")  # type: ignore[arg-type]
    assert result["route"] == "conflict"
    assert result.get("error_node") == "session_version"

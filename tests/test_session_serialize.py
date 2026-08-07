"""3.1c — per-session serialize / turn epoch fail-closed."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest


def test_concurrent_asks_serialize_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two parallel ask() on one session must not interleave history turns."""
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            agentic_mode=False,
            ask_budget_sec=0.0,
            quality_threshold=80,
            online_evaluators_enabled=False,
        ),
        raising=False,
    )

    order: list[str] = []
    order_lock = threading.Lock()

    def _pipeline(**kwargs):  # noqa: ANN003
        question = kwargs.get("question") or ""
        with order_lock:
            order.append(f"start:{question}")
        time.sleep(0.08)
        with order_lock:
            order.append(f"end:{question}")
        return {
            "answer": f"ans-{question}",
            "route": "auto",
            "quality_score": 80,
        }

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)

    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def _worker(label: str) -> None:
        try:
            results[label] = session.ask(label)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    t1 = threading.Thread(target=_worker, args=("a",))
    t2 = threading.Thread(target=_worker, args=("b",))
    t1.start()
    time.sleep(0.02)  # let first thread acquire the turn
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not t1.is_alive() and not t2.is_alive()
    assert errors == []

    # Fully nested serialization: one turn completes before the other starts.
    assert order in (
        ["start:a", "end:a", "start:b", "end:b"],
        ["start:b", "end:b", "start:a", "end:a"],
    ), order

    history = session.history
    assert len(history) == 4
    # Turns are complete pairs in order of completion.
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == f"ans-{history[0]['content']}"
    assert history[2]["role"] == "user"
    assert history[3]["role"] == "assistant"
    assert history[3]["content"] == f"ans-{history[2]['content']}"


def test_stale_pending_write_discarded_after_epoch_bump() -> None:
    import agent.graph as graph

    session = graph.ConversationSession(retriever=object(), llm=None)
    turn = session._acquire_turn()
    assert session._set_pending_action(
        {"summary": "s", "priority": "medium", "action_summary": "x"},
        turn=turn,
    )
    # Simulate wall-budget invalidate of the owning turn.
    with session._lock:
        session._mutation_epoch += 1
    assert (
        session._set_pending_action(
            {"summary": "late", "priority": "high", "action_summary": "y"},
            turn=turn,
        )
        is False
    )
    # Pending remains whatever was current before stale write (or cleared).
    pending = session._get_pending_action_copy()
    # After epoch bump without clear, old pending still visible unless cleared.
    # Stale writer must not replace it with "late".
    if pending is not None:
        assert pending["summary"] != "late"
    session._release_turn(turn, invalidate=False)


def test_wall_budget_timeout_invalidates_orphan_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orphan worker after wall-budget must not leave pending_action."""
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            agentic_mode=False,
            ask_budget_sec=0.15,
            quality_threshold=80,
            online_evaluators_enabled=False,
        ),
        raising=False,
    )

    def _pipeline(**kwargs):  # noqa: ANN003
        # Emulate agentic pending set then long work (orphan after budget).
        session_ref["s"]._set_pending_action(
            {
                "summary": "orphan",
                "priority": "medium",
                "action_summary": "orphan-action",
            }
        )
        time.sleep(0.5)
        return {"answer": "too-late", "route": "auto", "quality_score": 90}

    session_ref: dict[str, graph.ConversationSession] = {}
    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)
    session_ref["s"] = session

    result = session.ask("slow")
    assert result["route"] == "timeout"
    assert result.get("error_node") == "wall_budget"
    # Give orphan a moment; pending must stay cleared / not orphan-owned.
    time.sleep(0.1)
    assert session._get_pending_action_copy() is None
    # Timeout answer is still recorded once.
    assert any(m.get("role") == "assistant" for m in session.history)


def test_clear_waits_and_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent.graph as graph

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            agentic_mode=False,
            ask_budget_sec=0.0,
            quality_threshold=80,
            online_evaluators_enabled=False,
        ),
        raising=False,
    )

    entered = threading.Event()
    release = threading.Event()

    def _pipeline(**kwargs):  # noqa: ANN003
        entered.set()
        release.wait(timeout=2)
        return {"answer": "ok", "route": "auto", "quality_score": 80}

    monkeypatch.setattr(graph, "run_qa_pipeline", _pipeline, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)

    def _ask() -> None:
        session.ask("during-clear")

    t = threading.Thread(target=_ask)
    t.start()
    assert entered.wait(timeout=2)

    cleared = threading.Event()

    def _clear() -> None:
        session.clear()
        cleared.set()

    tc = threading.Thread(target=_clear)
    tc.start()
    # clear must block while ask holds the turn
    time.sleep(0.05)
    assert not cleared.is_set()
    release.set()
    t.join(timeout=3)
    tc.join(timeout=3)
    assert cleared.is_set()
    assert session.history == []

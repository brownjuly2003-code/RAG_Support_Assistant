"""3.1a — shared request executor (no per-request ThreadPoolExecutor)."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture(autouse=True)
def _reset_executor() -> None:
    from utils import request_executor as re

    re.reset_request_executor_for_tests()
    yield
    re.reset_request_executor_for_tests()


def test_get_request_executor_is_singleton() -> None:
    from utils.request_executor import get_request_executor

    a = get_request_executor(max_workers=2)
    b = get_request_executor(max_workers=2)
    assert a is b


def test_run_on_request_executor_respects_timeout() -> None:
    from utils.request_executor import run_on_request_executor

    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        run_on_request_executor(lambda: time.sleep(1.0), timeout_sec=0.15)
    assert time.perf_counter() - started < 0.8


def test_nested_on_worker_runs_inline_without_deadlock() -> None:
    """Nested budget must not re-submit onto the same saturated pool."""
    from utils.request_executor import (
        get_request_executor,
        is_on_request_executor_thread,
        run_on_request_executor,
    )

    get_request_executor(max_workers=1)
    seen: dict[str, bool] = {}

    def outer() -> str:
        seen["on_worker"] = is_on_request_executor_thread()
        # Nested call with timeout must not block forever on the only worker.
        return run_on_request_executor(lambda: "nested-ok", timeout_sec=0.5)

    result = run_on_request_executor(outer, timeout_sec=2.0)
    assert result == "nested-ok"
    assert seen["on_worker"] is True


def test_ask_budget_does_not_construct_private_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ConversationSession must not allocate per-request pools."""
    import agent.graph as graph
    from utils import request_executor as re

    constructions: list[int] = []
    real_tpe = ThreadPoolExecutor

    class TrackingPool(real_tpe):
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            constructions.append(1)
            super().__init__(*a, **k)

    monkeypatch.setattr(
        "concurrent.futures.ThreadPoolExecutor",
        TrackingPool,
    )
    # Re-bind inside request_executor module after patch.
    monkeypatch.setattr(re, "ThreadPoolExecutor", TrackingPool)
    re.reset_request_executor_for_tests()

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agentic_mode": False,
                "ask_budget_sec": 0.2,
                "quality_threshold": 80,
                "online_evaluators_enabled": False,
                "request_executor_max_workers": 2,
                "max_concurrent_pipelines": 2,
            },
        )(),
        raising=False,
    )

    def _slow(**kwargs):  # noqa: ANN003
        time.sleep(1.0)
        return {"answer": "late", "route": "auto", "quality_score": 90}

    monkeypatch.setattr(graph, "run_qa_pipeline", _slow, raising=False)
    session = graph.ConversationSession(retriever=object(), llm=None)
    result = session.ask("q")
    assert result["route"] == "timeout"
    # Shared pool may construct once; never one pool per ask call repeatedly.
    assert sum(constructions) <= 1


def test_request_executor_max_workers_setting_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REQUEST_EXECUTOR_MAX_WORKERS", raising=False)
    from config.settings import Settings

    assert Settings().request_executor_max_workers == 0


def test_submit_marks_worker_thread() -> None:
    from utils.request_executor import is_on_request_executor_thread, submit_request

    barrier = threading.Barrier(2)
    flag = {"on": False}

    def work() -> None:
        flag["on"] = is_on_request_executor_thread()
        barrier.wait(timeout=2)

    fut = submit_request(work)
    barrier.wait(timeout=2)
    fut.result(timeout=2)
    assert flag["on"] is True
    assert is_on_request_executor_thread() is False

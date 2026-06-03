"""Unit tests for utils.background_tasks.spawn_tracked."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from utils import background_tasks


def test_routers_use_spawn_tracked_not_bare_create_task() -> None:
    """F1 guard: fire-and-forget background work in routers must go through
    spawn_tracked, never a bare asyncio.create_task whose result is dropped
    (the task can be garbage-collected mid-run). Covers the audit miss in
    admin_kb.py and prevents the pattern from creeping back into any router."""
    routers_dir = Path(__file__).resolve().parents[1] / "api" / "routers"
    offenders = [
        path.name
        for path in sorted(routers_dir.glob("*.py"))
        if re.search(r"create_task\s*\(", path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"use spawn_tracked, not create_task, in: {offenders}"


def test_spawn_tracked_holds_reference_then_discards_on_completion() -> None:
    async def _scenario() -> int:
        released = asyncio.Event()

        async def _work() -> int:
            await released.wait()
            return 42

        task = background_tasks.spawn_tracked(_work())
        # Strong reference retained while the task is in flight.
        assert task in background_tasks._background_tasks

        released.set()
        result = await task
        # done-callback runs on the loop; give it a turn to fire.
        await asyncio.sleep(0)
        assert task not in background_tasks._background_tasks
        return result

    assert asyncio.run(_scenario()) == 42


def test_spawn_tracked_tolerates_patched_non_task_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()

    def _fake_create_task(coro):  # type: ignore[no-untyped-def]
        coro.close()
        return sentinel

    monkeypatch.setattr(background_tasks.asyncio, "create_task", _fake_create_task)

    async def _noop() -> None:
        return None

    result = background_tasks.spawn_tracked(_noop())
    assert result is sentinel
    # A non-Task return must not be tracked.
    assert sentinel not in background_tasks._background_tasks

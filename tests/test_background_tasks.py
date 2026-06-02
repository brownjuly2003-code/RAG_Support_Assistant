"""Unit tests for utils.background_tasks.spawn_tracked."""
from __future__ import annotations

import asyncio

import pytest

from utils import background_tasks


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

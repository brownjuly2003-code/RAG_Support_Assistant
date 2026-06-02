"""Tracked spawning of fire-and-forget asyncio tasks.

``asyncio.create_task`` returns a task that the running loop references only
weakly; without an additional strong reference the task can be garbage-collected
mid-execution (a documented asyncio footgun). ``spawn_tracked`` keeps a strong
reference in a module-level set until the task finishes, so fire-and-forget work
(audit-log writes, citation stats, regression jobs) cannot silently vanish.

This module imports nothing from the project, so it is safe to use from any
layer (including ``db.*``) without creating an import cycle.
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine

_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_tracked(coro: Coroutine[Any, Any, Any]) -> "asyncio.Task[Any] | None":
    """Schedule *coro* on the running loop and retain a strong reference.

    The reference is dropped automatically once the task finishes via
    ``add_done_callback``, so the tracking set never grows unbounded. The result
    of ``asyncio.create_task`` is tracked only when it exposes
    ``add_done_callback``; this tolerates call sites whose ``create_task`` is
    monkeypatched to return a sentinel (as some tests do).
    """
    task = asyncio.create_task(coro)
    if hasattr(task, "add_done_callback"):
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    return task

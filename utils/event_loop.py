"""Handle to the application's main event loop for sync->async bridging.

The RAG pipeline runs synchronously inside ``asyncio.to_thread``. Anything it
needs to persist through the async SQLAlchemy engine must run on the loop that
owns the asyncpg pool — otherwise each call needs its own ``asyncio.run()``
plus a full ``engine.dispose()`` (the old Bug 2 workaround, which destroyed
the connection pool after every request).

``api.app`` registers the loop at startup; worker threads fetch it via
``get_main_loop()`` and schedule coroutines with
``asyncio.run_coroutine_threadsafe``. Sync CLI scripts never register a loop
and keep using the legacy ``asyncio.run()`` path.
"""
from __future__ import annotations

import asyncio
from typing import Optional

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    loop = _main_loop
    if loop is not None and loop.is_closed():
        return None
    return loop

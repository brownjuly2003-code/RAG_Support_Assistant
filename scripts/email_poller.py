#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from channels.email_channel import poll_once


async def _noop_process(message) -> None:
    _ = message
    return None


async def main() -> int:
    await poll_once(_noop_process)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

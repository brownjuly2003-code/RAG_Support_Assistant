#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging
import sys

from channels.email_channel import poll_forever, poll_once


async def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if "--once" in sys.argv:
        await poll_once()
        return 0

    await poll_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

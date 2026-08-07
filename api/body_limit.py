"""ASGI received-byte body limits (plan §8.2 / API-01).

Content-Length alone is not a trust boundary: clients can omit it, understate
it, or stream more bytes than advertised. Limits must count **actually
received** ``http.request`` body chunks.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# Starlette receive callable: () -> message dict
Receive = Callable[[], Awaitable[dict[str, Any]]]


class BodySizeExceeded(Exception):
    """Raised when cumulative received body bytes exceed the configured limit."""

    def __init__(self, *, received: int, limit: int) -> None:
        self.received = received
        self.limit = limit
        super().__init__(
            f"Request body too large ({received} bytes received, limit {limit})"
        )


def parse_content_length(header_value: str | None) -> int | None:
    """Return non-negative Content-Length, or None if absent/unparseable."""
    if header_value is None:
        return None
    try:
        size = int(header_value)
    except (TypeError, ValueError):
        return None
    if size < 0:
        return None
    return size


def make_limited_receive(receive: Receive, *, limit: int) -> Receive:
    """Wrap an ASGI receive callable to enforce a cumulative body-byte limit.

    Counts only ``http.request`` message bodies. Disconnect and other message
    types pass through unchanged. Raises :class:`BodySizeExceeded` when the
    cumulative size of received body chunks exceeds ``limit``.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")

    received = 0

    async def limited_receive() -> dict[str, Any]:
        nonlocal received
        message = await receive()
        if message.get("type") == "http.request":
            chunk = message.get("body", b"") or b""
            received += len(chunk)
            if received > limit:
                raise BodySizeExceeded(received=received, limit=limit)
        return message

    return limited_receive

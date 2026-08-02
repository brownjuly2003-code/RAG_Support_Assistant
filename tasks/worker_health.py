"""Exact-node health probe for the local Celery ingestion worker.

Used by Docker Compose healthchecks and Helm readiness/liveness probes.
Pings only ``ingest@<hostname>``; never prints URLs, credentials, or
exception strings. Performs no broker/network work at import time.
"""
from __future__ import annotations

import socket
from typing import Any, Protocol


class _CeleryControl(Protocol):
    def ping(
        self,
        destination: list[str] | None = None,
        timeout: float = 1.0,
    ) -> Any: ...


class _CeleryApp(Protocol):
    control: _CeleryControl


def expected_node_name(hostname: str | None = None) -> str:
    """Return the Celery node name this probe addresses.

    Matches Celery ``--hostname=ingest@%h``: Celery expands ``%h`` with
    ``socket.gethostname()`` (see ``celery.utils.nodenames.host_format``), so
    the exact-destination ping targets the same identity inside Linux
    containers whether the hostname is short or FQDN.
    """
    host = hostname if hostname is not None else socket.gethostname()
    return f"ingest@{host}"


def _get_celery_app() -> _CeleryApp:
    """Lazy import so module import never touches the broker."""
    from tasks.celery_app import celery_app

    return celery_app  # type: ignore[return-value]


def _is_valid_pong(replies: Any, node: str) -> bool:
    """Accept only a list containing ``{node: {"ok": "pong"}}``."""
    if not isinstance(replies, list) or not replies:
        return False
    for item in replies:
        if not isinstance(item, dict):
            return False
        payload = item.get(node)
        if isinstance(payload, dict) and payload.get("ok") == "pong":
            return True
    return False


def check_worker(*, timeout: float = 2.0) -> int:
    """Return 0 if the local ingest worker answers with pong, else 1.

    Never emits secrets, broker URLs, or exception details to stdout/stderr.
    """
    node = expected_node_name()
    try:
        replies = _get_celery_app().control.ping(
            destination=[node],
            timeout=timeout,
        )
    except Exception:
        return 1
    if not _is_valid_pong(replies, node):
        return 1
    return 0


def main() -> None:
    """CLI entrypoint for container probes (``python -m tasks.worker_health``)."""
    code = check_worker()
    # Explicit silent exit: probes must not leak connection details.
    raise SystemExit(code)


if __name__ == "__main__":
    main()

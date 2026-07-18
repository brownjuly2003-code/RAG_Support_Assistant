"""Shared route introspection for ownership tests.

Kept in one module rather than copied per test file: the flat-vs-nested
compatibility below has to stay identical in every caller, and two copies of it
would drift the moment one of them is touched.

Background: until FastAPI 0.137 ``include_router`` rewrote child routes into
flat, prefixed copies on the app, so ownership tests could scan ``app.routes``
directly.  0.138 keeps a single wrapper object per included router instead --
it exposes neither ``path`` nor ``methods`` -- and the historical scan silently
matched nothing, failing with "Route not found" rather than reporting a real
routing change.  0.138 ships ``fastapi.routing.iter_route_contexts`` as the
supported way to walk the effective routing table; both branches here use
public API only, because reaching into the wrapper internals is what made this
brittle in the first place.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient


def iter_app_routes(app: Any) -> Iterator[tuple[str, set[str], Any]]:
    """Yield ``(effective path, methods, endpoint)`` for every route on ``app``."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # fastapi <= 0.137: routes are already flat and prefixed
        for route in app.routes:
            path = getattr(route, "path", None)
            if path is None:
                continue
            yield path, set(getattr(route, "methods", None) or ()), getattr(route, "endpoint", None)
        return

    for context in iter_route_contexts(app.routes):
        yield context.path, set(context.methods or ()), context.endpoint


def route_endpoint_module(client: TestClient, path: str, method: str) -> str:
    """Return the module defining the endpoint that serves ``method path``."""
    for route_path, methods, endpoint in iter_app_routes(client.app):
        if route_path != path or method not in methods or endpoint is None:
            continue
        while hasattr(endpoint, "__wrapped__"):
            endpoint = endpoint.__wrapped__
        return str(endpoint.__module__)

    raise AssertionError(f"Route not found: {method} {path}")

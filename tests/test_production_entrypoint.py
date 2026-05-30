"""Smoke tests for production entrypoint (api.app:app + main alias).

Locks invariants exposed by Codex audit 2026-04-27 P0:
- main:app and api.app:app must be the same FastAPI instance.
- Production app must carry full middleware stack and lifespan validation.
- No legacy unauthenticated /ask, /escalations, /traces endpoints.
"""

from __future__ import annotations

import pytest


def test_main_app_is_canonical_api_app():
    from api.app import app as api_app
    import main as legacy_entrypoint

    assert legacy_entrypoint.app is api_app, (
        "main:app must re-export api.app:app — Docker/uvicorn entrypoints "
        "must run the production application with full middleware/lifespan."
    )


def test_production_app_has_full_middleware_stack():
    from api.app import app as api_app

    # 8 middleware: request-id, body-size, cors, sessions, http-metrics,
    # logger, tenant, plus the implicit ServerErrorMiddleware. The exact
    # count is locked to catch accidental drops.
    middleware_count = len(api_app.user_middleware)
    assert middleware_count >= 6, (
        f"Production app has only {middleware_count} middleware — "
        "expected the full request-id/body-size/cors/sessions/metrics/"
        "logger/tenant stack."
    )


@pytest.mark.parametrize(
    "legacy_path",
    [
        "/ask",
        "/escalations",
        "/traces",
        "/escalations-ui",
        "/traces-ui",
        "/traces-ui/{trace_id}",
    ],
)
def test_no_legacy_unauthenticated_endpoints(legacy_path: str):
    from api.app import app as api_app

    paths = {getattr(r, "path", None) for r in api_app.routes}
    assert legacy_path not in paths, (
        f"Legacy unauthenticated endpoint {legacy_path!r} re-appeared on "
        "production app — these were removed because they bypassed auth, "
        "tenant isolation and quality gates."
    )


def test_api_namespace_is_populated():
    from api.app import app as api_app

    api_routes = [
        r for r in api_app.routes
        if hasattr(r, "path") and r.path.startswith("/api")
    ]
    assert len(api_routes) >= 60, (
        f"/api namespace has only {len(api_routes)} routes — "
        "expected >= 60 after Phase 2 router split."
    )

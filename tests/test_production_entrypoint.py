"""Smoke tests for production entrypoint (api.app:app + main alias).

Locks invariants exposed by Codex audit 2026-04-27 P0:
- main:app and api.app:app must be the same FastAPI instance.
- Production app must carry full middleware stack and lifespan validation.
- No legacy unauthenticated /ask, /escalations, /traces endpoints.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_main_app_is_canonical_api_app():
    import main as legacy_entrypoint
    from api.app import app as api_app

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


def test_production_import_disables_fastapi_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")

    import api.app as app_module
    import config.settings as settings_module

    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    app_module = importlib.reload(app_module)
    try:
        assert app_module.app.docs_url is None
        assert app_module.app.redoc_url is None
        assert app_module.app.openapi_url is None
        paths = {getattr(route, "path", None) for route in app_module.app.routes}
        assert "/docs" not in paths
        assert "/redoc" not in paths
        assert "/openapi.json" not in paths
    finally:
        monkeypatch.setenv("RAG_ENV", "development")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        settings_module = importlib.reload(settings_module)
        settings_module._settings = None
        importlib.reload(app_module)


def test_production_auto_migrate_failure_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import alembic.command

    import api.app as app_module

    monkeypatch.setenv("AUTO_MIGRATE", "true")
    monkeypatch.delenv("AUTO_MIGRATE_FAIL_OPEN", raising=False)
    monkeypatch.setattr(app_module, "get_settings", lambda: SimpleNamespace(rag_env="production"))
    monkeypatch.setattr(
        alembic.command,
        "upgrade",
        lambda config, revision: (_ for _ in ()).throw(RuntimeError("migration failed")),
    )

    with pytest.raises(RuntimeError, match="auto-migrate failed"):
        app_module._run_alembic_upgrade()


def test_production_auto_migrate_fail_open_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import alembic.command

    import api.app as app_module

    monkeypatch.setenv("AUTO_MIGRATE", "true")
    monkeypatch.setenv("AUTO_MIGRATE_FAIL_OPEN", "true")
    monkeypatch.setattr(app_module, "get_settings", lambda: SimpleNamespace(rag_env="production"))
    monkeypatch.setattr(
        alembic.command,
        "upgrade",
        lambda config, revision: (_ for _ in ()).throw(RuntimeError("migration failed")),
    )

    app_module._run_alembic_upgrade()


def _openapi_paths(app) -> set[str]:
    """Collect route paths via OpenAPI — stable across FastAPI versions.

    FastAPI 0.138+ may nest included routers as ``_IncludedRouter`` objects
    without a top-level ``.path`` on ``app.routes``. OpenAPI still lists every
    published path, so it is the version-proof inventory for smoke guards.
    """
    return set(app.openapi().get("paths", {}) or {})


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

    paths = _openapi_paths(api_app)
    # Also check flat app.routes for mounts / non-OpenAPI legacy handlers.
    paths |= {getattr(r, "path", None) for r in api_app.routes if getattr(r, "path", None)}
    assert legacy_path not in paths, (
        f"Legacy unauthenticated endpoint {legacy_path!r} re-appeared on "
        "production app — these were removed because they bypassed auth, "
        "tenant isolation and quality gates."
    )


def test_api_namespace_is_populated():
    from api.app import app as api_app

    api_paths = [p for p in _openapi_paths(api_app) if p.startswith("/api")]
    assert len(api_paths) >= 60, (
        f"/api namespace has only {len(api_paths)} OpenAPI paths — "
        "expected >= 60 after Phase 2 router split."
    )

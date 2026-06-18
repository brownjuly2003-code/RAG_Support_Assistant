"""Entry point alias for `python main.py` and legacy `uvicorn main:app`.

Re-exports the production FastAPI application from `api.app`.
All previous PoC handlers (`/ask`, `/escalations`, `/traces`, UI endpoints)
have been removed — they bypassed authentication, tenant isolation and
quality gates. The supported entrypoint is `api.app:app`.
"""

from __future__ import annotations

from api.app import app  # noqa: F401  re-exported as `main:app` for backwards compat


def _reload_enabled() -> bool:
    """Auto-reload is opt-in via ``UVICORN_RELOAD`` (default off).

    The previous hardcoded ``reload=True`` made any write under ``data/``/``demo/``
    flap the API mid-run — harmless for local dev, but a footgun for headless
    ingest/eval runs that write to those dirs. Default off is headless-safe;
    set ``UVICORN_RELOAD=true`` to restore the dev autoreload loop.
    """
    import os

    return os.getenv("UVICORN_RELOAD", "false").strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.app:app", host=host, port=port, reload=_reload_enabled())

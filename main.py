"""Entry point alias for `python main.py` and legacy `uvicorn main:app`.

Re-exports the production FastAPI application from `api.app`.
All previous PoC handlers (`/ask`, `/escalations`, `/traces`, UI endpoints)
have been removed — they bypassed authentication, tenant isolation and
quality gates. The supported entrypoint is `api.app:app`.
"""

from __future__ import annotations

from api.app import app  # noqa: F401  re-exported as `main:app` for backwards compat

if __name__ == "__main__":
    import os

    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.app:app", host=host, port=port, reload=True)

"""FastAPI dependencies for authentication."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def get_current_user(request: Request, settings: object | None = None) -> dict:
    """Authenticate via Bearer JWT or legacy X-API-Key."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from auth.jwt_handler import verify_token

        token = auth_header[7:]
        payload = verify_token(token, expected_type="access")
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return {
            "sub": payload["sub"],
            "role": payload.get("role", "viewer"),
            "tenant": payload.get("tenant", "default"),
        }

    if settings is None:
        settings = getattr(getattr(request.app, "state", None), "settings", None)
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()
    expected = getattr(settings, "api_key", "")
    if not expected:
        return {"sub": "anonymous", "role": "admin", "tenant": "default"}

    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="Authorization required")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return {"sub": "api-key-user", "role": "admin", "tenant": "default"}


def require_role(*roles: str):
    """Dependency factory - require specific role(s)."""

    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{user['role']}' not authorized")
        return user

    return dependency

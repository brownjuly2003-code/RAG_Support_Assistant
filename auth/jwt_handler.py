"""JWT token creation and verification."""
from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production!")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = int(os.getenv("JWT_ACCESS_TTL", "3600"))
REFRESH_TOKEN_TTL = int(os.getenv("JWT_REFRESH_TTL", "604800"))
# Plan §8.1: short-lived widget bootstrap tokens (default 15 min).
WIDGET_TOKEN_TTL = int(os.getenv("WIDGET_TOKEN_TTL_SEC", "900"))
WIDGET_TOKEN_AUD = "widget"


def create_access_token(
    user_id: str,
    role: str = "viewer",
    tenant: str = "default",
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "tenant": tenant,
        "exp": int(time.time()) + ACCESS_TOKEN_TTL,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: str,
    role: str = "viewer",
    tenant: str = "default",
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "tenant": tenant,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_widget_token(
    *,
    tenant: str = "default",
    origin: str,
    session_id: str | None = None,
    ttl_sec: int | None = None,
) -> str:
    """Short-lived audience-scoped token for embeddable widget (plan §8.1)."""
    ttl = int(ttl_sec) if ttl_sec is not None else WIDGET_TOKEN_TTL
    ttl = max(60, min(ttl, 3600))
    sid = (session_id or "").strip() or str(uuid.uuid4())
    now = int(time.time())
    payload = {
        "sub": f"widget:{tenant}",
        "role": "widget",
        "tenant": tenant,
        "aud": WIDGET_TOKEN_AUD,
        "origin": origin,
        "sid": sid,
        "exp": now + ttl,
        "iat": now,
        "type": "widget",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> Optional[dict]:
    """Verify and decode JWT. Returns payload dict or None."""
    try:
        decode_kwargs: dict = {"algorithms": [JWT_ALGORITHM]}
        # PyJWT requires ``audience`` when the token carries ``aud``.
        if expected_type == "widget":
            decode_kwargs["audience"] = WIDGET_TOKEN_AUD
        payload = jwt.decode(token, JWT_SECRET, **decode_kwargs)
        if payload.get("type") != expected_type:
            return None
        if expected_type == "widget" and payload.get("aud") != WIDGET_TOKEN_AUD:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

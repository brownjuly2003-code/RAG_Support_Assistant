"""JWT token creation and verification."""
from __future__ import annotations

import os
import time
from typing import Optional

import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production!")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = int(os.getenv("JWT_ACCESS_TTL", "3600"))
REFRESH_TOKEN_TTL = int(os.getenv("JWT_REFRESH_TTL", "604800"))


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


def verify_token(token: str, expected_type: str = "access") -> Optional[dict]:
    """Verify and decode JWT. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

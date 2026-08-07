"""Embeddable widget bootstrap (plan §8.1)."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth.jwt_handler import create_widget_token
from config.settings import get_settings

router = APIRouter(tags=["widget"])


class WidgetBootstrapRequest(BaseModel):
    parent_origin: str = Field(..., min_length=1, max_length=512)
    tenant_id: str = Field(default="default", max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    handshake_nonce: str | None = Field(default=None, max_length=128)


class WidgetBootstrapResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int
    session_id: str
    tenant_id: str
    parent_origin: str
    handshake_nonce: str | None = None


def normalize_origin(value: str) -> str:
    """Return scheme://host[:port] or raise ValueError."""
    raw = (value or "").strip()
    if not raw or raw == "null":
        raise ValueError("origin required")
    if raw == "*":
        raise ValueError("wildcard origin not allowed for bootstrap")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid origin")
    # Drop path/query/fragment — origin only.
    return f"{parsed.scheme}://{parsed.netloc}"


def origin_allowed(origin: str, allowed: list[str]) -> bool:
    if not allowed:
        return False
    if "*" in allowed:
        # Explicit opt-in wildcard (dev only); still reject empty.
        return True
    normalized_allowed = set()
    for item in allowed:
        try:
            normalized_allowed.add(normalize_origin(item))
        except ValueError:
            continue
    try:
        return normalize_origin(origin) in normalized_allowed
    except ValueError:
        return False


def frame_ancestors_csp(allowed: list[str]) -> str:
    """Build CSP frame-ancestors directive for widget HTML."""
    if not allowed:
        return "frame-ancestors 'none'"
    if "*" in allowed:
        return "frame-ancestors *"
    parts: list[str] = []
    for item in allowed:
        try:
            parts.append(normalize_origin(item))
        except ValueError:
            continue
    if not parts:
        return "frame-ancestors 'none'"
    return "frame-ancestors " + " ".join(parts)


@router.post("/widget/bootstrap", response_model=WidgetBootstrapResponse)
def widget_bootstrap(
    body: WidgetBootstrapRequest,
    request: Request,
) -> WidgetBootstrapResponse:
    """Issue a short-lived audience-scoped widget token for an allowed origin.

    Fail-closed when ``WIDGET_ALLOWED_ORIGINS`` is empty. Token is scoped to
    ``aud=widget`` + parent origin and reuses/creates ``session_id``.
    """
    settings = get_settings()
    allowed = list(getattr(settings, "widget_allowed_origins", None) or [])
    try:
        parent_origin = normalize_origin(body.parent_origin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid parent_origin: {exc}") from exc

    # Prefer explicit body origin; optionally cross-check Origin/Referer headers.
    header_origin = (request.headers.get("origin") or "").strip()
    if header_origin and header_origin != "null":
        try:
            if normalize_origin(header_origin) != parent_origin:
                raise HTTPException(
                    status_code=403,
                    detail="parent_origin does not match Origin header",
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Origin header") from exc

    if not origin_allowed(parent_origin, allowed):
        raise HTTPException(
            status_code=403,
            detail="parent origin not in WIDGET_ALLOWED_ORIGINS",
        )

    tenant = (body.tenant_id or "default").strip() or "default"
    session_id = (body.session_id or "").strip() or str(uuid4())
    ttl = int(getattr(settings, "widget_token_ttl_sec", 900) or 900)
    token = create_widget_token(
        tenant=tenant,
        origin=parent_origin,
        session_id=session_id,
        ttl_sec=ttl,
    )
    nonce = (body.handshake_nonce or "").strip() or None
    if nonce is None:
        nonce = secrets.token_urlsafe(16)

    return WidgetBootstrapResponse(
        token=token,
        expires_in=max(60, min(ttl, 3600)),
        session_id=session_id,
        tenant_id=tenant,
        parent_origin=parent_origin,
        handshake_nonce=nonce,
    )


def is_widget_static_path(path: str) -> bool:
    return path == "/static/widget.html" or path.startswith("/static/widget.")

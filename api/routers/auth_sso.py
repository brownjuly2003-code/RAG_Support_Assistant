"""SSO/OIDC endpoints — provider list, login redirect, callback.

Extracted from api.app on 2026-04-26 (Phase 2j). The handlers keep lazy access
to api.app OIDC helpers/settings so existing monkeypatch-based tests remain
effective.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from api._shared import app_module as _app_module

router = APIRouter()


@router.get("/auth/sso/providers")
async def sso_providers() -> dict[str, list[dict[str, str]]]:
    _app = _app_module()
    return {"providers": _app.list_sso_providers(_app.get_settings())}


@router.get("/auth/sso/{provider}/login")
async def sso_login(provider: str, request: Request):
    _app = _app_module()
    try:
        client = _app.get_oidc_client(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if client is None:
        raise HTTPException(status_code=404, detail="Provider not configured")

    redirect_uri = request.url_for("sso_callback", provider=provider)
    return await client.authorize_redirect(request, str(redirect_uri))


@router.get("/auth/sso/{provider}/callback", name="sso_callback")
async def sso_callback(provider: str, request: Request):
    from auth.jwt_handler import (
        ACCESS_TOKEN_TTL,
        REFRESH_TOKEN_TTL,
        create_access_token,
        create_refresh_token,
    )

    _app = _app_module()
    try:
        client = _app.get_oidc_client(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if client is None:
        raise HTTPException(status_code=404, detail="Provider not configured")

    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"SSO callback failed: {exc}")

    userinfo = token.get("userinfo") if isinstance(token, dict) else None
    if userinfo is None and hasattr(client, "userinfo"):
        userinfo = await client.userinfo(token=token)
    if not isinstance(userinfo, dict):
        raise HTTPException(status_code=400, detail="OIDC userinfo is missing")

    try:
        user = await _app.resolve_oidc_user(provider, userinfo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    access_token = create_access_token(str(user.id), user.role, user.tenant_id)
    refresh_token = create_refresh_token(str(user.id), user.role, user.tenant_id)
    secure_cookie = getattr(_app.get_settings(), "rag_env", "development") == "production"

    response = RedirectResponse("/static/chat.html", status_code=307)
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=ACCESS_TOKEN_TTL,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=REFRESH_TOKEN_TTL,
        path="/",
    )
    await _app.log_audit(
        actor=str(user.id),
        action="sso_login",
        resource=f"auth/{provider}",
        detail={"provider": provider, "tenant": user.tenant_id},
        ip_address=request.client.host if request.client else None,
    )
    return response

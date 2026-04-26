"""Miscellaneous integration/admin endpoints.

Extracted from api.app on 2026-04-27 (Phase 2m). The provider snapshot helper
stays in api.app so existing tests can keep monkeypatching app-level settings.
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.correlation import get_current_tenant
from auth.dependencies import require_role

router = APIRouter()


def _app_module():
    from api import app as _app  # noqa: PLC0415

    return _app


@router.post("/channels/email/inbound")
async def email_inbound_webhook(request: Request) -> JSONResponse:
    from channels.email_webhook import process_webhook_payload, verify_signature  # noqa: PLC0415

    settings = _app_module().get_settings()
    body = await request.body()
    signature = request.headers.get("X-Signature") or request.headers.get("X-Webhook-Signature")
    webhook_secret = (
        getattr(settings, "email_webhook_signing_secret", None)
        or getattr(settings, "email_webhook_secret", None)
    )
    if not verify_signature(body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = _json.loads(body.decode("utf-8") or "{}")
    await process_webhook_payload(payload)
    return JSONResponse(content={"ok": True})


@router.get("/admin/providers")
async def admin_list_providers(
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    _app = _app_module()
    tenant = _user.get("tenant") or get_current_tenant() or "default"
    return JSONResponse(content=_app._load_provider_admin_snapshot(tenant))

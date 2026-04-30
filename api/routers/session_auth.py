"""Auth + session management endpoints (login, refresh, list/get/delete sessions).

Extracted from api/app.py during the Step 8 thin-shell refactor. Globals
(`_db_retry_after`, `_sessions`, `_session_last_access`) still live in
api.app and are accessed via late-binding through `_app_module()`, the
same pattern conversation.py uses.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api._shared import app_module as _app_module
from api.rate_limit import limiter
from auth.dependencies import require_role
from monitoring import prometheus as prometheus_metrics

router = APIRouter()
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=4096)


class SessionInfo(BaseModel):
    session_id: str
    message_count: int


class HistoryMessage(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[HistoryMessage]
    tenant_id: str = "default"


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT tokens."""
    from auth.jwt_handler import create_access_token, create_refresh_token  # noqa: PLC0415

    _app = _app_module()
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    admin_default_tenant = os.getenv("ADMIN_DEFAULT_TENANT", "default") or "default"
    login_tenant = "default" if not admin_hash else admin_default_tenant
    client_ip = request.client.host if request.client else None

    async def _record_failure(reason: str) -> None:
        try:
            prometheus_metrics.record_auth_failure(reason)
        except Exception:
            pass
        await _app.log_audit(
            actor=body.username or "<anonymous>",
            action="login_failed",
            resource="auth",
            detail={"reason": reason, "tenant": login_tenant},
            ip_address=client_ip,
        )

    if not admin_hash:
        if body.username == "admin" and body.password == "admin":
            response = TokenResponse(
                access_token=create_access_token("admin", "admin", login_tenant),
                refresh_token=create_refresh_token("admin", "admin", login_tenant),
            )
            await _app.log_audit(
                actor=body.username,
                action="login",
                resource="auth",
                detail={"tenant": login_tenant},
                ip_address=client_ip,
            )
            return response
        await _record_failure("bad_credentials_dev")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from passlib.hash import bcrypt  # noqa: PLC0415

    if body.username != admin_user:
        await _record_failure("unknown_user")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.verify(body.password, admin_hash):
        await _record_failure("bad_password")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = TokenResponse(
        access_token=create_access_token(body.username, "admin", login_tenant),
        refresh_token=create_refresh_token(body.username, "admin", login_tenant),
    )
    await _app.log_audit(
        actor=body.username,
        action="login",
        resource="auth",
        detail={"tenant": login_tenant},
        ip_address=client_ip,
    )
    return response


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest) -> TokenResponse:
    """Refresh access token."""
    from auth.jwt_handler import create_access_token, create_refresh_token, verify_token  # noqa: PLC0415

    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return TokenResponse(
        access_token=create_access_token(
            payload["sub"],
            payload.get("role", "viewer"),
            payload.get("tenant", "default"),
        ),
        refresh_token=create_refresh_token(
            payload["sub"],
            payload.get("role", "viewer"),
            payload.get("tenant", "default"),
        ),
    )


def _try_parse_uuid(session_id: str) -> uuid.UUID | None:
    """Return UUID if parseable, else None.

    Skipping the DB query for non-UUID ids keeps invalid input from poisoning
    the 60s `_db_retry_after` cooldown (a ValueError inside the SQLAlchemy
    expression would otherwise be swallowed by the outer except and disable
    DB lookups for everyone). In-memory sessions still resolve via string
    keys, so we fall through and let the caller answer 404.
    """
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return None


@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> HistoryResponse:
    _app = _app_module()
    user_tenant = (_user.get("tenant") or "default") or "default"
    session_uuid = _try_parse_uuid(session_id)
    if session_uuid is not None and time.monotonic() >= _app._db_retry_after:
        try:
            from sqlalchemy import select  # noqa: PLC0415

            from db.engine import async_session  # noqa: PLC0415
            from db.models import Message, Session as DBSession  # noqa: PLC0415

            async with async_session() as db:
                # Tenant isolation: messages must belong to a session
                # whose tenant matches the caller (Codex audit P0).
                result = await asyncio.wait_for(
                    db.execute(
                        select(Message)
                        .join(DBSession, DBSession.id == Message.session_id)
                        .where(Message.session_id == session_uuid)
                        .where(DBSession.tenant_id == user_tenant)
                        .order_by(Message.created_at)
                    ),
                    timeout=0.5,
                )
                messages = [
                    HistoryMessage(role=message.role, content=message.content)
                    for message in result.scalars()
                ]
                _app._db_retry_after = 0.0
                if messages:
                    return HistoryResponse(session_id=session_id, messages=messages)
        except Exception as exc:
            _app._db_retry_after = time.monotonic() + 60.0
            logger.warning("DB history fallback: %s", exc)

    if session_id in _app._sessions:
        session = _app._sessions[session_id]
        session_tenant = None
        if hasattr(session, "_tenant_id"):
            session_tenant = getattr(session, "_tenant_id")
        elif isinstance(session, dict):
            session_tenant = session.get("tenant_id") or session.get("_tenant_id")
        if session_tenant is not None and session_tenant != user_tenant:
            raise HTTPException(status_code=404, detail="Session not found")

        if hasattr(session, "history"):
            history = session.history
        elif isinstance(session, dict):
            history = session.get("history", [])
        else:
            history = []

        messages = [
            HistoryMessage(role=msg.get("role", ""), content=msg.get("content", ""))
            for msg in history
        ]
        if messages:
            return HistoryResponse(session_id=session_id, messages=messages)

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    _user: dict = Depends(require_role("agent", "admin")),
) -> list[SessionInfo]:
    _app = _app_module()
    user_tenant = (_user.get("tenant") or "default") or "default"
    result: dict[str, SessionInfo] = {}

    if time.monotonic() >= _app._db_retry_after:
        try:
            from sqlalchemy import func, select  # noqa: PLC0415

            from db.engine import async_session  # noqa: PLC0415
            from db.models import Message, Session as DBSession  # noqa: PLC0415

            async with async_session() as db:
                db_result = await asyncio.wait_for(
                    db.execute(
                        select(DBSession.id, func.count(Message.id))
                        .outerjoin(Message, Message.session_id == DBSession.id)
                        .where(DBSession.tenant_id == user_tenant)
                        .group_by(DBSession.id)
                        .order_by(DBSession.last_access.desc())
                    ),
                    timeout=0.5,
                )
                for session_uuid, message_count in db_result.all():
                    result[session_uuid.hex] = SessionInfo(
                        session_id=session_uuid.hex,
                        message_count=message_count,
                    )
                _app._db_retry_after = 0.0
        except Exception as exc:
            _app._db_retry_after = time.monotonic() + 60.0
            logger.warning("DB sessions fallback: %s", exc)

    for sid, session in list(_app._sessions.items()):
        session_tenant = None
        if hasattr(session, "_tenant_id"):
            session_tenant = getattr(session, "_tenant_id")
        elif isinstance(session, dict):
            session_tenant = session.get("tenant_id") or session.get("_tenant_id")
        if session_tenant is not None and session_tenant != user_tenant:
            continue

        if hasattr(session, "_history"):
            count = len(session._history)
        elif hasattr(session, "history"):
            count = len(session.history)
        elif isinstance(session, dict):
            count = len(session.get("history", []))
        else:
            count = 0
        if sid not in result:
            result[sid] = SessionInfo(session_id=sid, message_count=count)
    return list(result.values())


@router.delete("/sessions/{session_id}")
async def clear_session(
    request: Request,
    session_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> Dict[str, str]:
    _app = _app_module()
    user_tenant = (_user.get("tenant") or "default") or "default"
    session_uuid = _try_parse_uuid(session_id)
    found = False

    if session_id in _app._sessions:
        session = _app._sessions[session_id]
        session_tenant = None
        if hasattr(session, "_tenant_id"):
            session_tenant = getattr(session, "_tenant_id")
        elif isinstance(session, dict):
            session_tenant = session.get("tenant_id") or session.get("_tenant_id")
        # Tenant isolation: in-memory session must belong to caller's tenant.
        if session_tenant is None or session_tenant == user_tenant:
            if hasattr(session, "clear"):
                session.clear()
            del _app._sessions[session_id]
            _app._session_last_access.pop(session_id, None)
            found = True

    if session_uuid is not None and time.monotonic() >= _app._db_retry_after:
        try:
            from sqlalchemy import select  # noqa: PLC0415

            from db.engine import async_session  # noqa: PLC0415
            from db.models import Session as DBSession  # noqa: PLC0415

            async with async_session() as db:
                db_result = await asyncio.wait_for(
                    db.execute(
                        select(DBSession)
                        .where(DBSession.id == session_uuid)
                        .where(DBSession.tenant_id == user_tenant)
                    ),
                    timeout=0.5,
                )
                db_session = db_result.scalar_one_or_none()
                if db_session is not None:
                    await db.delete(db_session)
                    await asyncio.wait_for(db.commit(), timeout=0.5)
                    found = True
                _app._db_retry_after = 0.0
        except Exception as exc:
            _app._db_retry_after = time.monotonic() + 60.0
            logger.warning("DB clear session fallback: %s", exc)

    if not found:
        raise HTTPException(status_code=404, detail="Session not found")

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="delete_session",
        resource=f"session:{session_id}",
        detail={"tenant": _user.get("tenant", "default")},
        ip_address=request.client.host if request.client else None,
    )
    return {"status": "ok", "message": f"Session {session_id} cleared"}

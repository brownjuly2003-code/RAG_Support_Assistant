"""§8.3 OIDC identity binding: email_verified, (issuer, subject), no rebind."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "tenant_email_domains": "acme.com:tenant-acme,*:default",
        "azure_oidc_tenant": "tenant-123",
        "google_oidc_client_id": "g-id",
        "azure_oidc_client_id": "a-id",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_email_verified_required_helpers() -> None:
    from auth.oidc import email_is_verified, require_email_verified

    assert email_is_verified({"email_verified": True}) is True
    assert email_is_verified({"email_verified": "true"}) is True
    assert email_is_verified({"email_verified": False}) is False
    assert email_is_verified({}) is False
    assert email_is_verified({"email_verified": "false"}) is False

    with pytest.raises(ValueError, match="not verified"):
        require_email_verified({"email": "a@acme.com", "email_verified": False})

    with pytest.raises(ValueError, match="not verified"):
        require_email_verified({"email": "a@acme.com"})


def test_resolve_issuer_prefers_iss_claim_and_defaults() -> None:
    from auth.oidc import resolve_oidc_issuer

    settings = _settings()
    assert (
        resolve_oidc_issuer(
            "google",
            {"iss": "https://accounts.google.com"},
            settings,
        )
        == "https://accounts.google.com"
    )
    assert (
        resolve_oidc_issuer("google", {}, settings)
        == "https://accounts.google.com"
    )
    assert resolve_oidc_issuer("azure", {}, settings) == (
        "https://login.microsoftonline.com/tenant-123/v2.0"
    )


def test_resolve_issuer_rejects_iss_mismatch() -> None:
    from auth.oidc import resolve_oidc_issuer

    settings = _settings()
    with pytest.raises(ValueError, match="issuer"):
        resolve_oidc_issuer(
            "google",
            {"iss": "https://evil.example/"},
            settings,
        )


def test_tenant_mapping_supports_wildcard_fallback() -> None:
    from auth.oidc import match_tenant_from_email_domains, resolve_tenant_from_email

    mapping = "acme.com:tenant-acme,*:catchall"
    assert match_tenant_from_email_domains("alex@acme.com", mapping) == "tenant-acme"
    assert match_tenant_from_email_domains("bob@other.org", mapping) == "catchall"
    assert match_tenant_from_email_domains("bob@other.org", "acme.com:tenant-acme") is None

    assert resolve_tenant_from_email("bob@other.org", mapping) == "catchall"
    with pytest.raises(ValueError):
        resolve_tenant_from_email("bob@other.org", "acme.com:tenant-acme")


def test_email_channel_uses_shared_tenant_mapping() -> None:
    from channels.email_channel import resolve_tenant_by_email

    assert (
        resolve_tenant_by_email(
            "Alex <alex@acme.com>",
            "acme.com:tenant-acme,*:default",
        )
        == "tenant-acme"
    )
    assert (
        resolve_tenant_by_email(
            "nobody@unknown.test",
            "acme.com:tenant-acme,*:shared",
        )
        == "shared"
    )
    # No mapping and no wildcard → legacy default tenant (email path only).
    assert resolve_tenant_by_email("nobody@unknown.test", "") == "default"


@pytest.fixture
def users_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Temporary SQLite users table for resolve_oidc_user integration."""
    from db.models import User

    db_path = tmp_path / "oidc_users.sqlite"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    async_engine = create_async_engine(async_url, echo=False)

    async def _create() -> None:
        async with async_engine.begin() as conn:
            await conn.run_sync(User.__table__.create, checkfirst=True)

    asyncio.run(_create())
    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr("db.engine.async_session", factory)
    monkeypatch.setattr("auth.oidc.async_session", factory)

    yield {"async_session": factory, "db_path": db_path}

    async def _dispose() -> None:
        await async_engine.dispose()

    asyncio.run(_dispose())


@pytest.mark.asyncio
async def test_resolve_oidc_user_rejects_unverified_email(users_db) -> None:
    from auth.oidc import resolve_oidc_user

    with pytest.raises(ValueError, match="not verified"):
        await resolve_oidc_user(
            "google",
            {
                "sub": "sub-1",
                "email": "alex@acme.com",
                "email_verified": False,
            },
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_resolve_oidc_user_creates_with_issuer_subject(users_db) -> None:
    from auth.oidc import resolve_oidc_user
    from db.models import User

    user = await resolve_oidc_user(
        "google",
        {
            "sub": "google-sub-1",
            "email": "alex@acme.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
        },
        settings=_settings(),
    )

    assert user.username == "alex@acme.com"
    assert user.tenant_id == "tenant-acme"
    # Identity is (issuer, subject), not short provider name.
    assert user.sso_provider == "https://accounts.google.com"
    assert user.sso_subject_id == "google-sub-1"

    async with users_db["async_session"]() as db:
        rows = list((await db.execute(select(User))).scalars().all())
    assert len(rows) == 1
    assert rows[0].sso_provider == "https://accounts.google.com"


@pytest.mark.asyncio
async def test_resolve_oidc_user_reuses_issuer_subject(users_db) -> None:
    from auth.oidc import resolve_oidc_user

    first = await resolve_oidc_user(
        "google",
        {
            "sub": "same-sub",
            "email": "alex@acme.com",
            "email_verified": True,
        },
        settings=_settings(),
    )
    second = await resolve_oidc_user(
        "google",
        {
            "sub": "same-sub",
            "email": "alex@acme.com",
            "email_verified": True,
        },
        settings=_settings(),
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_resolve_oidc_user_links_unbound_local_user(users_db) -> None:
    from auth.oidc import resolve_oidc_user
    from db.models import User

    async with users_db["async_session"]() as db:
        local = User(
            id=uuid.uuid4(),
            username="alex@acme.com",
            password_hash="hashed",
            role="agent",
            tenant_id="tenant-acme",
            sso_provider=None,
            sso_subject_id=None,
        )
        db.add(local)
        await db.commit()
        local_id = local.id

    linked = await resolve_oidc_user(
        "google",
        {
            "sub": "link-sub",
            "email": "alex@acme.com",
            "email_verified": True,
        },
        settings=_settings(),
    )
    assert linked.id == local_id
    assert linked.sso_provider == "https://accounts.google.com"
    assert linked.sso_subject_id == "link-sub"
    assert linked.role == "agent"


@pytest.mark.asyncio
async def test_resolve_oidc_user_refuses_rebind_different_identity(users_db) -> None:
    from auth.oidc import resolve_oidc_user
    from db.models import User

    async with users_db["async_session"]() as db:
        bound = User(
            id=uuid.uuid4(),
            username="alex@acme.com",
            password_hash="!",
            role="viewer",
            tenant_id="tenant-acme",
            sso_provider="https://accounts.google.com",
            sso_subject_id="original-sub",
        )
        db.add(bound)
        await db.commit()

    with pytest.raises(ValueError, match="already linked"):
        await resolve_oidc_user(
            "google",
            {
                "sub": "attacker-sub",
                "email": "alex@acme.com",
                "email_verified": True,
            },
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_resolve_oidc_user_refuses_without_email_verified_on_link(
    users_db,
) -> None:
    from auth.oidc import resolve_oidc_user
    from db.models import User

    async with users_db["async_session"]() as db:
        db.add(
            User(
                id=uuid.uuid4(),
                username="alex@acme.com",
                password_hash="hashed",
                role="viewer",
                tenant_id="tenant-acme",
            )
        )
        await db.commit()

    with pytest.raises(ValueError, match="not verified"):
        await resolve_oidc_user(
            "google",
            {
                "sub": "new-sub",
                "email": "alex@acme.com",
                # missing email_verified
            },
            settings=_settings(),
        )

"""OIDC provider registry and SSO user resolution."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from config.settings import get_settings
from db.engine import async_session
from db.models import User

try:
    from authlib.integrations.starlette_client import OAuth
except ImportError:  # pragma: no cover - exercised only when dependency missing
    OAuth = None


def _secret_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        revealed = value.get_secret_value()
        return str(revealed) if revealed is not None else None
    text = str(value).strip()
    return text or None


def resolve_tenant_from_email(email: str, tenant_email_domains: str) -> str:
    if "@" not in email:
        raise ValueError("email is required for SSO tenant mapping")

    domain = email.rsplit("@", 1)[1].strip().lower()
    for item in tenant_email_domains.split(","):
        raw_item = item.strip()
        if not raw_item:
            continue
        raw_domain, separator, raw_tenant = raw_item.partition(":")
        mapped_domain = raw_domain.strip().lower()
        mapped_tenant = raw_tenant.strip()
        if separator and mapped_domain == domain and mapped_tenant:
            return mapped_tenant

    raise ValueError(f"No tenant mapping configured for email domain '{domain}'")


def list_sso_providers(settings: Any | None = None) -> list[dict[str, str]]:
    settings = settings or get_settings()
    providers: list[dict[str, str]] = []

    if getattr(settings, "google_oidc_client_id", None) and _secret_value(
        getattr(settings, "google_oidc_client_secret", None)
    ):
        providers.append({"name": "google", "label": "Google"})

    if (
        getattr(settings, "azure_oidc_tenant", None)
        and getattr(settings, "azure_oidc_client_id", None)
        and _secret_value(getattr(settings, "azure_oidc_client_secret", None))
    ):
        providers.append({"name": "azure", "label": "Microsoft"})

    return providers


def get_oauth_client(provider: str, settings: Any | None = None) -> Any:
    settings = settings or get_settings()
    if OAuth is None:
        raise RuntimeError("authlib is not installed")

    oauth = OAuth()
    google_secret = _secret_value(getattr(settings, "google_oidc_client_secret", None))
    azure_secret = _secret_value(getattr(settings, "azure_oidc_client_secret", None))

    if getattr(settings, "google_oidc_client_id", None) and google_secret:
        oauth.register(
            name="google",
            client_id=settings.google_oidc_client_id,
            client_secret=google_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    if (
        getattr(settings, "azure_oidc_tenant", None)
        and getattr(settings, "azure_oidc_client_id", None)
        and azure_secret
    ):
        oauth.register(
            name="azure",
            client_id=settings.azure_oidc_client_id,
            client_secret=azure_secret,
            server_metadata_url=(
                "https://login.microsoftonline.com/"
                f"{settings.azure_oidc_tenant}/v2.0/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

    return oauth.create_client(provider)


async def resolve_oidc_user(provider: str, userinfo: dict[str, Any], settings: Any | None = None) -> User:
    settings = settings or get_settings()
    subject = str(userinfo.get("sub") or "").strip()
    email = str(userinfo.get("email") or "").strip().lower()
    if not subject:
        raise ValueError("OIDC subject is missing")
    if not email:
        raise ValueError("OIDC email is missing")

    tenant_id = resolve_tenant_from_email(
        email,
        getattr(settings, "tenant_email_domains", ""),
    )

    async with async_session() as db:
        user = (
            await db.execute(
                select(User).where(
                    User.sso_provider == provider,
                    User.sso_subject_id == subject,
                )
            )
        ).scalar_one_or_none()

        if user is None:
            user = (
                await db.execute(
                    select(User).where(User.username == email)
                )
            ).scalar_one_or_none()

            if user is None:
                user = User(
                    username=email,
                    password_hash="!",
                    role="viewer",
                    tenant_id=tenant_id,
                    sso_provider=provider,
                    sso_subject_id=subject,
                )
                db.add(user)
            else:
                user.tenant_id = getattr(user, "tenant_id", tenant_id) or tenant_id
                user.sso_provider = provider
                user.sso_subject_id = subject

        await db.commit()
        await db.refresh(user)
        return user

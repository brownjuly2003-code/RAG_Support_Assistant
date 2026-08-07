"""OIDC provider registry and SSO user resolution."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from config.settings import get_settings
from db.engine import async_session
from db.models import User

# Stable issuer defaults when userinfo omits `iss` (still bound as identity key).
_GOOGLE_ISSUER = "https://accounts.google.com"


def _secret_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        revealed = value.get_secret_value()
        return str(revealed) if revealed is not None else None
    text = str(value).strip()
    return text or None


def match_tenant_from_email_domains(email: str, tenant_email_domains: str) -> str | None:
    """Map email domain → tenant_id.

    Supports exact domain keys and a single wildcard ``*:tenant`` fallback
    (same semantics as the email channel). Returns ``None`` when nothing matches.
    """
    if "@" not in email:
        return None

    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain:
        return None

    fallback: str | None = None
    for item in (tenant_email_domains or "").split(","):
        raw_item = item.strip()
        if not raw_item:
            continue
        raw_domain, separator, raw_tenant = raw_item.partition(":")
        mapped_domain = raw_domain.strip().lower()
        mapped_tenant = raw_tenant.strip()
        if not separator or not mapped_tenant:
            continue
        if mapped_domain == "*":
            fallback = mapped_tenant
            continue
        if mapped_domain == domain:
            return mapped_tenant
    return fallback


def resolve_tenant_from_email(email: str, tenant_email_domains: str) -> str:
    """OIDC tenant mapping: fail closed when domain has no configured tenant."""
    if "@" not in email:
        raise ValueError("email is required for SSO tenant mapping")

    tenant = match_tenant_from_email_domains(email, tenant_email_domains)
    if tenant is None:
        domain = email.rsplit("@", 1)[1].strip().lower()
        raise ValueError(f"No tenant mapping configured for email domain '{domain}'")
    return tenant


def email_is_verified(userinfo: dict[str, Any]) -> bool:
    """Return True only when the IdP explicitly asserts a verified email."""
    raw = userinfo.get("email_verified")
    if raw is True or raw == 1:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes"}:
        return True
    return False


def require_email_verified(userinfo: dict[str, Any]) -> None:
    if not email_is_verified(userinfo):
        raise ValueError("OIDC email is not verified")


def default_issuer_for_provider(provider: str, settings: Any | None = None) -> str:
    """Canonical issuer URL for a configured provider short-name."""
    settings = settings or get_settings()
    name = (provider or "").strip().lower()
    if name == "google":
        return _GOOGLE_ISSUER
    if name == "azure":
        tenant = str(getattr(settings, "azure_oidc_tenant", None) or "").strip()
        if not tenant:
            raise ValueError("Azure OIDC tenant is not configured")
        return f"https://login.microsoftonline.com/{tenant}/v2.0"
    raise ValueError(f"Unknown OIDC provider '{provider}'")


def resolve_oidc_issuer(
    provider: str,
    userinfo: dict[str, Any],
    settings: Any | None = None,
) -> str:
    """Resolve identity issuer: prefer `iss` claim, else provider default.

    When `iss` is present it must match the expected issuer for the selected
    provider (normalized without trailing slash).
    """
    settings = settings or get_settings()
    expected = default_issuer_for_provider(provider, settings)
    claimed = str(userinfo.get("iss") or "").strip()
    if not claimed:
        return expected

    def _norm(value: str) -> str:
        return value.rstrip("/").lower()

    if _norm(claimed) != _norm(expected):
        raise ValueError(
            f"OIDC issuer mismatch for provider '{provider}' "
            f"(got '{claimed}', expected '{expected}')"
        )
    return expected


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


def _load_oauth_class() -> Any:
    try:
        from authlib.integrations.starlette_client import OAuth
    except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
        raise RuntimeError("authlib is not installed") from exc
    return OAuth


def get_oauth_client(provider: str, settings: Any | None = None) -> Any:
    settings = settings or get_settings()
    enabled_provider_names = {
        item["name"] for item in list_sso_providers(settings)
    }
    if provider not in enabled_provider_names:
        return None

    oauth = _load_oauth_class()()
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


async def resolve_oidc_user(
    provider: str,
    userinfo: dict[str, Any],
    settings: Any | None = None,
) -> User:
    """Resolve or create a local user for an OIDC login.

    Security contract (plan §8.3 / SEC-01):
    - ``email_verified`` must be explicitly true before create/link.
    - Durable identity key is ``(issuer, subject)`` stored in
      ``(User.sso_provider, User.sso_subject_id)``.
    - Existing bound identities are never silently rebound to a different
      ``(issuer, subject)``.
    """
    settings = settings or get_settings()
    subject = str(userinfo.get("sub") or "").strip()
    email = str(userinfo.get("email") or "").strip().lower()
    if not subject:
        raise ValueError("OIDC subject is missing")
    if not email:
        raise ValueError("OIDC email is missing")

    # Fail closed before any DB write: verified email is required for linking.
    require_email_verified(userinfo)
    issuer = resolve_oidc_issuer(provider, userinfo, settings)

    tenant_id = resolve_tenant_from_email(
        email,
        getattr(settings, "tenant_email_domains", ""),
    )

    async with async_session() as db:
        # 1) Primary identity lookup: (issuer, subject).
        user = (
            await db.execute(
                select(User).where(
                    User.sso_provider == issuer,
                    User.sso_subject_id == subject,
                )
            )
        ).scalar_one_or_none()

        if user is not None:
            await db.commit()
            await db.refresh(user)
            return user

        # 2) Optional email link for unbound local accounts only.
        user = (
            await db.execute(select(User).where(User.username == email))
        ).scalar_one_or_none()

        if user is None:
            user = User(
                username=email,
                password_hash="!",
                role="viewer",
                tenant_id=tenant_id,
                sso_provider=issuer,
                sso_subject_id=subject,
            )
            db.add(user)
        else:
            existing_issuer = (user.sso_provider or "").strip() or None
            existing_subject = (user.sso_subject_id or "").strip() or None
            if existing_issuer is not None or existing_subject is not None:
                if existing_issuer != issuer or existing_subject != subject:
                    raise ValueError(
                        "OIDC identity is already linked to a different account"
                    )
                # Same identity already on the row (should be rare if primary
                # lookup missed) — return as-is.
            else:
                # First-time link of an unbound local user.
                user.tenant_id = getattr(user, "tenant_id", tenant_id) or tenant_id
                user.sso_provider = issuer
                user.sso_subject_id = subject

        await db.commit()
        await db.refresh(user)
        return user

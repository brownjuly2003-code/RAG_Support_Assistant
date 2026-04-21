# Task 112 — SSO через authlib (Google / Azure AD OIDC)

## Context
AUTH-3 из commercial-plan. JWT auth (task AUTH-1) и RBAC (AUTH-2) уже
готовы. Остался enterprise-блокер: SSO/OIDC. Enterprise-клиенты требуют
вход через корпоративный Google Workspace или Azure AD — это must-have
для tenders.

## Goal
OAuth2/OIDC flow через `authlib`:
1. User клик "Войти через Google" → redirect на Google OAuth
2. Google callback → приложение verify'ит id_token, находит/создаёт user
3. Возвращает application JWT (уже существующий формат) → дальше
   всё работает как раньше

Поддержать минимум 2 провайдера: Google, Azure AD. Добавление новых —
конфигом, без кода.

## Files to change
- `requirements.txt` — `authlib>=1.3.0`
- `auth/oidc.py` — новый: OAuth registry, callbacks, user resolution
- `api/app.py` — новые endpoints:
  - `GET /api/auth/sso/{provider}/login` — redirect в IdP
  - `GET /api/auth/sso/{provider}/callback` — verify + issue JWT
  - `GET /api/auth/sso/providers` — список enabled providers (для UI)
- `db/models.py` — расширить `User` моделью: `sso_provider`, `sso_subject_id`
  (обеспечить uniqueness на (provider, subject_id))
- `alembic/versions/007_user_sso_fields.py` — миграция
- `config/settings.py` — secrets конфиг:
  ```
  sso_providers_json: str = ""  # JSON массив {name, client_id, client_secret, issuer_url, enabled}
  ```
  или лучше:
  ```
  google_oidc_client_id: str | None = None
  google_oidc_client_secret: SecretStr | None = None
  azure_oidc_tenant: str | None = None
  azure_oidc_client_id: str | None = None
  azure_oidc_client_secret: SecretStr | None = None
  ```
- `static/login.html` — добавить кнопки "Войти через Google / Microsoft"
  (рендерятся на основе `/api/auth/sso/providers`)
- `tests/test_oidc_flow.py` — mock OIDC discovery + callback

## Implementation sketch

### auth/oidc.py
```python
from authlib.integrations.starlette_client import OAuth
from config import settings
from db import models

oauth = OAuth()

def register_providers():
    if settings.google_oidc_client_id:
        oauth.register(
            name="google",
            client_id=settings.google_oidc_client_id,
            client_secret=settings.google_oidc_client_secret.get_secret_value(),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if settings.azure_oidc_tenant:
        oauth.register(
            name="azure",
            client_id=settings.azure_oidc_client_id,
            client_secret=settings.azure_oidc_client_secret.get_secret_value(),
            server_metadata_url=f"https://login.microsoftonline.com/{settings.azure_oidc_tenant}/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

async def resolve_user(provider: str, userinfo: dict, tenant_id: str) -> User:
    """Find or create user by (provider, subject_id)."""
    subject_id = userinfo["sub"]
    email = userinfo["email"]
    # Ищем в db
    user = await session.scalar(select(User).where(
        User.sso_provider == provider,
        User.sso_subject_id == subject_id,
    ))
    if not user:
        # First login — создаём, default role=viewer (admin повысит)
        user = User(
            email=email, sso_provider=provider, sso_subject_id=subject_id,
            tenant_id=tenant_id, role="viewer",
        )
        session.add(user)
        await session.commit()
    return user
```

### api/app.py endpoints
```python
@app.get("/api/auth/sso/{provider}/login")
async def sso_login(provider: str, request: Request):
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(404, "Provider not configured")
    redirect_uri = request.url_for("sso_callback", provider=provider)
    return await client.authorize_redirect(request, redirect_uri)

@app.get("/api/auth/sso/{provider}/callback", name="sso_callback")
async def sso_callback(provider: str, request: Request):
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    userinfo = token.get("userinfo")
    user = await resolve_user(provider, userinfo, tenant_id=request.state.tenant_id)
    app_jwt = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": user.tenant_id})
    return RedirectResponse(f"/static/chat.html?token={app_jwt}")
```

## CONSTRAINTS
- Tenant assignment на first login — нужен механизм. Варианты:
  1. Email domain mapping (`@acme.com` → tenant "acme")
  2. State param в OAuth redirect содержит invited tenant
  3. Default tenant для всех — небезопасно
  Реализовать **вариант 1** (простейший). Конфиг:
  `TENANT_EMAIL_DOMAINS: str = "acme.com:tenant-acme, beta.io:tenant-beta"`
- Session state для OAuth state — используй SessionMiddleware с secure
  cookie (authlib требует)
- Первый SSO login = role "viewer" (минимум прав); admin назначает
  role вручную в БД / admin UI

## DONE WHEN
- [ ] Google OIDC: login кнопка → redirect → callback → JWT получен
- [ ] Azure AD OIDC: то же самое (mocked в тестах)
- [ ] User создаётся с правильным tenant_id по email domain mapping
- [ ] Существующий password login (если есть) продолжает работать
- [ ] `/api/auth/sso/providers` возвращает enabled provider list
- [ ] Миграция 007 прошла
- [ ] 253+ passed, ruff clean
- [ ] Commit: "SSO via authlib: Google + Azure AD OIDC (task-112)"

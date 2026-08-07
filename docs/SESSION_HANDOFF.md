# Session handoff

**Обновлено:** 2026-08-07 — **Update-98** after **8.1** @ `0bee13e`.

---

## 0. Routing

1. Actual Git  
2. `AGENT_STATE.md` **Update-98**  
3. This file + `PLAN_CLOSURE_STATUS.md`

---

## 1. Facts

| | |
|--|--|
| Latest impl | `0bee13e` — **8.1** widget bootstrap |
| Prior | `25788ee` 7.2; `94ac64e` 7.1 |
| Local complete | … + **7.1–7.2** + **8.1** |
| Production | NOT claimed |
| Next | **8.2** ASGI body / upload stream |
| WIP | none |

**Verify 8.1:** 12 focused passed; Ruff clean. Playwright E2E not run.

---

## 2. Contract 8.1 @ `0bee13e`

- `POST /api/widget/bootstrap` → short-lived JWT `type=widget`, `aud=widget`
- Env: `WIDGET_ALLOWED_ORIGINS`, `WIDGET_TOKEN_TTL_SEC` (default 900)
- Empty allowlist → 403 (fail-closed)
- `/static/widget.html`: CSP `frame-ancestors` from allowlist; no `X-Frame-Options: DENY`
- Widget JS: origin handshake, Bearer token, `session_id` reuse
- Auth accepts widget Bearer for `/api/ask`

---

## 3. Next: 8.2

ASGI received-byte limits; upload stream to temp + atomic rename.

Alternates: OIDC `email_verified`; production secret guards; Playwright widget E2E.

---

## 4. Do not

Re-select through **8.1**. No push/live/migrate without opt-in. One slice/turn.

# Task 131 — Fix email channel (task-119 follow-up)

## Goal
Сделать email-channel действительно работающим. Сейчас IMAP poller — no-op, webhook forwarding — no-op, tenant delimiter неверный (`domain=tenant` вместо `domain:tenant`).

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Follow-up на task-119 (`codex-tasks/Archive/task-119-email-channel.md`).
- Текущее состояние (из `codex-tasks/verification-report.md`):
  - `scripts/email_poller.py` / `channels/email_channel.py` — implemented, но IMAP fetch loop не делает ничего полезного (no-op).
  - `channels/email_webhook.py` — endpoint существует, но forwarding в основной pipeline (escalation / ingestion) не происходит.
  - Tenant resolution: код парсит `from_address.domain` и ищет в `TENANT_EMAIL_DOMAINS` env var. Формат env var документирован как `domain:tenant` (с двоеточием), но код парсит `domain=tenant` (с равенством). Любой real email приходит в default tenant.

## Deliverables
1. **IMAP poller** (`scripts/email_poller.py`, `channels/email_channel.py`):
   - Реальный IMAP-поток: `imaplib` или `aioimaplib`; подключение с `IMAP_HOST`/`IMAP_PORT`/`IMAP_USER`/`IMAP_PASSWORD` из settings.
   - Poll loop с interval `IMAP_POLL_INTERVAL_SEC` (default 60).
   - Для каждого unread email: распарсить (`email.message_from_bytes`), извлечь `From`, `Subject`, `Body` (plain text preferred, fallback HTML-to-text), Message-ID.
   - Записать в БД как escalation ticket (использовать существующую таблицу `escalated_tickets` из migration 004).
   - Пометить email как read (`\\Seen` flag) чтобы не обрабатывать дважды.
   - Обработать ошибки IMAP: connection lost — reconnect с backoff.
   - Метрики Prometheus: `email_poller_fetched_total`, `email_poller_errors_total`, `email_poller_last_success_timestamp_seconds`.
2. **Webhook** (`channels/email_webhook.py`):
   - POST endpoint `/webhook/email` (signed, как в task-119 spec).
   - При получении: парсить payload (SendGrid / Mailgun / SES format — выбрать один и задокументировать), создать escalation ticket аналогично IMAP.
   - Forwarding в LangGraph escalation flow: триггер `graph.ainvoke` с `channel="email"` — или записать в `escalated_tickets` с `status="pending_response"`, дальнейшая обработка — existing escalation logic.
3. **Tenant resolution**:
   - Format env var `TENANT_EMAIL_DOMAINS` — строка вида `example.com:acme,support.foo.com:foo-corp,*:default` (двоеточие-разделитель, запятая-разделитель пар, `*` как fallback).
   - Функция `resolve_tenant_by_email(email: str) -> str` парсит domain из email, ищет match, возвращает `tenant_id` или `default`.
   - Unit-тест покрывает: точный match, wildcard, unknown domain → default.
4. **Tests** (`tests/test_email_channel.py`):
   - IMAP poller mock-тест: fake IMAP server returns 2 messages → 2 tickets created → messages marked read.
   - Webhook тест: POST payload → ticket created with correct tenant_id.
   - Tenant resolution: 4+ cases из §3 выше.
   - Signature validation: invalid signature → 401.
5. **Docs**:
   - README раздел "Email channel" — как настроить IMAP / webhook, пример env vars, supported providers.

## Acceptance
- `grep -rE "domain=tenant" --include="*.py" --include="*.md" .` → 0 матчей. `grep -rE "domain:tenant" .` → найдено в env-docs с корректным синтаксисом.
- Дискретный прогон IMAP poller в dev-mode (fake IMAP via `aioimaplib` mock) — создаёт минимум 1 ticket.
- `curl -X POST /webhook/email -H "X-Signature: <valid>" -d '<payload>'` → 200 + ticket в БД.
- `curl -X POST /webhook/email -H "X-Signature: invalid" -d '<payload>'` → 401.
- `pytest tests/test_email_channel.py -v` — зелёный, минимум 6 тестов.
- ruff clean, общий `pytest tests/ -q` ≥ 293 passed.
- README содержит рабочий пример `TENANT_EMAIL_DOMAINS=acme.com:acme,*:default`.

## Notes
- **НЕ писать собственный MIME parser** — использовать stdlib `email` module.
- **НЕ поднимать реальный IMAP сервер в тестах** — mock на уровне клиента (patch `imaplib.IMAP4_SSL`).
- Secrets (IMAP_PASSWORD, webhook signing key) — только env, никогда в коде или тестах.
- `continue-on-error: true` в CI integration job — OK, тесты этого модуля могут быть в unit suite (mock-based).
- Для webhook signature: HMAC-SHA256(body, secret) в header `X-Signature`. Secret — `EMAIL_WEBHOOK_SIGNING_SECRET` env.
- Если IMAP недоступен на старте — poller должен логировать WARNING, но НЕ крашить app (graceful degradation).

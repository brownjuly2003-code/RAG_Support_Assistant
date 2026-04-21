# Task 119 — Email channel: IMAP/webhook → RAG → reply

## Context
MC-1 из commercial-plan. Telegram и Widget channels частично есть
(`channels/telegram_bot.py`, `static/widget.*`). Email отсутствует.
Email — доминирующий канал support'а в B2B (SaaS продукты типа Intercom
специально выделяют email inbox как первый-class support channel).

## Goal
Принимать incoming emails (IMAP polling или webhook через SendGrid/Postmark)
→ прогонять через RAG → отправлять reply. Эскалация: если quality низкая
→ forward в operator inbox (вместо автоматического ответа).

## Files to change
- `channels/email_channel.py` — новый: IMAP poller + send via SMTP
- `channels/email_webhook.py` — альтернатива: FastAPI endpoint для
  SendGrid/Postmark Inbound webhooks
- `config/settings.py`:
  - `EMAIL_CHANNEL_MODE: str = "disabled"` (disabled|imap|webhook)
  - `IMAP_HOST/PORT/USER/PASS`, `IMAP_FOLDER: str = "INBOX"`
  - `SMTP_HOST/PORT/USER/PASS`, `SMTP_FROM_ADDRESS`
  - `EMAIL_WEBHOOK_SECRET: SecretStr` (для верификации incoming webhooks)
- `api/app.py` — `POST /api/channels/email/inbound` (webhook receiver)
- `scripts/email_poller.py` — standalone IMAP poller (для self-hosted mode)
- `deploy/helm/templates/deployment-email-poller.yaml` (отдельный pod
  для poller — не mixать с main API)
- `tests/test_email_channel.py`

## Implementation sketch

### channels/email_channel.py (IMAP poller)
```python
import imaplib, email
from email.mime.text import MIMEText
import smtplib

async def poll_once():
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as mailbox:
        mailbox.login(settings.imap_user, settings.imap_pass.get_secret_value())
        mailbox.select(settings.imap_folder)
        _, data = mailbox.search(None, "UNSEEN")
        for num in data[0].split():
            _, msg_data = mailbox.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            await process_incoming(msg)
            mailbox.store(num, "+FLAGS", "\\Seen")

async def process_incoming(msg: email.message.Message):
    sender = msg["From"]
    subject = msg["Subject"]
    body = extract_plain_body(msg)

    # Tenant resolution: по recipient domain (support@acme.com → tenant acme)
    tenant_id = resolve_tenant_from_recipient(msg["To"])
    if not tenant_id:
        logger.warning("Could not resolve tenant for %s", msg["To"])
        return

    # Run через graph
    result = await run_graph(question=f"{subject}\n\n{body}", tenant_id=tenant_id)

    if result["quality_score"] >= settings.escalation_threshold:
        await send_reply(to=sender, subject=f"Re: {subject}", body=result["answer"])
    else:
        await forward_to_operators(sender, subject, body, result)
```

### Webhook alternative (api/app.py)
```python
@app.post("/api/channels/email/inbound")
async def email_webhook(request: Request):
    # Verify HMAC signature from SendGrid/Postmark
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    if not verify_signature(body, signature, settings.email_webhook_secret):
        raise HTTPException(401)
    payload = json.loads(body)
    # Same processing as IMAP version
    await process_incoming_from_webhook(payload)
    return {"ok": True}
```

### Tenant resolution
Reuse task-112 email-domain mapping: recipient `support@acme.com` →
tenant via env var `TENANT_EMAIL_DOMAINS`.

## CONSTRAINTS
- **`EMAIL_CHANNEL_MODE=disabled`** default — без конфига никаких побочек
- Reply-to: to-sender (не общий inbox)
- Threading: сохранять `Message-ID` / `In-Reply-To` headers для
  корректного threading в email-клиентах
- Rate limit per sender (5 emails/minute) — защита от спама
- Attachments в incoming — логируем размер, игнорируем content в MVP
  (parsing PDF/DOCX = отдельный task)
- HTML emails — extract plain text через `html2text`
- Sent emails → audit log (кто, что, когда)

## DONE WHEN
- [ ] IMAP mode: mocked mailbox → incoming email → RAG → sent reply
- [ ] Webhook mode: mocked SendGrid payload → 200 + reply sent
- [ ] Low quality → forward to operators (EscalatedTicket created)
- [ ] Tenant resolution по domain работает
- [ ] Signature verification для webhook защищает от unauthenticated
- [ ] Helm: отдельный deployment для poller (не crashит main API при IMAP down)
- [ ] 285+ passed
- [ ] Commit: "Email channel: IMAP polling + webhook mode (task-119)"

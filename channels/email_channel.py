from __future__ import annotations

import email
import imaplib
import re
import smtplib
from email.message import EmailMessage, Message
from email.utils import parseaddr
from typing import Any, Callable

from config.settings import get_settings


def extract_plain_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore")
            if content_type == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="ignore")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="ignore")


def resolve_tenant_from_recipient(recipient: str, mapping: str | None = None) -> str | None:
    _, address = parseaddr(recipient)
    domain = address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""
    if not domain:
        return None
    raw_mapping = mapping if mapping is not None else get_settings().tenant_email_domains
    for item in raw_mapping.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        mapped_domain, tenant_id = item.split("=", 1)
        if mapped_domain.strip().lower() == domain:
            return tenant_id.strip() or None
    return None


async def send_reply_smtp(to: str, subject: str, body: str, headers: dict[str, str]) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to
    message["Subject"] = subject
    for key, value in headers.items():
        if value:
            message[key] = value
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        if settings.smtp_user:
            client.starttls()
            password = settings.smtp_pass.get_secret_value() if settings.smtp_pass else ""
            client.login(settings.smtp_user, password)
        client.send_message(message)


async def process_incoming_message(
    message: Message,
    run_qa: Callable[[str, str], Any],
    send_reply: Callable[[str, str, str, dict[str, str]], Any],
    forward_message: Callable[[str, str, str, dict[str, Any]], Any],
    tenant_resolver: Callable[[str], str | None] = resolve_tenant_from_recipient,
    quality_threshold: int | None = None,
) -> dict[str, Any]:
    sender = parseaddr(message.get("From", ""))[1] or message.get("From", "")
    recipient = message.get("To", "")
    tenant_id = tenant_resolver(recipient)
    if not tenant_id:
        return {"status": "skipped", "reason": "tenant_not_found"}

    subject = str(message.get("Subject", "") or "")
    body = extract_plain_body(message).strip()
    question = "\n\n".join(part for part in (subject, body) if part).strip()
    result = await run_qa(question, tenant_id)

    threshold = quality_threshold if quality_threshold is not None else get_settings().quality_threshold
    headers = {}
    message_id = message.get("Message-ID")
    if message_id:
        headers["In-Reply-To"] = message_id
        headers["References"] = message_id

    if int(result.get("quality_score") or 0) >= threshold:
        await send_reply(sender, f"Re: {subject}".strip(), str(result.get("answer") or ""), headers)
        return {"status": "replied", "tenant_id": tenant_id}

    await forward_message(sender, subject, body, result)
    return {"status": "forwarded", "tenant_id": tenant_id}


async def poll_once(
    process_incoming: Callable[[Message], Any],
) -> int:
    settings = get_settings()
    processed = 0
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as mailbox:
        password = settings.imap_pass.get_secret_value() if settings.imap_pass else ""
        mailbox.login(settings.imap_user, password)
        mailbox.select(settings.imap_folder)
        _status, data = mailbox.search(None, "UNSEEN")
        for item in data[0].split():
            _fetch_status, msg_data = mailbox.fetch(item, "(RFC822)")
            message = email.message_from_bytes(msg_data[0][1])
            await process_incoming(message)
            mailbox.store(item, "+FLAGS", "\\Seen")
            processed += 1
    return processed

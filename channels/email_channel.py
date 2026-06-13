from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import re
import smtplib
import time
import uuid
from collections.abc import Callable
from email.message import EmailMessage, Message
from email.utils import parseaddr
from html import unescape
from typing import TYPE_CHECKING, Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


class _NoopMetric:
    def inc(self, amount: float = 1.0) -> None:
        _ = amount

    def set(self, value: float) -> None:
        _ = value


if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge

    # Bound to a real prometheus class when the dependency is present, else to
    # _NoopMetric; declare the union so mypy accepts both assignment branches.
    EMAIL_POLLER_FETCHED_TOTAL: Counter | _NoopMetric
    EMAIL_POLLER_ERRORS_TOTAL: Counter | _NoopMetric
    EMAIL_POLLER_LAST_SUCCESS_TIMESTAMP: Gauge | _NoopMetric


try:
    from prometheus_client import Counter, Gauge

    from monitoring import prometheus as prometheus_metrics
except ImportError:
    EMAIL_POLLER_FETCHED_TOTAL = _NoopMetric()
    EMAIL_POLLER_ERRORS_TOTAL = _NoopMetric()
    EMAIL_POLLER_LAST_SUCCESS_TIMESTAMP = _NoopMetric()
else:
    if getattr(prometheus_metrics, "PROMETHEUS_AVAILABLE", False) and prometheus_metrics.REGISTRY is not None:
        EMAIL_POLLER_FETCHED_TOTAL = Counter(
            "email_poller_fetched_total",
            "Total unread emails processed by the IMAP poller",
            registry=prometheus_metrics.REGISTRY,
        )
        EMAIL_POLLER_ERRORS_TOTAL = Counter(
            "email_poller_errors_total",
            "Total IMAP poller errors",
            registry=prometheus_metrics.REGISTRY,
        )
        EMAIL_POLLER_LAST_SUCCESS_TIMESTAMP = Gauge(
            "email_poller_last_success_timestamp_seconds",
            "Unix timestamp of the last successful IMAP poll cycle",
            registry=prometheus_metrics.REGISTRY,
        )
    else:
        EMAIL_POLLER_FETCHED_TOTAL = _NoopMetric()
        EMAIL_POLLER_ERRORS_TOTAL = _NoopMetric()
        EMAIL_POLLER_LAST_SUCCESS_TIMESTAMP = _NoopMetric()


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_plain_body(message: Message) -> str:
    html_fallback = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue

            raw_payload = part.get_payload(decode=True)
            payload = raw_payload if isinstance(raw_payload, bytes) else b""
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="ignore")
            content_type = part.get_content_type()

            if content_type == "text/plain" and content.strip():
                return content
            if content_type == "text/html" and content.strip() and not html_fallback:
                html_fallback = _html_to_text(content)

        return html_fallback

    raw_payload = message.get_payload(decode=True)
    payload = raw_payload if isinstance(raw_payload, bytes) else b""
    charset = message.get_content_charset() or "utf-8"
    content = payload.decode(charset, errors="ignore")
    if message.get_content_type() == "text/html":
        return _html_to_text(content)
    return content


def resolve_tenant_by_email(email_address: str, mapping: str | None = None) -> str:
    _, address = parseaddr(email_address)
    domain = address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""
    raw_mapping = mapping if mapping is not None else get_settings().tenant_email_domains
    fallback_tenant = "default"

    for item in raw_mapping.split(","):
        raw_item = item.strip()
        if not raw_item:
            continue

        mapped_domain, separator, tenant_id = raw_item.partition(":")
        normalized_domain = mapped_domain.strip().lower()
        normalized_tenant = tenant_id.strip()
        if not separator or not normalized_tenant:
            continue
        if normalized_domain == "*":
            fallback_tenant = normalized_tenant
            continue
        if normalized_domain == domain:
            return normalized_tenant

    return fallback_tenant


def resolve_tenant_from_recipient(recipient: str, mapping: str | None = None) -> str:
    return resolve_tenant_by_email(recipient, mapping)


async def persist_escalated_ticket(
    tenant_id: str,
    session_id: str,
    user_question: str,
    ai_draft: str | None,
    status: str = "pending_response",
) -> None:
    from db.engine import async_session
    from db.models import EscalatedTicket

    async with async_session() as db:
        db.add(
            EscalatedTicket(
                tenant_id=tenant_id or "default",
                session_id=session_id or uuid.uuid4().hex,
                user_question=user_question,
                ai_draft=ai_draft,
                status=status,
            )
        )
        await db.commit()


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


async def run_qa_via_app(question: str, tenant_id: str) -> dict[str, Any]:
    from api.app import _get_or_create_session

    session_result = _get_or_create_session(None, tenant_id)
    if asyncio.iscoroutine(session_result):
        session_id, session = await session_result
    else:
        session_id, session = session_result

    result = await asyncio.to_thread(session.ask, question, tenant_id=tenant_id)
    payload = dict(result or {})
    payload.setdefault("session_id", session_id)
    return payload


async def forward_to_ticket(
    sender: str,
    subject: str,
    body: str,
    result: dict[str, Any],
) -> None:
    question = "\n\n".join(part for part in (subject.strip(), body.strip()) if part).strip()
    await persist_escalated_ticket(
        tenant_id=str(result.get("tenant_id") or "default"),
        session_id=str(result.get("session_id") or result.get("message_id") or uuid.uuid4().hex),
        user_question=question or f"Email from {sender}",
        ai_draft=str(result.get("answer") or "").strip() or None,
        status="pending_response",
    )


async def process_incoming_message(
    message: Message,
    run_qa: Callable[[str, str], Any],
    send_reply: Callable[[str, str, str, dict[str, str]], Any],
    forward_message: Callable[[str, str, str, dict[str, Any]], Any] | None = None,
    tenant_resolver: Callable[[str], str] | None = None,
    quality_threshold: int | None = None,
) -> dict[str, Any]:
    sender = parseaddr(message.get("From", ""))[1] or message.get("From", "")
    resolver = tenant_resolver or resolve_tenant_by_email
    tenant_id = resolver(sender) or "default"

    subject = str(message.get("Subject", "") or "")
    body = extract_plain_body(message).strip()
    question = "\n\n".join(part for part in (subject, body) if part).strip()
    result = await run_qa(question, tenant_id)
    payload = dict(result or {})
    payload.setdefault("tenant_id", tenant_id)

    threshold = (
        quality_threshold
        if quality_threshold is not None
        else int(getattr(get_settings(), "quality_threshold", 80) or 80)
    )
    headers: dict[str, str] = {}
    message_id = message.get("Message-ID")
    if message_id:
        headers["In-Reply-To"] = message_id
        headers["References"] = message_id
        payload.setdefault("message_id", message_id)

    if int(payload.get("quality_score") or 0) >= threshold:
        await send_reply(sender, f"Re: {subject}".strip(), str(payload.get("answer") or ""), headers)
        return {"status": "replied", "tenant_id": tenant_id}

    handler = forward_message or forward_to_ticket
    await handler(sender, subject, body, payload)
    return {"status": "forwarded", "tenant_id": tenant_id}


async def process_support_email(message: Message) -> dict[str, Any]:
    return await process_incoming_message(
        message,
        run_qa=run_qa_via_app,
        send_reply=send_reply_smtp,
    )


async def poll_once(
    process_incoming: Callable[[Message], Any] | None = None,
) -> int:
    settings = get_settings()
    processor = process_incoming or process_support_email
    processed = 0

    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as mailbox:
        password = settings.imap_pass.get_secret_value() if settings.imap_pass else ""
        mailbox.login(settings.imap_user, password)
        mailbox.select(settings.imap_folder)
        status, data = mailbox.search(None, "UNSEEN")
        if status != "OK":
            raise imaplib.IMAP4.error("failed to search unread emails")

        unread_items = data[0].split() if data and data[0] else []
        for item in unread_items:
            fetch_status, msg_data = mailbox.fetch(item, "(RFC822)")
            if fetch_status != "OK" or not msg_data:
                raise imaplib.IMAP4.error(f"failed to fetch message {item!r}")

            raw_message = msg_data[0]
            if not isinstance(raw_message, tuple):
                raise imaplib.IMAP4.error(f"unexpected fetch response for {item!r}")
            message = email.message_from_bytes(raw_message[1])
            await processor(message)

            store_status, _ = mailbox.store(item, "+FLAGS", "\\Seen")
            if store_status != "OK":
                raise imaplib.IMAP4.error(f"failed to mark message {item!r} as seen")

            processed += 1

    EMAIL_POLLER_FETCHED_TOTAL.inc(processed)
    EMAIL_POLLER_LAST_SUCCESS_TIMESTAMP.set(time.time())
    return processed


async def poll_forever(
    process_incoming: Callable[[Message], Any] | None = None,
) -> None:
    backoff_seconds = 1.0
    max_backoff_seconds = 300.0

    while True:
        settings = get_settings()
        poll_interval = float(getattr(settings, "imap_poll_interval_sec", 60) or 60)
        try:
            await poll_once(process_incoming=process_incoming)
            backoff_seconds = 1.0
            await asyncio.sleep(poll_interval)
        except Exception as exc:
            EMAIL_POLLER_ERRORS_TOTAL.inc()
            logger.warning("Email poller cycle failed: %s", exc)
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)

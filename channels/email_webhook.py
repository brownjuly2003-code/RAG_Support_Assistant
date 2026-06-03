from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from email.message import EmailMessage
from email.parser import Parser
from typing import Any

from pydantic import SecretStr

from channels.email_channel import (
    process_incoming_message,
    process_support_email,
    resolve_tenant_by_email,
    run_qa_via_app,
    send_reply_smtp,
)


def verify_signature(body: bytes, signature: str | None, secret: SecretStr | str | None) -> bool:
    if secret is None:
        return False
    secret_value = secret.get_secret_value() if isinstance(secret, SecretStr) else str(secret)
    if not signature or not secret_value:
        return False
    expected = hmac.new(secret_value.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_message_id(headers: str | None) -> str | None:
    if not headers:
        return None
    parsed_headers = Parser().parsestr(headers)
    return parsed_headers.get("Message-ID") or parsed_headers.get("Message-Id")


def _build_sendgrid_message(payload: dict[str, Any]) -> EmailMessage:
    message = EmailMessage()
    message["From"] = str(payload.get("from") or "")
    message["To"] = str(payload.get("to") or "")
    message["Subject"] = str(payload.get("subject") or "")

    message_id = payload.get("message_id") or _extract_message_id(payload.get("headers"))
    if message_id:
        message["Message-ID"] = str(message_id)

    text_body = payload.get("text") or payload.get("body")
    html_body = payload.get("html")
    if text_body:
        message.set_content(str(text_body))
    elif html_body:
        message.set_content(str(html_body), subtype="html")
    else:
        message.set_content("")
    return message


async def process_webhook_payload(
    payload: dict[str, Any],
    run_qa: Callable[[str, str], Any] | None = None,
    send_reply: Callable[[str, str, str, dict[str, str]], Any] | None = None,
    forward_message: Callable[[str, str, str, dict[str, Any]], Any] | None = None,
    tenant_resolver: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    message = _build_sendgrid_message(payload)
    if (
        run_qa is None
        and send_reply is None
        and forward_message is None
        and tenant_resolver is None
    ):
        return await process_support_email(message)

    return await process_incoming_message(
        message,
        run_qa=run_qa or run_qa_via_app,
        send_reply=send_reply or send_reply_smtp,
        forward_message=forward_message,
        tenant_resolver=tenant_resolver or resolve_tenant_by_email,
    )

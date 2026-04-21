from __future__ import annotations

import hashlib
import hmac
from email.message import EmailMessage
from typing import Any, Callable

from pydantic import SecretStr

from channels.email_channel import process_incoming_message


def verify_signature(body: bytes, signature: str | None, secret: SecretStr | str | None) -> bool:
    if secret is None:
        return False
    secret_value = secret.get_secret_value() if isinstance(secret, SecretStr) else str(secret)
    if not signature or not secret_value:
        return False
    expected = hmac.new(secret_value.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def process_webhook_payload(
    payload: dict[str, Any],
    run_qa: Callable[[str, str], Any],
    send_reply: Callable[[str, str, str, dict[str, str]], Any],
    forward_message: Callable[[str, str, str, dict[str, Any]], Any],
    tenant_resolver: Callable[[str], str | None],
) -> dict[str, Any]:
    message = EmailMessage()
    message["From"] = payload.get("from", "")
    message["To"] = payload.get("to", "")
    message["Subject"] = payload.get("subject", "")
    if payload.get("message_id"):
        message["Message-ID"] = payload["message_id"]
    message.set_content(payload.get("text") or payload.get("body") or "")
    return await process_incoming_message(
        message,
        run_qa=run_qa,
        send_reply=send_reply,
        forward_message=forward_message,
        tenant_resolver=tenant_resolver,
    )

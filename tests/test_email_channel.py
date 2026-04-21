from __future__ import annotations

import asyncio
import json
from email.message import EmailMessage

import pytest
from pydantic import SecretStr


def test_process_incoming_email_replies_when_quality_is_high() -> None:
    from channels.email_channel import process_incoming_message

    message = EmailMessage()
    message["From"] = "user@example.com"
    message["To"] = "support@acme.test"
    message["Subject"] = "Need help"
    message.set_content("Where is my delivery?")

    sent: list[tuple[str, str]] = []
    forwarded: list[str] = []

    async def _fake_run(question: str, tenant_id: str) -> dict:
        assert tenant_id == "acme"
        assert "Need help" in question
        return {"answer": "Your delivery is on the way.", "quality_score": 90}

    async def _fake_send_reply(to: str, subject: str, body: str, headers: dict[str, str]) -> None:
        _ = headers
        sent.append((to, subject))
        assert body == "Your delivery is on the way."

    async def _fake_forward(sender: str, subject: str, body: str, result: dict) -> None:
        _ = body, result
        forwarded.append(f"{sender}:{subject}")

    asyncio.run(
        process_incoming_message(
            message,
            run_qa=_fake_run,
            send_reply=_fake_send_reply,
            forward_message=_fake_forward,
            tenant_resolver=lambda recipient: "acme",
        )
    )

    assert sent == [("user@example.com", "Re: Need help")]
    assert forwarded == []


def test_process_incoming_email_forwards_low_quality_messages() -> None:
    from channels.email_channel import process_incoming_message

    message = EmailMessage()
    message["From"] = "user@example.com"
    message["To"] = "support@acme.test"
    message["Subject"] = "Need help"
    message.set_content("Where is my delivery?")

    forwarded: list[str] = []

    async def _fake_run(question: str, tenant_id: str) -> dict:
        _ = question, tenant_id
        return {"answer": "I am not sure.", "quality_score": 10}

    async def _fake_send_reply(to: str, subject: str, body: str, headers: dict[str, str]) -> None:
        raise AssertionError("reply should not be sent")

    async def _fake_forward(sender: str, subject: str, body: str, result: dict) -> None:
        _ = body, result
        forwarded.append(f"{sender}:{subject}")

    asyncio.run(
        process_incoming_message(
            message,
            run_qa=_fake_run,
            send_reply=_fake_send_reply,
            forward_message=_fake_forward,
            tenant_resolver=lambda recipient: "acme",
        )
    )

    assert forwarded == ["user@example.com:Need help"]


def test_email_webhook_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.email_webhook_secret = SecretStr("super-secret")
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    response = client.post(
        "/api/channels/email/inbound",
        data=json.dumps({"from": "user@example.com", "to": "support@acme.test", "subject": "Hi", "text": "Body"}),
        headers={"X-Webhook-Signature": "invalid"},
    )

    assert response.status_code == 401

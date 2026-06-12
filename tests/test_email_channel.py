from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
from pydantic import SecretStr


@pytest.mark.parametrize(
    ("email_address", "mapping", "expected"),
    [
        ("alex@acme.com", "acme.com:acme,*:default", "acme"),
        ("agent@support.foo.com", "support.foo.com:foo-corp,*:default", "foo-corp"),
        ("unknown@other.net", "acme.com:acme,*:default", "default"),
        ("not-an-email", "acme.com:acme,*:default", "default"),
    ],
)
def test_resolve_tenant_by_email(
    email_address: str,
    mapping: str,
    expected: str,
) -> None:
    from channels.email_channel import resolve_tenant_by_email

    assert resolve_tenant_by_email(email_address, mapping) == expected


def test_process_incoming_email_replies_when_quality_is_high() -> None:
    from channels.email_channel import process_incoming_message

    message = EmailMessage()
    message["From"] = "user@acme.com"
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
            tenant_resolver=lambda sender: "acme",
        )
    )

    assert sent == [("user@acme.com", "Re: Need help")]
    assert forwarded == []


def test_process_incoming_email_forwards_low_quality_messages() -> None:
    from channels.email_channel import process_incoming_message

    message = EmailMessage()
    message["From"] = "user@acme.com"
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
            tenant_resolver=lambda sender: "acme",
        )
    )

    assert forwarded == ["user@acme.com:Need help"]


def test_poll_once_creates_tickets_for_unread_messages_and_marks_them_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import channels.email_channel as email_channel

    message_one = EmailMessage()
    message_one["From"] = "first@acme.com"
    message_one["To"] = "support@example.com"
    message_one["Subject"] = "First"
    message_one["Message-ID"] = "<first@example.com>"
    message_one.set_content("Need help with the first order")

    message_two = EmailMessage()
    message_two["From"] = "second@acme.com"
    message_two["To"] = "support@example.com"
    message_two["Subject"] = "Second"
    message_two["Message-ID"] = "<second@example.com>"
    message_two.set_content("Need help with the second order")

    tickets: list[dict[str, str]] = []

    async def _fake_run_qa(question: str, tenant_id: str) -> dict:
        return {
            "answer": f"Draft for {tenant_id}: {question}",
            "quality_score": 0,
            "session_id": f"session-{len(tickets) + 1}",
        }

    async def _fake_send_reply(to: str, subject: str, body: str, headers: dict[str, str]) -> None:
        raise AssertionError("reply should not be sent")

    async def _fake_persist_ticket(
        tenant_id: str,
        session_id: str,
        user_question: str,
        ai_draft: str | None,
        status: str,
    ) -> None:
        tickets.append(
            {
                "tenant_id": tenant_id,
                "session_id": session_id,
                "user_question": user_question,
                "ai_draft": ai_draft or "",
                "status": status,
            }
        )

    class FakeMailbox:
        def __init__(self) -> None:
            self._messages = {
                b"1": message_one.as_bytes(),
                b"2": message_two.as_bytes(),
            }
            self.seen: list[tuple[bytes, str, str]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb

        def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
            assert user == "poller@example.com"
            assert password == "imap-secret"
            return "OK", []

        def select(self, folder: str) -> tuple[str, list[bytes]]:
            assert folder == "INBOX"
            return "OK", []

        def search(self, charset, *criteria: str) -> tuple[str, list[bytes]]:
            _ = charset
            assert criteria == ("UNSEEN",)
            return "OK", [b"1 2"]

        def fetch(self, item: bytes, query: str) -> tuple[str, list[tuple[bytes, bytes]]]:
            assert query == "(RFC822)"
            return "OK", [(b"RFC822", self._messages[item])]

        def store(self, item: bytes, mode: str, flag: str) -> tuple[str, list[bytes]]:
            self.seen.append((item, mode, flag))
            return "OK", []

    mailbox = FakeMailbox()
    settings = SimpleNamespace(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="poller@example.com",
        imap_pass=SecretStr("imap-secret"),
        imap_folder="INBOX",
        tenant_email_domains="acme.com:acme,*:default",
        quality_threshold=80,
    )

    monkeypatch.setattr(email_channel, "get_settings", lambda: settings)
    monkeypatch.setattr(email_channel, "run_qa_via_app", _fake_run_qa)
    monkeypatch.setattr(email_channel, "send_reply_smtp", _fake_send_reply)
    monkeypatch.setattr(email_channel, "persist_escalated_ticket", _fake_persist_ticket)
    monkeypatch.setattr(email_channel.imaplib, "IMAP4_SSL", lambda host, port: mailbox)

    processed = asyncio.run(email_channel.poll_once())

    assert processed == 2
    assert [ticket["tenant_id"] for ticket in tickets] == ["acme", "acme"]
    assert [ticket["status"] for ticket in tickets] == ["pending_response", "pending_response"]
    assert mailbox.seen == [
        (b"1", "+FLAGS", "\\Seen"),
        (b"2", "+FLAGS", "\\Seen"),
    ]


def test_email_webhook_accepts_signed_payload_and_creates_ticket(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    import api.app as api_app
    import channels.email_channel as email_channel

    tickets: list[dict[str, str]] = []

    async def _fake_run_qa(question: str, tenant_id: str) -> dict:
        assert tenant_id == "acme"
        assert "Need help" in question
        return {
            "answer": "Escalate this",
            "quality_score": 10,
            "session_id": "email-session-1",
        }

    async def _fake_send_reply(to: str, subject: str, body: str, headers: dict[str, str]) -> None:
        raise AssertionError("reply should not be sent")

    async def _fake_persist_ticket(
        tenant_id: str,
        session_id: str,
        user_question: str,
        ai_draft: str | None,
        status: str,
    ) -> None:
        tickets.append(
            {
                "tenant_id": tenant_id,
                "session_id": session_id,
                "user_question": user_question,
                "ai_draft": ai_draft or "",
                "status": status,
            }
        )

    settings = api_app.get_settings()
    settings.email_webhook_secret = SecretStr("super-secret")
    settings.email_webhook_signing_secret = SecretStr("super-secret")
    settings.tenant_email_domains = "acme.com:acme,*:default"
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)
    monkeypatch.setattr(email_channel, "get_settings", lambda: settings)
    monkeypatch.setattr(email_channel, "run_qa_via_app", _fake_run_qa)
    monkeypatch.setattr(email_channel, "send_reply_smtp", _fake_send_reply)
    monkeypatch.setattr(email_channel, "persist_escalated_ticket", _fake_persist_ticket)

    payload = {
        "from": "customer@acme.com",
        "to": "support@example.com",
        "subject": "Need help",
        "text": "Where is my order?",
        "headers": "Message-ID: <ticket@example.com>\n",
    }
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"super-secret", body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook/email",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert tickets == [
        {
            "tenant_id": "acme",
            "session_id": "email-session-1",
            "user_question": "Need help\n\nWhere is my order?",
            "ai_draft": "Escalate this",
            "status": "pending_response",
        }
    ]


def test_email_webhook_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.email_webhook_secret = SecretStr("super-secret")
    settings.email_webhook_signing_secret = SecretStr("super-secret")
    monkeypatch.setattr(api_app, "get_settings", lambda: settings)

    response = client.post(
        "/webhook/email",
        content=json.dumps({"from": "user@acme.com", "to": "support@acme.test", "subject": "Hi", "text": "Body"}),
        headers={"X-Signature": "invalid"},
    )

    assert response.status_code == 401

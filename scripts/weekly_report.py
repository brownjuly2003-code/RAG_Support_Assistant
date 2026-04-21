#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import httpx

from config.settings import get_settings
from reports.renderer import generate_report


def get_target_tenants(tenant: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    tenant_id = tenant or "default"
    return [
        {
            "id": tenant_id,
            "slack_webhook": settings.report_slack_webhook,
            "report_emails": list(settings.report_email_recipients),
        }
    ]


async def send_slack(webhook: str, markdown: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook, json={"text": markdown})
        response.raise_for_status()


async def send_email(recipients: list[str], subject: str, markdown: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(markdown)

    with smtplib.SMTP(settings.report_smtp_host or settings.smtp_host, settings.report_smtp_port) as client:
        if settings.report_smtp_user:
            client.starttls()
            password = settings.report_smtp_pass.get_secret_value() if settings.report_smtp_pass else ""
            client.login(settings.report_smtp_user, password)
        client.send_message(message)


async def run_once(tenant: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = now - timedelta(days=7)
    processed = 0

    for target in get_target_tenants(tenant):
        markdown = await generate_report(target["id"], week_start, week_end)
        if dry_run:
            print(markdown)
            processed += 1
            continue
        if target.get("slack_webhook"):
            await send_slack(target["slack_webhook"], markdown)
        if target.get("report_emails"):
            await send_email(target["report_emails"], f"Weekly report — {week_start:%Y-%m-%d}", markdown)
        processed += 1

    return {"status": "ok", "processed": processed}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    await run_once(tenant=args.tenant, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

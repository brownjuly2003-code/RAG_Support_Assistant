from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest


def test_generate_report_includes_week_over_week_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reports import renderer

    async def _fake_gather(tenant_id: str, week_start: datetime, week_end: datetime) -> dict:
        _ = tenant_id, week_start, week_end
        if week_end.day == 14:
            return {
                "total_q": 5,
                "resolution_rate": 0.4,
                "avg_quality": 0.7,
                "total_cost": 0.0,
                "top_topics": [],
                "new_gaps": [],
                "stale_docs": [],
                "anomalies": [],
            }
        return {
            "total_q": 10,
            "resolution_rate": 0.6,
            "avg_quality": 0.8,
            "total_cost": 0.0,
            "top_topics": [],
            "new_gaps": [],
            "stale_docs": [],
            "anomalies": [],
        }

    monkeypatch.setattr(renderer, "gather_analytics", _fake_gather)

    week_start = datetime(2026, 4, 14, tzinfo=timezone.utc)
    week_end = datetime(2026, 4, 21, tzinfo=timezone.utc)
    report = asyncio.run(renderer.generate_report("TEST", week_start, week_end))

    assert "# RAG Support Weekly Report" in report
    assert "| Total questions | 10 | 5 | +100.0% |" in report


def test_weekly_report_run_once_sends_slack_and_email(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import weekly_report

    async def _fake_generate_report(tenant_id: str, week_start: datetime, week_end: datetime) -> str:
        _ = tenant_id, week_start, week_end
        return "# Weekly report"

    sent: list[tuple[str, str]] = []

    async def _fake_send_slack(webhook: str, markdown: str) -> None:
        sent.append(("slack", webhook))
        assert markdown == "# Weekly report"

    async def _fake_send_email(recipients: list[str], subject: str, markdown: str) -> None:
        sent.append(("email", ",".join(recipients)))
        assert "Weekly report" in subject
        assert markdown == "# Weekly report"

    monkeypatch.setattr(weekly_report, "generate_report", _fake_generate_report)
    monkeypatch.setattr(weekly_report, "send_slack", _fake_send_slack)
    monkeypatch.setattr(weekly_report, "send_email", _fake_send_email)
    monkeypatch.setattr(
        weekly_report,
        "get_target_tenants",
        lambda tenant=None: [
            {
                "id": "TEST",
                "slack_webhook": "https://hooks.slack.test/weekly",
                "report_emails": ["ops@example.com"],
            }
        ],
    )

    result = asyncio.run(weekly_report.run_once(tenant="TEST", dry_run=False))

    assert result["processed"] == 1
    assert ("slack", "https://hooks.slack.test/weekly") in sent
    assert ("email", "ops@example.com") in sent
    assert capsys.readouterr().out == ""

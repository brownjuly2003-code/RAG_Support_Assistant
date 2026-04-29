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


def test_renderer_helpers_cover_empty_and_limited_rows() -> None:
    from reports import renderer

    assert renderer.delta_pct(0, 0) == "n/a"
    assert renderer.delta_pct(3, 0) == "+100.0%"
    assert renderer.delta_pp(0.6, 0.4) == "+20.0 pp"
    assert renderer.render_topics_table([]) == "_No topic data_"
    assert renderer.render_gaps([]) == "_No new gaps_"
    assert renderer.render_stale([]) == "_No stale docs_"
    assert renderer.render_anomalies([]) == "_No anomalies detected_"

    topics = [{"category": f"topic-{idx}", "count": idx} for idx in range(6)]
    topics_table = renderer.render_topics_table(topics)
    assert "| topic-0 | 0 |" in topics_table
    assert "| topic-4 | 4 |" in topics_table
    assert "topic-5" not in topics_table
    assert renderer.render_topics_table([{"topic": "fallback-topic"}]).endswith(
        "| fallback-topic | 0 |"
    )
    assert renderer.render_topics_table([{}]).endswith("| uncategorized | 0 |")

    assert renderer.render_gaps([{"topic_summary": "billing gap"}]) == "- billing gap"
    assert renderer.render_stale([{"title": "Refunds", "citation_count": 3}]) == (
        "- Refunds (3 citations)"
    )
    assert renderer.render_stale([{"doc_id": "doc-1"}]) == "- doc-1 (0 citations)"
    assert renderer.render_anomalies(["cost spike"]) == "- cost spike"


def test_gather_analytics_filters_week_and_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app
    from reports import renderer

    week_start = datetime(2026, 4, 14, tzinfo=timezone.utc)
    week_end = datetime(2026, 4, 21, tzinfo=timezone.utc)
    summaries = [
        {
            "created_at": datetime(2026, 4, 15, tzinfo=timezone.utc),
            "route": "auto",
            "quality_score": 0.8,
            "cost_usd": "0.10",
            "categories": ["billing", "returns"],
        },
        {
            "created_at": datetime(2026, 4, 20, tzinfo=timezone.utc),
            "route": "escalated",
            "quality_score": 0.6,
            "cost_usd": 0.2,
            "categories": ["billing"],
        },
        {
            "created_at": datetime(2026, 4, 10, tzinfo=timezone.utc),
            "route": "auto",
            "quality_score": 1.0,
            "cost_usd": 9.99,
            "categories": ["ignored"],
        },
    ]

    monkeypatch.setattr(api_app, "_load_recent_trace_summaries", lambda tenant, days: summaries)
    monkeypatch.setattr(
        api_app,
        "_list_tenant_documents",
        lambda tenant: [
            {"doc_id": "doc-1", "title": "Refund policy", "last_updated": "2026-04-20"},
            {"doc_id": "doc-2", "title": "No date", "last_updated": ""},
        ],
    )

    analytics = asyncio.run(renderer.gather_analytics("TENANT", week_start, week_end))

    assert analytics["total_q"] == 2
    assert analytics["resolution_rate"] == 0.5
    assert analytics["avg_quality"] == pytest.approx(0.7)
    assert analytics["total_cost"] == pytest.approx(0.3)
    assert analytics["top_topics"] == [
        {"category": "billing", "count": 2},
        {"category": "returns", "count": 1},
    ]
    assert analytics["stale_docs"] == [
        {"doc_id": "doc-1", "title": "Refund policy", "last_updated": "2026-04-20"}
    ]
    assert analytics["new_gaps"] == []
    assert analytics["anomalies"] == []


def test_gather_analytics_handles_empty_data_and_document_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.app as api_app
    from reports import renderer

    monkeypatch.setattr(api_app, "_load_recent_trace_summaries", lambda tenant, days: [])

    def _raise(_tenant: str) -> list[dict]:
        raise RuntimeError("documents unavailable")

    monkeypatch.setattr(api_app, "_list_tenant_documents", _raise)

    analytics = asyncio.run(
        renderer.gather_analytics(
            "TENANT",
            datetime(2026, 4, 14, tzinfo=timezone.utc),
            datetime(2026, 4, 21, tzinfo=timezone.utc),
        )
    )

    assert analytics["total_q"] == 0
    assert analytics["resolution_rate"] == 0.0
    assert analytics["avg_quality"] == 0.0
    assert analytics["total_cost"] == 0
    assert analytics["top_topics"] == []
    assert analytics["stale_docs"] == []


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

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("analytics-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def test_top_topics_endpoint_groups_by_category(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        api_app,
        "_load_recent_trace_summaries",
        lambda tenant_id, days: [
            {
                "categories": ["shipping"],
                "route": "auto",
                "quality_score": 80,
                "cost_usd": 0.0,
                "created_at": now,
            },
            {
                "categories": ["shipping", "returns"],
                "route": "human",
                "quality_score": 60,
                "cost_usd": 0.0,
                "created_at": now,
            },
        ],
    )

    response = client_with_key.get(
        "/api/analytics/top-topics?days=7",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    topics = response.json()["topics"]
    assert topics[0]["category"] == "shipping"
    assert topics[0]["count"] == 2


def test_cost_summary_reports_self_hosted_when_cost_is_zero(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app

    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        api_app,
        "_load_recent_trace_summaries",
        lambda tenant_id, days: [
            {
                "categories": ["shipping"],
                "route": "auto",
                "quality_score": 80,
                "cost_usd": 0.0,
                "created_at": now,
            }
        ],
    )

    response = client_with_key.get(
        "/api/analytics/cost-summary?days=7",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["label"] == "self-hosted (no cost)"

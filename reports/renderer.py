from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def delta_pct(current: float, previous: float) -> str:
    if previous == 0:
        return "n/a" if current == 0 else "+100.0%"
    return f"{((current - previous) / previous) * 100:+.1f}%"


def delta_pp(current: float, previous: float) -> str:
    return f"{(current - previous) * 100:+.1f} pp"


def render_topics_table(topics: list[dict[str, Any]]) -> str:
    if not topics:
        return "_No topic data_"
    lines = ["| Topic | Count |", "| --- | ---: |"]
    for item in topics[:5]:
        lines.append(f"| {item.get('category') or item.get('topic') or 'uncategorized'} | {item.get('count', 0)} |")
    return "\n".join(lines)


def render_gaps(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return "_No new gaps_"
    return "\n".join(f"- {item.get('topic_summary') or item}" for item in gaps[:5])


def render_stale(stale_docs: list[dict[str, Any]]) -> str:
    if not stale_docs:
        return "_No stale docs_"
    return "\n".join(
        f"- {item.get('title') or item.get('doc_id')} ({item.get('citation_count', 0)} citations)"
        for item in stale_docs[:5]
    )


def render_anomalies(anomalies: list[str]) -> str:
    if not anomalies:
        return "_No anomalies detected_"
    return "\n".join(f"- {item}" for item in anomalies[:5])


async def gather_analytics(tenant_id: str, week_start: datetime, week_end: datetime) -> dict[str, Any]:
    from api import app as api_app  # noqa: PLC0415

    days = max(1, (week_end - week_start).days)
    summaries = api_app._load_recent_trace_summaries(tenant_id, days)
    summaries = [
        item for item in summaries
        if week_start <= item["created_at"] <= week_end
    ]

    total_q = len(summaries)
    resolved = sum(1 for item in summaries if item["route"] == "auto")
    avg_quality = sum(float(item["quality_score"] or 0) for item in summaries) / total_q if total_q else 0.0
    total_cost = sum(float(item["cost_usd"] or 0.0) for item in summaries)

    topic_counts: dict[str, int] = {}
    for item in summaries:
        for category in item["categories"]:
            topic_counts[category] = topic_counts.get(category, 0) + 1

    top_topics = [
        {"category": category, "count": count}
        for category, count in sorted(topic_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]

    stale_docs = []
    try:
        documents = api_app._list_tenant_documents(tenant_id)
        stale_docs = [doc for doc in documents if doc.get("last_updated")]
    except Exception:
        stale_docs = []

    return {
        "total_q": total_q,
        "resolution_rate": resolved / total_q if total_q else 0.0,
        "avg_quality": avg_quality,
        "total_cost": total_cost,
        "top_topics": top_topics,
        "new_gaps": [],
        "stale_docs": stale_docs[:5],
        "anomalies": [],
    }


async def generate_report(tenant_id: str, week_start: datetime, week_end: datetime) -> str:
    analytics = await gather_analytics(tenant_id, week_start, week_end)
    prev_week = await gather_analytics(
        tenant_id,
        week_start - timedelta(days=7),
        week_start,
    )

    return f"""# RAG Support Weekly Report — {week_start:%Y-%m-%d} to {week_end:%Y-%m-%d}

**Tenant:** {tenant_id}

## Key metrics
| Metric | This week | Last week | Δ |
| --- | ---: | ---: | ---: |
| Total questions | {analytics['total_q']} | {prev_week['total_q']} | {delta_pct(analytics['total_q'], prev_week['total_q'])} |
| Resolution rate | {analytics['resolution_rate']:.1%} | {prev_week['resolution_rate']:.1%} | {delta_pp(analytics['resolution_rate'], prev_week['resolution_rate'])} |
| Avg quality score | {analytics['avg_quality']:.2f} | {prev_week['avg_quality']:.2f} | {delta_pct(analytics['avg_quality'], prev_week['avg_quality'])} |
| Total cost | ${analytics['total_cost']:.2f} | ${prev_week['total_cost']:.2f} | {delta_pct(analytics['total_cost'], prev_week['total_cost'])} |

## Top 5 topics
{render_topics_table(analytics['top_topics'])}

## Knowledge gaps (new this week)
{render_gaps(analytics['new_gaps'])}

## Stale docs requiring review
{render_stale(analytics['stale_docs'])}

## Anomalies
{render_anomalies(analytics['anomalies'])}
"""

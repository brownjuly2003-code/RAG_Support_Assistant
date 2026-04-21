from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from auth.jwt_handler import create_access_token


def _headers(tenant: str = "acme", role: str = "admin") -> dict[str, str]:
    token = create_access_token("improvement-backlog-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def _signal(
    source: str,
    title: str,
    *,
    tenant_id: str = "acme",
    frequency: int = 1,
    days_ago: int = 0,
    impact: float | None = None,
) -> dict[str, object]:
    return {
        "source": source,
        "title": title,
        "tenant_id": tenant_id,
        "frequency": frequency,
        "impact": impact,
        "latest_at": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc) - timedelta(days=days_ago),
        "trace_ids": [f"{source}-{title}"],
        "details": {},
    }


def test_run_once_merges_sources_and_ranks_by_priority(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
) -> None:
    from scripts import generate_improvement_backlog

    settings = settings_factory(
        project_root=tmp_path,
        backlog_weight_review_bad=3.0,
        backlog_weight_thumbs_down=2.0,
        backlog_weight_slow=1.5,
        backlog_weight_freshness=1.0,
        backlog_weight_evaluator_drift=2.5,
        backlog_max_items=30,
        backlog_freshness_max_days=90,
        backlog_email_enabled=False,
        tenant_admin_email="",
    )

    async def _review(*args, **kwargs):
        _ = args, kwargs
        return [_signal("review", "Refund misinformation", frequency=3)]

    async def _kb(*args, **kwargs):
        _ = args, kwargs
        return [_signal("kb_gap", "Missing invoice KB", frequency=2)]

    async def _slow(*args, **kwargs):
        _ = args, kwargs
        return [_signal("slow_trace", "Slow /api/ask", frequency=4)]

    async def _empty(*args, **kwargs):
        _ = args, kwargs
        return []

    monkeypatch.setattr(generate_improvement_backlog, "load_review_queue_signals", _review)
    monkeypatch.setattr(generate_improvement_backlog, "load_kb_gap_signals", _kb)
    monkeypatch.setattr(generate_improvement_backlog, "load_slow_trace_signals", _slow)
    monkeypatch.setattr(generate_improvement_backlog, "load_freshness_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_evaluator_drift_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_thumbs_down_signals", _empty)

    result = asyncio.run(
        generate_improvement_backlog.run_once(
            tenant="acme",
            week="2026-W17",
            out=tmp_path / "reports" / "improvement_backlog" / "2026-W17.md",
            settings=settings,
            now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        )
    )

    assert [item["source"] for item in result["items"]] == ["review", "slow_trace", "kb_gap"]
    assert result["summary"]["items"] == 3
    assert result["items"][0]["priority"] > result["items"][1]["priority"] > result["items"][2]["priority"]


def test_priority_recency_decay_prefers_recent_signal() -> None:
    from scripts import generate_improvement_backlog

    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    recent = generate_improvement_backlog.compute_priority(
        impact=2.0,
        frequency=2,
        latest_at=now,
        now=now,
    )
    old = generate_improvement_backlog.compute_priority(
        impact=2.0,
        frequency=2,
        latest_at=now - timedelta(days=7),
        now=now,
    )

    assert recent > old


def test_run_once_caps_items_to_configured_max(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
) -> None:
    from scripts import generate_improvement_backlog

    settings = settings_factory(
        project_root=tmp_path,
        backlog_weight_review_bad=3.0,
        backlog_weight_thumbs_down=2.0,
        backlog_weight_slow=1.5,
        backlog_weight_freshness=1.0,
        backlog_weight_evaluator_drift=2.5,
        backlog_max_items=2,
        backlog_freshness_max_days=90,
        backlog_email_enabled=False,
        tenant_admin_email="",
    )

    async def _review(*args, **kwargs):
        _ = args, kwargs
        return [
            _signal("review", "Item 1", frequency=4),
            _signal("review", "Item 2", frequency=3),
            _signal("review", "Item 3", frequency=2),
        ]

    async def _empty(*args, **kwargs):
        _ = args, kwargs
        return []

    monkeypatch.setattr(generate_improvement_backlog, "load_review_queue_signals", _review)
    monkeypatch.setattr(generate_improvement_backlog, "load_kb_gap_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_slow_trace_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_freshness_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_evaluator_drift_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_thumbs_down_signals", _empty)

    result = asyncio.run(
        generate_improvement_backlog.run_once(
            tenant="acme",
            week="2026-W17",
            out=tmp_path / "reports" / "improvement_backlog" / "2026-W17.md",
            settings=settings,
            now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        )
    )

    assert len(result["items"]) == 2


def test_run_once_writes_markdown_that_parses(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
) -> None:
    from scripts import generate_improvement_backlog

    settings = settings_factory(
        project_root=tmp_path,
        backlog_weight_review_bad=3.0,
        backlog_weight_thumbs_down=2.0,
        backlog_weight_slow=1.5,
        backlog_weight_freshness=1.0,
        backlog_weight_evaluator_drift=2.5,
        backlog_max_items=30,
        backlog_freshness_max_days=90,
        backlog_email_enabled=False,
        tenant_admin_email="",
    )
    out_path = tmp_path / "reports" / "improvement_backlog" / "2026-W17.md"

    async def _review(*args, **kwargs):
        _ = args, kwargs
        return [_signal("review", "Refund misinformation", frequency=3)]

    async def _empty(*args, **kwargs):
        _ = args, kwargs
        return []

    monkeypatch.setattr(generate_improvement_backlog, "load_review_queue_signals", _review)
    monkeypatch.setattr(generate_improvement_backlog, "load_kb_gap_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_slow_trace_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_freshness_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_evaluator_drift_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_thumbs_down_signals", _empty)

    asyncio.run(
        generate_improvement_backlog.run_once(
            tenant="acme",
            week="2026-W17",
            out=out_path,
            settings=settings,
            now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        )
    )

    markdown = out_path.read_text(encoding="utf-8")
    tokens = MarkdownIt().parse(markdown)

    assert markdown.startswith("# Improvement backlog")
    assert any(token.type == "heading_open" for token in tokens)


def test_admin_current_improvement_backlog_endpoint_returns_json(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    import api.app as api_app
    from scripts import generate_improvement_backlog

    async def _run_once(*args, **kwargs):
        _ = args, kwargs
        return {
            "week": "2026-W17",
            "summary": {"items": 1, "top_sources": {"review": 1}},
            "items": [{"source": "review", "title": "Refund misinformation", "priority": 9.0}],
            "stats": {"items_by_type": {"review": 1}, "most_common_tenant": "acme"},
        }

    monkeypatch.setattr(generate_improvement_backlog, "run_once", _run_once)
    monkeypatch.setattr(generate_improvement_backlog, "latest_persisted_week", lambda root: "2026-W17")

    response = client_with_key.get(
        "/api/admin/improvement-backlog/current",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert response.json()["week"] == "2026-W17"
    assert response.json()["items"][0]["title"] == "Refund misinformation"
    assert api_app.get_current_tenant() is None


def test_admin_improvement_backlog_archive_lists_historical_weeks(
    client_with_key,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import api.app as api_app

    settings = api_app.get_settings()
    settings.project_root = tmp_path
    backlog_dir = tmp_path / "reports" / "improvement_backlog"
    backlog_dir.mkdir(parents=True)
    (backlog_dir / "2026-W17.md").write_text("# W17", encoding="utf-8")
    (backlog_dir / "2026-W18.md").write_text("# W18", encoding="utf-8")
    (backlog_dir / "2025-W52.md").write_text("# W52", encoding="utf-8")

    response = client_with_key.get(
        "/api/admin/improvement-backlog/archive?year=2026",
        headers=_headers("acme", "admin"),
    )

    assert response.status_code == 200
    assert [item["week"] for item in response.json()["weeks"]] == ["2026-W18", "2026-W17"]


def test_run_once_empty_week_returns_zero_items(
    monkeypatch: pytest.MonkeyPatch,
    settings_factory,
    tmp_path: Path,
) -> None:
    from scripts import generate_improvement_backlog

    settings = settings_factory(
        project_root=tmp_path,
        backlog_weight_review_bad=3.0,
        backlog_weight_thumbs_down=2.0,
        backlog_weight_slow=1.5,
        backlog_weight_freshness=1.0,
        backlog_weight_evaluator_drift=2.5,
        backlog_max_items=30,
        backlog_freshness_max_days=90,
        backlog_email_enabled=False,
        tenant_admin_email="",
    )
    out_path = tmp_path / "reports" / "improvement_backlog" / "2026-W17.md"

    async def _empty(*args, **kwargs):
        _ = args, kwargs
        return []

    monkeypatch.setattr(generate_improvement_backlog, "load_review_queue_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_kb_gap_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_slow_trace_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_freshness_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_evaluator_drift_signals", _empty)
    monkeypatch.setattr(generate_improvement_backlog, "load_thumbs_down_signals", _empty)

    result = asyncio.run(
        generate_improvement_backlog.run_once(
            tenant="acme",
            week="2026-W17",
            out=out_path,
            settings=settings,
            now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        )
    )

    assert result["summary"]["items"] == 0
    assert result["items"] == []
    assert "Items: 0" in out_path.read_text(encoding="utf-8")

from __future__ import annotations

from pathlib import Path

import pytest

from api import _shared as api_shared

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_tenant_access_decision_records_only_confirmed_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[str] = []
    monkeypatch.setattr(
        api_shared.prometheus_metrics,
        "record_tenant_access_denial",
        recorded.append,
    )

    assert api_shared.tenant_access_allowed("tenant-a", "tenant-a", "session") is True
    assert api_shared.tenant_access_allowed(None, "tenant-a", "session") is True
    assert api_shared.tenant_access_allowed("tenant-a", "tenant-b", "session") is False
    assert recorded == ["session"]


def test_tenant_access_metric_failure_preserves_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_resource: str) -> None:
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(
        api_shared.prometheus_metrics,
        "record_tenant_access_denial",
        _boom,
    )

    assert api_shared.tenant_access_allowed("tenant-a", "tenant-b", "ticket") is False


def test_confirmed_api_denial_inventory_uses_shared_boundary() -> None:
    expected = {
        "api/app.py": (1, 1),
        "api/routers/session_auth.py": (2, 0),
        "api/routers/agent.py": (3, 0),
        "api/routers/admin_kb.py": (3, 0),
    }

    total = 0
    for relative_path, (decision_calls, direct_calls) in expected.items():
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert source.count("tenant_access_allowed(") == decision_calls
        assert source.count('record_tenant_access_denial("session")') == direct_calls
        total += decision_calls + direct_calls

    assert total == 10

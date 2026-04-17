from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def test_record_db_pool_stats_sets_gauges() -> None:
    from monitoring.prometheus import (
        DB_POOL_CHECKED_OUT,
        DB_POOL_OVERFLOW,
        DB_POOL_SIZE,
        PROMETHEUS_AVAILABLE,
        record_db_pool_stats,
    )

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_db_pool_stats(size=10, checked_out=3, overflow=2)

    def _gauge_val(metric, sample_name: str) -> float:
        for collected in metric.collect():
            for sample in collected.samples:
                if sample.name == sample_name:
                    return sample.value
        return -1.0

    assert _gauge_val(DB_POOL_SIZE, "rag_db_pool_size") == 10
    assert _gauge_val(DB_POOL_CHECKED_OUT, "rag_db_pool_checked_out") == 3
    assert _gauge_val(DB_POOL_OVERFLOW, "rag_db_pool_overflow") == 2


def test_negative_values_are_ignored() -> None:
    from monitoring.prometheus import (
        DB_POOL_CHECKED_OUT,
        DB_POOL_OVERFLOW,
        DB_POOL_SIZE,
        PROMETHEUS_AVAILABLE,
        record_db_pool_stats,
    )

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_db_pool_stats(size=42, checked_out=4, overflow=1)
    record_db_pool_stats(size=-1, checked_out=-1, overflow=-1)

    def _gauge_val(metric, sample_name: str) -> float:
        for collected in metric.collect():
            for sample in collected.samples:
                if sample.name == sample_name:
                    return sample.value
        return -1.0

    assert _gauge_val(DB_POOL_SIZE, "rag_db_pool_size") == 42
    assert _gauge_val(DB_POOL_CHECKED_OUT, "rag_db_pool_checked_out") == 4
    assert _gauge_val(DB_POOL_OVERFLOW, "rag_db_pool_overflow") == 1


def test_get_pool_stats_handles_broken_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    import db.engine as db_engine

    class _BrokenPool:
        def size(self) -> int:
            raise RuntimeError("engine disposed")

        def checkedout(self) -> int:
            raise RuntimeError("engine disposed")

        def overflow(self) -> int:
            raise RuntimeError("engine disposed")

    fake_engine = MagicMock()
    fake_engine.pool = _BrokenPool()
    monkeypatch.setattr(db_engine, "engine", fake_engine)

    assert db_engine.get_pool_stats() == {
        "size": -1,
        "checked_out": -1,
        "overflow": -1,
    }


def test_probe_postgres_updates_pool_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.app as api_app
    import db.engine as db_engine
    from monitoring.prometheus import DB_POOL_SIZE, PROMETHEUS_AVAILABLE, record_db_pool_stats

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def execute(self, statement):
            return statement

    record_db_pool_stats(size=0, checked_out=0, overflow=0)
    monkeypatch.setattr(db_engine, "async_session", lambda: _FakeSession())
    monkeypatch.setattr(
        db_engine,
        "get_pool_stats",
        lambda: {"size": 99, "checked_out": 7, "overflow": 1},
    )

    status = asyncio.run(api_app._probe_postgres())

    def _gauge_val() -> float:
        for collected in DB_POOL_SIZE.collect():
            for sample in collected.samples:
                if sample.name == "rag_db_pool_size":
                    return sample.value
        return -1.0

    assert status.status == "ok"
    assert _gauge_val() == 99

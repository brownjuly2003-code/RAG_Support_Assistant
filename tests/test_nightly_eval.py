from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import monitoring.prometheus as prometheus_metrics
from db.models import EvalResult
from evaluation import drift
from scripts import nightly_eval


class _FakeSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb
        return None


def test_detect_drift_updates_prometheus_gauge() -> None:
    drift.detect_drift(
        {"faithfulness": 0.72},
        {"faithfulness": 0.9},
        threshold=0.1,
    )

    metrics_text = prometheus_metrics.generate_latest(prometheus_metrics.REGISTRY).decode("utf-8")

    assert 'rag_eval_drift{metric_name="faithfulness"} 0.2' in metrics_text


def test_run_once_skips_when_trace_sample_is_too_small(monkeypatch) -> None:
    async def _fake_sample_traces(session, since, n):
        _ = session, since, n
        return [{"question": "q"}] * 5

    monkeypatch.setattr(nightly_eval, "sample_traces", _fake_sample_traces)

    result = asyncio.run(
        nightly_eval.run_once(
            session_factory=_FakeSessionFactory(SimpleNamespace()),
            now=datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc),
        )
    )

    assert result["status"] == "skipped"
    assert result["sample_size"] == 5


def test_run_once_persists_eval_results_and_alert_flags(monkeypatch) -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.added: list[EvalResult] = []
            self.commit_calls = 0

        def add(self, obj) -> None:
            self.added.append(obj)

        async def commit(self) -> None:
            self.commit_calls += 1

    async def _fake_sample_traces(session, since, n):
        _ = session, since, n
        return [{"question": f"q-{idx}", "answer": "a", "context_docs": []} for idx in range(12)]

    async def _fake_evaluate_traces(traces):
        _ = traces
        return {
            "faithfulness": 0.72,
            "context_precision": 0.81,
        }

    async def _fake_get_baseline(session, metric_name, days, now):
        _ = session, days, now
        baselines = {
            "faithfulness": 0.9,
            "context_precision": 0.8,
        }
        return baselines[metric_name]

    fake_session = _FakeSession()
    monkeypatch.setattr(nightly_eval, "sample_traces", _fake_sample_traces)
    monkeypatch.setattr(nightly_eval, "evaluate_traces", _fake_evaluate_traces)
    monkeypatch.setattr(nightly_eval, "get_baseline", _fake_get_baseline)

    result = asyncio.run(
        nightly_eval.run_once(
            session_factory=_FakeSessionFactory(fake_session),
            now=datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc),
        )
    )

    assert result["status"] == "ok"
    assert result["sample_size"] == 12
    assert fake_session.commit_calls == 1
    assert len(fake_session.added) == 2
    assert {row.metric_name for row in fake_session.added} == {"faithfulness", "context_precision"}
    assert {row.metric_name for row in fake_session.added if row.drift_alert} == {"faithfulness"}

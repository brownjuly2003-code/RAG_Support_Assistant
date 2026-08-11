"""PipelineRunner ownership of capacity and orphan-work lifecycle."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest


def test_pipeline_runner_owns_orphan_capacity_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import pipeline as pipeline_service

    recorded: list[str] = []
    monkeypatch.setattr(
        pipeline_service.prometheus_metrics,
        "record_orphan_work_started",
        lambda: recorded.append("started"),
    )
    monkeypatch.setattr(
        pipeline_service.prometheus_metrics,
        "record_orphan_work_finished",
        lambda: recorded.append("finished"),
    )

    class _Gauge:
        def dec(self) -> None:
            recorded.append("inflight-dec")

    class _Semaphore:
        def release(self) -> None:
            recorded.append("released")

    monkeypatch.setattr(pipeline_service.prometheus_metrics, "INFLIGHT_PIPELINES", _Gauge())
    runner = pipeline_service.PipelineRunner()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        runner.hold_capacity_until_future_done(
            loop=loop,
            fut=future,
            semaphore=_Semaphore(),
        )
        assert recorded == ["started"]

        future.set_result(None)
        loop.run_until_complete(asyncio.sleep(0.01))

        assert recorded == ["started", "finished", "inflight-dec", "released"]
    finally:
        loop.close()


def test_conversation_capacity_helpers_delegate_to_single_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = importlib.import_module("api.routers.conversation")

    class RecordingOwner:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def release_capacity(self, semaphore: Any) -> None:
            self.calls.append(("release", semaphore))

        def hold_capacity_until_future_done(
            self,
            *,
            loop: asyncio.AbstractEventLoop,
            fut: Any,
            semaphore: Any,
            release_capacity: Any = None,
        ) -> None:
            self.calls.append(("hold", loop, fut, semaphore, release_capacity))

    owner = RecordingOwner()
    monkeypatch.setattr(conversation, "pipeline_runner", owner)
    semaphore = object()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        conversation._release_pipeline_capacity(semaphore)
        conversation._hold_capacity_until_future_done(
            loop=loop,
            fut=future,
            semaphore=semaphore,
        )

        assert owner.calls == [
            ("release", semaphore),
            (
                "hold",
                loop,
                future,
                semaphore,
                conversation._release_pipeline_capacity,
            ),
        ]
    finally:
        loop.close()

"""PipelineRunner ownership of capacity and orphan-work lifecycle."""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import Any, ClassVar

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


def test_pipeline_runner_owns_sync_execution_and_timeout_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import pipeline as pipeline_service

    async def _exercise() -> None:
        runner = pipeline_service.PipelineRunner()
        running_loop = asyncio.get_running_loop()
        executor = object()
        semaphore = object()
        submitted: list[tuple[Any, Any]] = []
        held: list[dict[str, Any]] = []

        def operation() -> str:
            return "unused"

        class _Loop:
            def __init__(self, future: asyncio.Future[Any]) -> None:
                self.future = future

            def run_in_executor(
                self,
                selected_executor: Any,
                selected_operation: Any,
            ) -> asyncio.Future[Any]:
                submitted.append((selected_executor, selected_operation))
                return self.future

        success_future = running_loop.create_future()
        success_future.set_result("done")
        result = await runner.run_sync_with_deadline(
            loop=_Loop(success_future),
            executor=executor,
            operation=operation,
            timeout=1.0,
            semaphore=semaphore,
        )

        assert result == "done"
        assert submitted == [(executor, operation)]

        timeout_future = running_loop.create_future()
        monkeypatch.setattr(
            runner,
            "hold_capacity_until_future_done",
            lambda **kwargs: held.append(kwargs),
        )
        with pytest.raises(asyncio.TimeoutError):
            await runner.run_sync_with_deadline(
                loop=_Loop(timeout_future),
                executor=executor,
                operation=operation,
                timeout=0.0,
                semaphore=semaphore,
            )

        assert len(held) == 1
        assert held[0]["fut"] is timeout_future
        assert held[0]["semaphore"] is semaphore
        assert held[0]["release_capacity"] is None
        timeout_future.cancel()

    asyncio.run(_exercise())


def test_sync_ask_execution_delegates_to_pipeline_runner(
    monkeypatch: pytest.MonkeyPatch,
    client,
    settings_factory,
) -> None:
    api_app = importlib.import_module("api.app")
    conversation = importlib.import_module("api.routers.conversation")
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(request_timeout_sec=1.25),
    )
    api_app._db_retry_after = time.monotonic() + 60.0
    api_app._pipeline_semaphore = None

    class _Session:
        _history: ClassVar[list] = []

        def ask(self, question: str, **kwargs: Any) -> dict:
            raise AssertionError("endpoint bypassed PipelineRunner")

    async def _get_session(session_id, tenant_id="default"):
        return "pipeline-owner", _Session()

    async def _run_sync_with_deadline(**kwargs: Any) -> dict:
        calls.append(kwargs)
        return {
            "answer": "owned",
            "quality_score": 75,
            "route": "auto",
        }

    monkeypatch.setattr(api_app, "_get_or_create_session", _get_session)
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "run_sync_with_deadline",
        _run_sync_with_deadline,
    )

    response = client.post("/api/ask", json={"question": "owner"})

    assert response.status_code == 200
    assert response.json()["answer"] == "owned"
    assert len(calls) == 1
    assert calls[0]["timeout"] == 1.25
    assert callable(calls[0]["operation"])

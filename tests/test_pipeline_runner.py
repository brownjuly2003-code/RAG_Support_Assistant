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


def test_pipeline_runner_owns_streaming_submission_and_deadline_handoff(
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
            return "stream-work"

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
        success_future.set_result("submitted")
        graph_future = runner.submit_stream_graph(
            loop=_Loop(success_future),
            executor=executor,
            operation=operation,
        )
        assert graph_future is success_future
        assert submitted == [(executor, operation)]

        event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        await event_queue.put(("event", {"type": "status", "node": "retrieve"}))
        kind, payload = await runner.wait_stream_queue_event(
            queue=event_queue,
            timeout=1.0,
            fut=success_future,
            semaphore=semaphore,
        )
        assert kind == "event"
        assert payload == {"type": "status", "node": "retrieve"}

        result_future = running_loop.create_future()
        result_future.set_result({"answer": "graph"})
        result = await runner.wait_stream_future_result(
            fut=result_future,
            timeout=1.0,
            semaphore=semaphore,
        )
        assert result == {"answer": "graph"}

        monkeypatch.setattr(
            runner,
            "hold_capacity_until_future_done",
            lambda **kwargs: held.append(kwargs),
        )

        timeout_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        timeout_queue_future = running_loop.create_future()
        with pytest.raises(asyncio.TimeoutError):
            await runner.wait_stream_queue_event(
                queue=timeout_queue,
                timeout=0.0,
                fut=timeout_queue_future,
                semaphore=semaphore,
            )
        assert len(held) == 1
        assert held[0]["fut"] is timeout_queue_future
        assert held[0]["semaphore"] is semaphore
        assert held[0]["release_capacity"] is None

        held.clear()
        timeout_future = running_loop.create_future()
        with pytest.raises(asyncio.TimeoutError):
            await runner.wait_stream_future_result(
                fut=timeout_future,
                timeout=0.0,
                semaphore=semaphore,
            )
        assert len(held) == 1
        assert held[0]["fut"] is timeout_future
        assert held[0]["semaphore"] is semaphore
        assert held[0]["release_capacity"] is None
        timeout_queue_future.cancel()
        timeout_future.cancel()

        # After timeout, no leaked queue.get() waiter may consume a later item.
        leftover_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        leftover_future = running_loop.create_future()
        with pytest.raises(asyncio.TimeoutError):
            await runner.wait_stream_queue_event(
                queue=leftover_queue,
                timeout=0.0,
                fut=leftover_future,
                semaphore=semaphore,
            )
        await leftover_queue.put(("event", {"type": "status", "node": "late"}))
        assert leftover_queue.qsize() == 1
        leftover_kind, leftover_payload = leftover_queue.get_nowait()
        assert leftover_kind == "event"
        assert leftover_payload == {"type": "status", "node": "late"}
        leftover_future.cancel()

    asyncio.run(_exercise())


def test_stream_graph_execution_delegates_to_pipeline_runner(
    monkeypatch: pytest.MonkeyPatch,
    client,
    settings_factory,
) -> None:
    api_app = importlib.import_module("api.app")
    conversation = importlib.import_module("api.routers.conversation")
    submit_calls: list[dict[str, Any]] = []
    wait_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            streaming_enabled=True,
            streaming_rag_parity=True,
            request_timeout_sec=1.5,
            max_concurrent_pipelines=2,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0
    api_app._pipeline_semaphore = None

    class _Session:
        _history: ClassVar[list] = []

        def ask(self, question: str, **kwargs: Any) -> dict:
            raise AssertionError("stream graph path bypassed PipelineRunner")

    async def _get_session(session_id, tenant_id="default"):
        return "stream-owner", _Session()

    def _submit_stream_graph(**kwargs: Any) -> Any:
        submit_calls.append(kwargs)
        active_loop = kwargs.get("loop") or asyncio.get_running_loop()
        future = active_loop.create_future()
        future.set_result(
            {
                "answer": "owned-stream",
                "quality_score": 82,
                "route": "auto",
                "quality_source": "llm",
                "trace_id": "trace-owner",
                "suggested_questions": [],
                "graded_docs": [],
            }
        )
        return future

    async def _wait_stream_future_result(**kwargs: Any) -> Any:
        wait_calls.append(kwargs)
        return await kwargs["fut"]

    async def _wait_stream_queue_event(**kwargs: Any) -> Any:
        raise AssertionError("ask-only stream path must not wait on queue events")

    monkeypatch.setattr(api_app, "_get_or_create_session", _get_session)
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "submit_stream_graph",
        _submit_stream_graph,
    )
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "wait_stream_future_result",
        _wait_stream_future_result,
    )
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "wait_stream_queue_event",
        _wait_stream_queue_event,
    )

    response = client.post(
        "/api/ask/stream",
        json={"question": "owner-stream"},
        headers={"Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    body = response.text
    assert "owned-stream" in body
    assert len(submit_calls) == 1
    assert callable(submit_calls[0]["operation"])
    assert len(wait_calls) == 1
    assert wait_calls[0]["timeout"] == 1.5
    assert wait_calls[0]["fut"].done()
    assert wait_calls[0]["release_capacity"] is conversation._release_pipeline_capacity


def test_stream_event_path_delegates_to_pipeline_runner(
    monkeypatch: pytest.MonkeyPatch,
    client,
    settings_factory,
) -> None:
    api_app = importlib.import_module("api.app")
    conversation = importlib.import_module("api.routers.conversation")
    submit_calls: list[dict[str, Any]] = []
    queue_wait_calls: list[dict[str, Any]] = []
    future_wait_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        api_app,
        "get_settings",
        lambda: settings_factory(
            streaming_enabled=True,
            streaming_rag_parity=True,
            request_timeout_sec=1.5,
            max_concurrent_pipelines=2,
        ),
    )
    api_app._db_retry_after = time.monotonic() + 60.0
    api_app._pipeline_semaphore = None

    class _Session:
        def __init__(self) -> None:
            self._history: list[dict[str, str]] = []

        def iter_ask_events(self, question: str, **kwargs: Any):
            _ = kwargs
            yield {
                "type": "status",
                "node": "retrieve",
                "source": "graph",
                "phase": "end",
            }
            yield {
                "type": "token",
                "token": "owned-",
                "token_source": "provider_generate",
            }
            yield {
                "type": "token",
                "token": "events",
                "token_source": "provider_generate",
            }
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": "owned-events"})
            yield {
                "type": "pipeline_result",
                "state": {
                    "answer": "owned-events",
                    "quality_score": 88,
                    "quality_source": "llm",
                    "route": "auto",
                    "trace_id": "trace-events-owner",
                    "suggested_questions": [],
                    "graded_docs": [],
                },
                "nodes": ["retrieve", "generate"],
            }

        def ask(self, question: str, **kwargs: Any) -> dict:
            raise AssertionError("event stream path must not fall back to ask()")

    async def _get_session(session_id, tenant_id="default"):
        return "stream-events-owner", _Session()

    def _submit_stream_graph(**kwargs: Any) -> Any:
        submit_calls.append(kwargs)
        operation = kwargs["operation"]
        operation()
        active_loop = kwargs.get("loop") or asyncio.get_running_loop()
        future = active_loop.create_future()
        future.set_result(None)
        return future

    async def _wait_stream_queue_event(**kwargs: Any) -> Any:
        queue_wait_calls.append(kwargs)
        return await kwargs["queue"].get()

    async def _wait_stream_future_result(**kwargs: Any) -> Any:
        future_wait_calls.append(kwargs)
        raise AssertionError("event stream path must not wait on ask-only future")

    monkeypatch.setattr(api_app, "_get_or_create_session", _get_session)
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "submit_stream_graph",
        _submit_stream_graph,
    )
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "wait_stream_queue_event",
        _wait_stream_queue_event,
    )
    monkeypatch.setattr(
        conversation.pipeline_runner,
        "wait_stream_future_result",
        _wait_stream_future_result,
    )

    response = client.post(
        "/api/ask/stream",
        json={"question": "owner-events"},
        headers={"Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    body = response.text
    assert '"type": "status"' in body
    assert '"node": "retrieve"' in body
    assert '"type": "token"' in body
    assert "owned-" in body
    assert "events" in body
    assert "owned-events" in body
    assert len(submit_calls) == 1
    assert callable(submit_calls[0]["operation"])
    assert len(queue_wait_calls) >= 1
    assert all(call["timeout"] == 1.5 for call in queue_wait_calls)
    assert all(
        call["release_capacity"] is conversation._release_pipeline_capacity
        for call in queue_wait_calls
    )
    assert future_wait_calls == []

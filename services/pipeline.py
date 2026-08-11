"""Single owner for pipeline execution, capacity, and orphan-work lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from monitoring import prometheus as prometheus_metrics

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Own sync/stream execution deadlines and pipeline-capacity lifecycle."""

    async def run_sync_with_deadline(
        self,
        *,
        executor: Any,
        operation: Callable[[], Any],
        timeout: float,
        semaphore: Any,
        release_capacity: Callable[[Any], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Any:
        """Run synchronous pipeline work and retain capacity past a timeout."""
        active_loop = loop or asyncio.get_running_loop()
        future = active_loop.run_in_executor(executor, operation)
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self.hold_capacity_until_future_done(
                loop=active_loop,
                fut=future,
                semaphore=semaphore,
                release_capacity=release_capacity,
            )
            raise

    def submit_stream_graph(
        self,
        *,
        executor: Any,
        operation: Callable[[], Any],
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Any:
        """Submit streaming graph/event work to the request executor."""
        active_loop = loop or asyncio.get_running_loop()
        return active_loop.run_in_executor(executor, operation)

    async def wait_stream_queue_event(
        self,
        *,
        queue: asyncio.Queue,
        timeout: float,
        fut: Any,
        semaphore: Any,
        release_capacity: Callable[[Any], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Any:
        """Wait for the next stream queue event; hand off capacity on timeout."""
        active_loop = loop or asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            self.hold_capacity_until_future_done(
                loop=active_loop,
                fut=fut,
                semaphore=semaphore,
                release_capacity=release_capacity,
            )
            raise

    async def wait_stream_future_result(
        self,
        *,
        fut: Any,
        timeout: float,
        semaphore: Any,
        release_capacity: Callable[[Any], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Any:
        """Wait for a shielded stream graph future; hand off capacity on timeout."""
        active_loop = loop or asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                asyncio.shield(fut),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self.hold_capacity_until_future_done(
                loop=active_loop,
                fut=fut,
                semaphore=semaphore,
                release_capacity=release_capacity,
            )
            raise

    def release_capacity(self, semaphore: Any) -> None:
        """Drop inflight gauge and release the semaphore best-effort."""
        try:
            prometheus_metrics.INFLIGHT_PIPELINES.dec()
        except Exception:
            pass
        try:
            semaphore.release()
        except Exception:
            pass

    def hold_capacity_until_future_done(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        fut: Any,
        semaphore: Any,
        release_capacity: Callable[[Any], None] | None = None,
    ) -> None:
        """Transfer capacity release to a thread-pool future callback."""
        try:
            prometheus_metrics.record_orphan_work_started()
        except Exception:
            logger.debug("Orphan work start metric failed", exc_info=True)

        release = release_capacity or self.release_capacity

        def _on_done(_fut: Any) -> None:
            try:
                prometheus_metrics.record_orphan_work_finished()
            except Exception:
                logger.debug("Orphan work finish metric failed", exc_info=True)
            release(semaphore)

        fut.add_done_callback(lambda done: loop.call_soon_threadsafe(_on_done, done))


pipeline_runner = PipelineRunner()

__all__ = ["PipelineRunner", "pipeline_runner"]

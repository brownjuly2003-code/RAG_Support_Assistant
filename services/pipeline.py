"""Single owner for pipeline capacity and orphan-work lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from monitoring import prometheus as prometheus_metrics

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Own semaphore release and orphaned-future capacity handoff."""

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

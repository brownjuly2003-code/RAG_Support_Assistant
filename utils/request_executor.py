"""Process-level bounded executor for sync pipeline / ask work.

Plan §3 / REL-01: replace per-request ``ThreadPoolExecutor(max_workers=1)``
with one shared pool. Capacity (pipeline semaphore) must be held until the
submitted work actually finishes — outer ``asyncio.wait_for`` only cancels
the *wait*, not the worker thread.

Workers mark themselves via ``threading.local`` so nested ``ask()`` wall-budget
paths do not re-submit onto the same pool (deadlock risk when saturated).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_max_workers: int | None = None
_worker_local = threading.local()

# Default aligns with MAX_CONCURRENT_PIPELINES when settings are unavailable.
_DEFAULT_MAX_WORKERS = 8


def _mark_request_worker() -> None:
    _worker_local.on_request_executor = True


def is_on_request_executor_thread() -> bool:
    """True when the current thread is a shared request-executor worker."""
    return bool(getattr(_worker_local, "on_request_executor", False))


def _resolve_max_workers(explicit: int | None = None) -> int:
    if explicit is not None and explicit > 0:
        return int(explicit)
    try:
        from config.settings import get_settings

        settings = get_settings()
        configured = int(getattr(settings, "request_executor_max_workers", 0) or 0)
        if configured > 0:
            return configured
        pipelines = int(getattr(settings, "max_concurrent_pipelines", 0) or 0)
        if pipelines > 0:
            return pipelines
    except Exception:
        pass
    return _DEFAULT_MAX_WORKERS


def get_request_executor(*, max_workers: int | None = None) -> ThreadPoolExecutor:
    """Return the process-wide request executor (lazy, thread-safe)."""
    global _executor, _max_workers
    desired = _resolve_max_workers(max_workers)
    with _lock:
        if _executor is None:
            _max_workers = desired
            _executor = ThreadPoolExecutor(
                max_workers=desired,
                thread_name_prefix="rag-request",
                initializer=_mark_request_worker,
            )
            logger.info(
                "Request executor started max_workers=%d",
                desired,
            )
            return _executor
        # Already running: do not shrink/grow mid-process (avoid surprise).
        if max_workers is not None and max_workers > 0 and max_workers != _max_workers:
            logger.warning(
                "Request executor already started max_workers=%s; ignore request for %s",
                _max_workers,
                max_workers,
            )
        return _executor


def submit_request(fn: Callable[..., T], /, *args: object, **kwargs: object) -> Future[T]:
    """Submit callable to the shared request executor."""
    executor = get_request_executor()
    return executor.submit(fn, *args, **kwargs)


def run_on_request_executor(
    fn: Callable[[], T],
    *,
    timeout_sec: float | None = None,
) -> T:
    """Run ``fn`` on the shared pool, or inline when already on a worker thread.

    When ``timeout_sec`` is set and exceeded, raises ``TimeoutError`` while the
    worker continues (non-cancellable graph). Callers that own capacity must
    keep that capacity until the underlying future completes — use
    ``submit_request`` + explicit future lifecycle for that path.
    """
    if is_on_request_executor_thread():
        if timeout_sec is not None and timeout_sec > 0:
            logger.warning(
                "Nested request-executor wall budget skipped (already on worker); "
                "running inline — outer deadline owns cancellation semantics"
            )
        return fn()

    future = submit_request(fn)
    if timeout_sec is None or timeout_sec <= 0:
        return future.result()
    try:
        return future.result(timeout=float(timeout_sec))
    except FuturesTimeout as exc:
        raise TimeoutError(
            f"request executor work exceeded {float(timeout_sec):.1f}s"
        ) from exc


def reset_request_executor_for_tests() -> None:
    """Shut down and clear the shared executor (test isolation only)."""
    global _executor, _max_workers
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=False)
        _executor = None
        _max_workers = None

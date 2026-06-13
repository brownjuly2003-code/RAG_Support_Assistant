"""Exponential backoff retry for Ollama network calls."""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any, Literal, TypeVar

T = TypeVar("T")
RetryEvent = Literal["attempt", "success", "retry", "exhausted"]
RetryCallback = Callable[[RetryEvent], None]

logger = logging.getLogger(__name__)

_RETRYABLE_EXC_NAMES = frozenset(
    {
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "NetworkError",
        "RemoteProtocolError",
        "ResponseError",
    }
)


def is_retryable_error(exc: BaseException) -> bool:
    """Return True when the exception looks like a transient network failure."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _RETRYABLE_EXC_NAMES:
            return True
    return False


def retry_with_backoff(
    fn: Callable[..., T],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 5.0,
    jitter: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = is_retryable_error,
    on_event: RetryCallback | None = None,
) -> Callable[..., T]:
    """Wrap `fn` with retry and exponential backoff."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def _emit(event: RetryEvent) -> None:
        if on_event is None:
            return
        try:
            on_event(event)
        except Exception:
            logger.exception("retry on_event callback raised")

    def wrapped(*args: Any, **kwargs: Any) -> T:
        last_exc: BaseException | None = None
        for attempt in range(max_attempts):
            _emit("attempt")
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                if not is_retryable(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    _emit("exhausted")
                    break
                _emit("retry")
                delay = min(base_delay_sec * (2 ** attempt), max_delay_sec)
                if jitter:
                    delay = min(delay * (0.5 + random.random()), max_delay_sec)
                logger.info(
                    "retry_with_backoff: attempt %d/%d failed (%s); sleeping %.2fs",
                    attempt + 1,
                    max_attempts,
                    type(exc).__name__,
                    delay,
                )
                sleep(delay)
            else:
                _emit("success")
                return result
        raise last_exc  # type: ignore[misc]

    return wrapped

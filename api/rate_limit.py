"""Shared request rate limiting primitives."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from monitoring import prometheus as prometheus_metrics

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
except ImportError:
    class RateLimitExceeded(Exception):
        pass

    class Limiter:  # type: ignore[no-redef]
        def __init__(self, key_func):
            self.key_func = key_func

        def limit(self, value: str):
            _ = value

            def decorator(func):
                return func

            return decorator

    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    def get_remote_address(request: Request | None) -> str:
        if request is None or request.client is None:
            return "unknown"
        return request.client.host


def _rate_limit_rejected(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    try:
        prometheus_metrics.record_rate_limit_rejection(request.url.path)
    except Exception:
        pass
    return _rate_limit_exceeded_handler(request, exc)


limiter = Limiter(key_func=get_remote_address)

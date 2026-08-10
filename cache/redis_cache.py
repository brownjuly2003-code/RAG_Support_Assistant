"""Redis cache with graceful degradation to an in-memory dict."""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_redis_client = None
_FALLBACK_CACHE_MAX = 1024
_fallback: OrderedDict[str, tuple[str, float]] = OrderedDict()
_fallback_lock = Lock()
_use_fallback = False


def _purge_expired_fallback(now: float) -> None:
    expired = [key for key, (_, expires_at) in _fallback.items() if expires_at <= now]
    for key in expired:
        _fallback.pop(key, None)


def _fallback_get(key: str) -> str | None:
    now = time.monotonic()
    with _fallback_lock:
        entry = _fallback.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= now:
            _fallback.pop(key, None)
            return None
        _fallback.move_to_end(key)
        return value


def _fallback_set(key: str, value: str, ttl_seconds: int) -> None:
    now = time.monotonic()
    with _fallback_lock:
        _purge_expired_fallback(now)
        if ttl_seconds <= 0:
            _fallback.pop(key, None)
            return
        _fallback[key] = (value, now + ttl_seconds)
        _fallback.move_to_end(key)
        while len(_fallback) > _FALLBACK_CACHE_MAX:
            _fallback.popitem(last=False)


def _fallback_delete(key: str) -> None:
    with _fallback_lock:
        _fallback.pop(key, None)


def _fallback_delete_pattern(pattern: str) -> int:
    import fnmatch

    now = time.monotonic()
    with _fallback_lock:
        _purge_expired_fallback(now)
        to_delete = [key for key in _fallback if fnmatch.fnmatch(key, pattern)]
        for key in to_delete:
            _fallback.pop(key, None)
        return len(to_delete)


def _get_redis():
    """Lazy init Redis connection."""
    global _redis_client, _use_fallback
    if _use_fallback:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        from config.settings import get_settings

        settings = get_settings()
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory fallback: %s", exc)
        _use_fallback = True
        return None


def cache_get(key: str) -> str | None:
    """Get a value from cache."""
    r = _get_redis()
    if r is not None:
        try:
            return r.get(key)
        except Exception as exc:
            logger.warning("Redis GET failed: %s", exc)
    return _fallback_get(key)


def cache_set(key: str, value: str, ttl_seconds: int = 3600) -> None:
    """Store a value in cache with TTL."""
    r = _get_redis()
    if r is not None:
        try:
            r.setex(key, ttl_seconds, value)
            return
        except Exception as exc:
            logger.warning("Redis SET failed: %s", exc)
    _fallback_set(key, value, ttl_seconds)


def cache_delete(key: str) -> None:
    """Delete a value from cache."""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(key)
        except Exception as exc:
            logger.warning("Redis DELETE failed: %s", exc)
    _fallback_delete(key)


def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a glob-style pattern."""
    r = _get_redis()
    deleted = 0
    if r is not None:
        try:
            for key in r.scan_iter(match=pattern, count=500):
                r.delete(key)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.warning("Redis SCAN/DEL failed: %s", exc)

    return deleted + _fallback_delete_pattern(pattern)


def cache_json_get(key: str) -> Any | None:
    """Get a JSON object from cache."""
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


def cache_json_set(key: str, value: Any, ttl_seconds: int = 3600) -> None:
    """Store a JSON object in cache."""
    cache_set(key, json.dumps(value, ensure_ascii=False), ttl_seconds)

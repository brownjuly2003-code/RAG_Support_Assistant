"""Redis cache with graceful degradation to an in-memory dict."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_redis_client = None
_fallback: dict[str, str] = {}
_use_fallback = False


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
    return _fallback.get(key)


def cache_set(key: str, value: str, ttl_seconds: int = 3600) -> None:
    """Store a value in cache with TTL."""
    r = _get_redis()
    if r is not None:
        try:
            r.setex(key, ttl_seconds, value)
            return
        except Exception as exc:
            logger.warning("Redis SET failed: %s", exc)
    _fallback[key] = value


def cache_delete(key: str) -> None:
    """Delete a value from cache."""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(key)
        except Exception as exc:
            logger.warning("Redis DELETE failed: %s", exc)
    _fallback.pop(key, None)


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

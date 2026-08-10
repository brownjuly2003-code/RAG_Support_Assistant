from __future__ import annotations

import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_state():
    from cache import redis_cache

    redis_cache._redis_client = None
    redis_cache._fallback.clear()
    redis_cache._redis_retry_at = 0.0
    redis_cache._redis_retry_delay_seconds = getattr(
        redis_cache, "_REDIS_RETRY_INITIAL_SECONDS", 1.0
    )
    redis_cache._use_fallback = False
    yield
    redis_cache._redis_client = None
    redis_cache._fallback.clear()
    redis_cache._redis_retry_at = 0.0
    redis_cache._redis_retry_delay_seconds = getattr(
        redis_cache, "_REDIS_RETRY_INITIAL_SECONDS", 1.0
    )
    redis_cache._use_fallback = False


def test_cache_falls_back_to_memory_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from cache import redis_cache

    class _Redis:
        @staticmethod
        def from_url(*args: Any, **kwargs: Any) -> object:
            _ = args, kwargs
            raise RuntimeError("redis down")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_Redis))

    redis_cache.cache_set("alpha", "one")
    redis_cache.cache_json_set("json", {"ok": True})
    redis_cache.cache_set("prefix:1", "a")
    redis_cache.cache_set("prefix:2", "b")
    redis_cache.cache_set("other", "c")

    assert redis_cache.cache_get("alpha") == "one"
    assert redis_cache.cache_json_get("json") == {"ok": True}
    assert redis_cache.cache_delete_pattern("prefix:*") == 2
    assert redis_cache.cache_get("prefix:1") is None
    assert redis_cache.cache_get("prefix:2") is None
    assert redis_cache.cache_get("other") == "c"

    redis_cache.cache_delete("alpha")
    assert redis_cache.cache_get("alpha") is None
    assert redis_cache._use_fallback is True
    assert "Redis unavailable, using in-memory fallback: redis down" in caplog.text


def test_cache_json_get_returns_none_for_missing_or_invalid_json() -> None:
    from cache import redis_cache

    assert redis_cache.cache_json_get("missing") is None

    redis_cache.cache_set("bad-json", "{not json")

    assert redis_cache.cache_json_get("bad-json") is None


def test_cache_uses_redis_client_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from cache import redis_cache

    calls: list[tuple[str, Any]] = []

    class _Client:
        def ping(self) -> None:
            calls.append(("ping", None))

        def get(self, key: str) -> str | None:
            calls.append(("get", key))
            return "stored" if key == "alpha" else None

        def setex(self, key: str, ttl_seconds: int, value: str) -> None:
            calls.append(("setex", (key, ttl_seconds, value)))

        def delete(self, key: str) -> None:
            calls.append(("delete", key))

        def scan_iter(self, *, match: str, count: int):
            calls.append(("scan_iter", (match, count)))
            yield "prefix:1"
            yield "prefix:2"

    client = _Client()

    class _Redis:
        @staticmethod
        def from_url(url: str, **kwargs: Any) -> _Client:
            calls.append(("from_url", (url, kwargs)))
            return client

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_Redis))
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(redis_url="redis://cache.local/0"),
    )

    redis_cache.cache_set("alpha", "one", ttl_seconds=12)
    assert redis_cache.cache_get("alpha") == "stored"
    redis_cache.cache_delete("alpha")
    assert redis_cache.cache_delete_pattern("prefix:*") == 2

    assert calls[0][0] == "from_url"
    assert calls[0][1][0] == "redis://cache.local/0"
    assert ("ping", None) in calls
    assert ("setex", ("alpha", 12, "one")) in calls
    assert ("get", "alpha") in calls
    assert ("delete", "alpha") in calls
    assert ("scan_iter", ("prefix:*", 500)) in calls
    assert ("delete", "prefix:1") in calls
    assert ("delete", "prefix:2") in calls


def test_cache_falls_back_when_redis_operations_fail(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from cache import redis_cache

    class _Client:
        def get(self, key: str) -> str | None:
            _ = key
            raise RuntimeError("get failed")

        def setex(self, key: str, ttl_seconds: int, value: str) -> None:
            _ = key, ttl_seconds, value
            raise RuntimeError("set failed")

        def delete(self, key: str) -> None:
            _ = key
            raise RuntimeError("delete failed")

        def scan_iter(self, *, match: str, count: int):
            _ = match, count
            raise RuntimeError("scan failed")
            yield ""

    redis_cache._use_fallback = True
    redis_cache.cache_set("alpha", "fallback-value")
    redis_cache.cache_set("prefix:1", "a")
    redis_cache._use_fallback = False
    redis_cache._redis_client = _Client()

    redis_cache.cache_set("beta", "stored-in-fallback")
    redis_cache._use_fallback = False
    redis_cache._redis_client = _Client()
    assert redis_cache.cache_get("alpha") == "fallback-value"
    redis_cache._use_fallback = False
    redis_cache._redis_client = _Client()
    redis_cache.cache_delete("alpha")
    assert redis_cache.cache_get("alpha") is None
    redis_cache._use_fallback = False
    redis_cache._redis_client = _Client()
    assert redis_cache.cache_delete_pattern("prefix:*") == 1
    assert redis_cache.cache_get("beta") == "stored-in-fallback"
    assert "Redis GET failed: get failed" in caplog.text
    assert "Redis SET failed: set failed" in caplog.text
    assert "Redis DELETE failed: delete failed" in caplog.text
    assert "Redis SCAN/DEL failed: scan failed" in caplog.text


def test_cache_delete_pattern_counts_partial_redis_and_fallback_deletes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from cache import redis_cache

    deleted_keys: list[str] = []

    class _Client:
        def delete(self, key: str) -> None:
            deleted_keys.append(key)

        def scan_iter(self, *, match: str, count: int):
            _ = match, count
            yield "prefix:redis"
            raise RuntimeError("scan interrupted")

    redis_cache._use_fallback = True
    redis_cache.cache_set("prefix:fallback", "value")
    redis_cache._use_fallback = False
    redis_cache._redis_client = _Client()

    assert redis_cache.cache_delete_pattern("prefix:*") == 2
    assert deleted_keys == ["prefix:redis"]
    assert "prefix:fallback" not in redis_cache._fallback
    assert "Redis SCAN/DEL failed: scan interrupted" in caplog.text


def test_connection_retries_with_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cache import redis_cache

    now = [0.0]
    connect_attempts: list[float] = []

    class _Client:
        def ping(self) -> None:
            return None

        def get(self, key: str) -> str:
            _ = key
            return "recovered"

    class _Redis:
        @staticmethod
        def from_url(*args: Any, **kwargs: Any) -> _Client:
            _ = args, kwargs
            connect_attempts.append(now[0])
            if len(connect_attempts) < 5:
                raise RuntimeError("redis down")
            return _Client()

    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(redis_cache, "_REDIS_RETRY_INITIAL_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(redis_cache, "_REDIS_RETRY_MAX_SECONDS", 4.0, raising=False)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_Redis))
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(redis_url="redis://cache.local/0"),
    )

    assert redis_cache.cache_get("alpha") is None
    now[0] = 0.9
    assert redis_cache.cache_get("alpha") is None
    now[0] = 1.0
    assert redis_cache.cache_get("alpha") is None
    now[0] = 2.9
    assert redis_cache.cache_get("alpha") is None
    now[0] = 3.0
    assert redis_cache.cache_get("alpha") is None
    now[0] = 6.9
    assert redis_cache.cache_get("alpha") is None
    now[0] = 7.0
    assert redis_cache.cache_get("alpha") is None
    now[0] = 10.9
    assert redis_cache.cache_get("alpha") is None
    now[0] = 11.0
    assert redis_cache.cache_get("alpha") == "recovered"

    assert connect_attempts == [0.0, 1.0, 3.0, 7.0, 11.0]
    assert redis_cache._use_fallback is False


def test_operation_failure_reconnects_after_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cache import redis_cache

    now = [100.0]
    failed_gets: list[str] = []
    connect_attempts: list[float] = []

    class _FailingClient:
        def get(self, key: str) -> str:
            failed_gets.append(key)
            raise RuntimeError("connection lost")

    class _RecoveredClient:
        def ping(self) -> None:
            return None

        def get(self, key: str) -> str:
            _ = key
            return "redis-value"

    class _Redis:
        @staticmethod
        def from_url(*args: Any, **kwargs: Any) -> _RecoveredClient:
            _ = args, kwargs
            connect_attempts.append(now[0])
            return _RecoveredClient()

    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_Redis))
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(redis_url="redis://cache.local/0"),
    )

    redis_cache._use_fallback = True
    redis_cache.cache_set("alpha", "fallback-value")
    redis_cache._use_fallback = False
    redis_cache._redis_client = _FailingClient()

    assert redis_cache.cache_get("alpha") == "fallback-value"
    now[0] = 100.9
    assert redis_cache.cache_get("alpha") == "fallback-value"
    assert failed_gets == ["alpha"]
    assert connect_attempts == []

    now[0] = 101.0
    assert redis_cache.cache_get("alpha") == "redis-value"
    assert connect_attempts == [101.0]
    assert redis_cache._use_fallback is False


def test_fallback_entry_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    from cache import redis_cache

    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    redis_cache._use_fallback = True

    redis_cache.cache_set("short-lived", "value", ttl_seconds=5)
    assert redis_cache.cache_get("short-lived") == "value"

    now[0] = 105.0
    assert redis_cache.cache_get("short-lived") is None
    assert "short-lived" not in redis_cache._fallback


def test_fallback_size_cap_evicts_least_recently_used() -> None:
    from cache import redis_cache

    redis_cache._use_fallback = True

    for index in range(1024):
        redis_cache.cache_set(f"key-{index}", str(index))
    assert redis_cache.cache_get("key-0") == "0"

    redis_cache.cache_set("key-1024", "1024")

    assert redis_cache.cache_get("key-0") == "0"
    assert redis_cache.cache_get("key-1") is None
    assert redis_cache.cache_get("key-1024") == "1024"
    assert len(redis_cache._fallback) == 1024

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_state():
    from cache import redis_cache

    redis_cache._redis_client = None
    redis_cache._fallback.clear()
    redis_cache._use_fallback = False
    yield
    redis_cache._redis_client = None
    redis_cache._fallback.clear()
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

    redis_cache._redis_client = _Client()
    redis_cache._fallback["alpha"] = "fallback-value"
    redis_cache._fallback["prefix:1"] = "a"

    redis_cache.cache_set("beta", "stored-in-fallback")
    assert redis_cache.cache_get("alpha") == "fallback-value"
    redis_cache.cache_delete("alpha")
    assert redis_cache.cache_get("alpha") is None
    assert redis_cache.cache_delete_pattern("prefix:*") == 1
    assert redis_cache.cache_get("beta") == "stored-in-fallback"
    assert "Redis GET failed: get failed" in caplog.text
    assert "Redis SET failed: set failed" in caplog.text
    assert "Redis DELETE failed: delete failed" in caplog.text
    assert "Redis SCAN/DEL failed: scan failed" in caplog.text

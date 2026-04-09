import asyncio

import app.cache as cache


def _reset_memory_cache() -> None:
    cache._memory_cache.clear()
    cache._memory_cache_bytes = 0


def test_memory_fallback_prunes_expired_entries_before_growing(monkeypatch):
    _reset_memory_cache()
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_ENTRIES", 8)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_BYTES", 1024)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_VALUE_BYTES", 1024)

    now = 100.0
    monkeypatch.setattr(cache.time, "monotonic", lambda: now)

    assert cache._memory_set("expired", "old", expire_seconds=1) is True

    now = 105.0
    assert cache._memory_set("fresh", "new", expire_seconds=60) is True

    assert cache._memory_get("expired") is None
    assert cache._memory_get("fresh") == "new"
    assert list(cache._memory_cache.keys()) == ["fresh"]


def test_memory_fallback_evicts_oldest_entries_when_capacity_is_exceeded(monkeypatch):
    _reset_memory_cache()
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_BYTES", 9)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_VALUE_BYTES", 9)

    assert cache._memory_set("a", "12345", expire_seconds=60) is True
    assert cache._memory_set("b", "1234", expire_seconds=60) is True
    assert cache._memory_set("c", "1234", expire_seconds=60) is True

    assert cache._memory_get("a") is None
    assert cache._memory_get("b") == "1234"
    assert cache._memory_get("c") == "1234"
    assert cache._memory_cache_bytes <= cache.MEMORY_CACHE_MAX_BYTES
    assert len(cache._memory_cache) <= cache.MEMORY_CACHE_MAX_ENTRIES


def test_memory_fallback_skips_values_that_are_too_large(monkeypatch):
    _reset_memory_cache()
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_ENTRIES", 8)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_BYTES", 16)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_VALUE_BYTES", 4)

    assert cache._memory_set("oversized", "12345", expire_seconds=60) is False
    assert cache._memory_get("oversized") is None
    assert cache._memory_cache_bytes == 0


def test_set_cached_accepts_ttl_alias_for_backward_compatibility(monkeypatch):
    _reset_memory_cache()
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_ENTRIES", 8)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_BYTES", 1024)
    monkeypatch.setattr(cache, "MEMORY_CACHE_MAX_VALUE_BYTES", 1024)

    async def _boom():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(cache, "get_redis", _boom)

    assert asyncio.run(cache.set_cached("ttl-key", "ttl-value", ttl=60)) is True
    assert cache._memory_get("ttl-key") == "ttl-value"

"""Shared test fixtures.

Endpoint response caching (app.cache) must not leak between tests or depend on
a developer's local Redis: force the in-process memory fallback and clear it
around every test so each test starts from a cold cache.
"""

import pytest

import app.cache as cache


def _clear_memory_cache() -> None:
    cache._memory_cache.clear()
    cache._memory_cache_bytes = 0


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    async def _redis_disabled():
        raise ConnectionError("redis disabled in tests")

    monkeypatch.setattr(cache, "get_redis", _redis_disabled)
    _clear_memory_cache()
    yield
    _clear_memory_cache()

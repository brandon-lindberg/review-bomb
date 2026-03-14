"""
Redis caching utilities for expensive queries.
"""

import json
import hashlib
import time
from fnmatch import fnmatch
from typing import Optional, Any, Dict, Tuple
from functools import wraps

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

# Global Redis client
_redis_client: Optional[redis.Redis] = None
_memory_cache: Dict[str, Tuple[str, float]] = {}


def _memory_get(key: str) -> Optional[str]:
    entry = _memory_cache.get(key)
    if not entry:
        return None

    value, expires_at = entry
    if expires_at < time.monotonic():
        _memory_cache.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: str, expire_seconds: int) -> bool:
    _memory_cache[key] = (value, time.monotonic() + max(expire_seconds, 1))
    return True


def _memory_delete(pattern: str) -> int:
    to_delete = [key for key in list(_memory_cache.keys()) if fnmatch(key, pattern)]
    for key in to_delete:
        _memory_cache.pop(key, None)
    return len(to_delete)


async def get_redis() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def get_cached(key: str) -> Optional[str]:
    """Get value from cache."""
    try:
        client = await get_redis()
        return await client.get(key)
    except Exception:
        # Fallback to process-local cache (dev/single-worker resilience)
        return _memory_get(key)


async def set_cached(key: str, value: str, expire_seconds: int = 300) -> bool:
    """Set value in cache with expiration."""
    try:
        client = await get_redis()
        await client.set(key, value, ex=expire_seconds)
        return True
    except Exception:
        # Fallback to process-local cache (dev/single-worker resilience)
        return _memory_set(key, value, expire_seconds)


async def delete_cached(pattern: str) -> int:
    """Delete keys matching pattern."""
    try:
        client = await get_redis()
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            return await client.delete(*keys)
        return 0
    except Exception:
        return _memory_delete(pattern)


def cache_key(*args, **kwargs) -> str:
    """Generate a cache key from arguments."""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()


async def close_redis():
    """Close the Redis client connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    _memory_cache.clear()


# Cache TTL constants (in seconds)
CACHE_TTL_HOT = 15  # 15 seconds - for high-traffic recent data
CACHE_TTL_SHORT = 60  # 1 minute - for frequently changing data
CACHE_TTL_MEDIUM = 300  # 5 minutes - for leaderboards, stats
CACHE_TTL_LONG = 900  # 15 minutes - for rarely changing data

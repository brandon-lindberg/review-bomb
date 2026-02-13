"""
Redis caching utilities for expensive queries.
"""

import json
import hashlib
from typing import Optional, Any
from functools import wraps

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

# Global Redis client
_redis_client: Optional[redis.Redis] = None


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
        # If Redis fails, return None (cache miss)
        return None


async def set_cached(key: str, value: str, expire_seconds: int = 300) -> bool:
    """Set value in cache with expiration."""
    try:
        client = await get_redis()
        await client.set(key, value, ex=expire_seconds)
        return True
    except Exception:
        # If Redis fails, continue without caching
        return False


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
        return 0


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


# Cache TTL constants (in seconds)
CACHE_TTL_SHORT = 60  # 1 minute - for frequently changing data
CACHE_TTL_MEDIUM = 300  # 5 minutes - for leaderboards, stats
CACHE_TTL_LONG = 900  # 15 minutes - for rarely changing data

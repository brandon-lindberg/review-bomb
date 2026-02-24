"""
Performance-oriented maintenance tasks (cache prewarming, snapshot refreshes).
"""

import asyncio

import dramatiq

from app.cache import close_redis
from app.services.cache_prewarm import prewarm_core_caches


def run_async(coro):
    """Helper to run async code in sync Dramatiq tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(close_redis())
        finally:
            loop.close()


@dramatiq.actor(max_retries=2, time_limit=900000)  # 15 minutes
def prewarm_core_api_caches(top_journalist_details: int = 10):
    """Prewarm caches for user-facing routes after deploys/data syncs."""
    run_async(_prewarm_core_api_caches(top_journalist_details))


async def _prewarm_core_api_caches(top_journalist_details: int = 10):
    await prewarm_core_caches(top_journalist_details=top_journalist_details)

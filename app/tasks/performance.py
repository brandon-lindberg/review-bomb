"""Performance-oriented maintenance tasks (cache prewarming, snapshot refreshes)."""

import dramatiq

from app.services.cache_prewarm import prewarm_core_caches
from app.tasks.runtime import QUEUE_PERFORMANCE, run_async_task


@dramatiq.actor(queue_name=QUEUE_PERFORMANCE, max_retries=2, time_limit=900000)  # 15 minutes
def prewarm_core_api_caches(top_journalist_details: int = 10):
    """Prewarm caches for user-facing routes after deploys/data syncs."""
    run_async_task(lambda: _prewarm_core_api_caches(top_journalist_details))


async def _prewarm_core_api_caches(top_journalist_details: int = 10):
    await prewarm_core_caches(top_journalist_details=top_journalist_details)

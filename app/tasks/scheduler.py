"""
Task scheduler configuration.

This module configures APScheduler to run recurring tasks for data synchronization
and disparity calculation.

To run the scheduler:
    python -m app.tasks.scheduler
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.tasks.sync import (
    sync_opencritic_incremental,
    sync_steam_scores,
    sync_metacritic_scores,
    match_games_to_platforms,
    sync_news_feeds,
)
from app.tasks.disparity import calculate_daily_snapshots
from app.tasks.performance import prewarm_core_api_caches


def create_scheduler() -> BlockingScheduler:
    """
    Create and configure the task scheduler.

    Returns:
        Configured BlockingScheduler instance
    """
    scheduler = BlockingScheduler()

    # OpenCritic incremental sync - every 6 hours
    scheduler.add_job(
        lambda: sync_opencritic_incremental.send(),
        trigger=IntervalTrigger(hours=6),
        id="sync_opencritic_incremental",
        name="Sync new reviews from OpenCritic",
        replace_existing=True,
    )

    # Steam scores sync - daily at 2 AM UTC
    scheduler.add_job(
        lambda: sync_steam_scores.send(),
        trigger=CronTrigger(hour=2, minute=0),
        id="sync_steam_scores",
        name="Sync Steam user scores",
        replace_existing=True,
    )

    # Metacritic scores sync - daily at 3 AM UTC
    scheduler.add_job(
        lambda: sync_metacritic_scores.send(),
        trigger=CronTrigger(hour=3, minute=0),
        id="sync_metacritic_scores",
        name="Sync Metacritic user scores",
        replace_existing=True,
    )

    # Game matching - daily at 1 AM UTC
    scheduler.add_job(
        lambda: match_games_to_platforms.send(),
        trigger=CronTrigger(hour=1, minute=0),
        id="match_games",
        name="Match games to Steam/Metacritic",
        replace_existing=True,
    )

    # Disparity snapshots - daily at 5 AM UTC (after all syncs complete)
    scheduler.add_job(
        lambda: calculate_daily_snapshots.send(),
        trigger=CronTrigger(hour=5, minute=0),
        id="calculate_snapshots",
        name="Calculate daily disparity snapshots",
        replace_existing=True,
    )

    # News RSS feeds - every 4 hours
    scheduler.add_job(
        lambda: sync_news_feeds.send(),
        trigger=IntervalTrigger(hours=4),
        id="sync_news_feeds",
        name="Sync gaming news RSS feeds",
        replace_existing=True,
    )

    # Cache prewarm - hourly to keep first user hit fast and refresh stored stats snapshot
    scheduler.add_job(
        lambda: prewarm_core_api_caches.send(10),
        trigger=IntervalTrigger(hours=1),
        id="prewarm_core_api_caches",
        name="Prewarm core API caches and site stats snapshot",
        replace_existing=True,
    )

    return scheduler


def main():
    """Run the scheduler."""
    print("Starting task scheduler...")
    print("Scheduled jobs:")
    print("  - OpenCritic incremental sync: every 6 hours")
    print("  - Steam scores sync: daily at 2 AM UTC")
    print("  - Metacritic scores sync: daily at 3 AM UTC")
    print("  - Game matching: daily at 1 AM UTC")
    print("  - Disparity snapshots: daily at 5 AM UTC")
    print("  - News RSS feeds: every 4 hours")
    print("  - Cache prewarm: every 1 hour")
    print()
    print("Press Ctrl+C to exit")

    scheduler = create_scheduler()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("Shutting down scheduler...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()

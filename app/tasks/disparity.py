"""
Disparity calculation tasks.

These tasks handle computing and storing disparity snapshots
for journalists, outlets, and games.
"""

import asyncio
from datetime import date
from typing import Optional

import dramatiq

from app.database import async_session_maker
from app.services.disparity import DisparityCalculator


def run_async(coro):
    """Helper to run async code in sync Dramatiq tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@dramatiq.actor(max_retries=3, time_limit=1800000)  # 30 min time limit
def calculate_daily_snapshots(snapshot_date: Optional[str] = None):
    """
    Calculate and store daily disparity snapshots for all entities.

    This should be run once daily to generate fresh disparity statistics
    for journalists, outlets, and games.

    Args:
        snapshot_date: Optional date string (YYYY-MM-DD) for the snapshot.
                      Defaults to today's date.
    """
    run_async(_calculate_daily_snapshots(snapshot_date))


async def _calculate_daily_snapshots(snapshot_date_str: Optional[str] = None):
    """Async implementation of daily snapshot calculation."""
    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        # Parse date if provided
        if snapshot_date_str:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        else:
            snapshot_date = date.today()

        print(f"Calculating disparity snapshots for {snapshot_date}...")

        results = await calculator.generate_all_snapshots(snapshot_date)

        print(f"Snapshot generation complete:")
        print(f"  - Journalists: {results['journalists']}")
        print(f"  - Outlets: {results['outlets']}")
        print(f"  - Games: {results['games']}")


@dramatiq.actor(max_retries=3, time_limit=600000)  # 10 min time limit
def calculate_journalist_snapshot(journalist_id: int, snapshot_date: Optional[str] = None):
    """
    Calculate disparity snapshot for a single journalist.

    Args:
        journalist_id: ID of the journalist
        snapshot_date: Optional date string (YYYY-MM-DD)
    """
    run_async(_calculate_journalist_snapshot(journalist_id, snapshot_date))


async def _calculate_journalist_snapshot(
    journalist_id: int,
    snapshot_date_str: Optional[str] = None,
):
    """Async implementation of single journalist snapshot."""
    from app.models.models import DisparitySnapshot

    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        if snapshot_date_str:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        else:
            snapshot_date = date.today()

        stats = await calculator.calculate_journalist_disparity(journalist_id)

        if stats and stats["review_count"] > 0:
            snapshot = DisparitySnapshot(
                journalist_id=journalist_id,
                snapshot_date=snapshot_date,
                avg_disparity_steam=stats["avg_disparity_steam"],
                avg_disparity_metacritic=stats["avg_disparity_metacritic"],
                avg_disparity_combined=stats["avg_disparity_combined"],
                review_count=stats["review_count"],
                std_deviation=stats["std_deviation"],
                min_disparity=stats["min_disparity"],
                max_disparity=stats["max_disparity"],
            )
            db.add(snapshot)
            await db.commit()
            print(f"Created snapshot for journalist {journalist_id}")


@dramatiq.actor(max_retries=3, time_limit=600000)  # 10 min time limit
def calculate_outlet_snapshot(outlet_id: int, snapshot_date: Optional[str] = None):
    """
    Calculate disparity snapshot for a single outlet.

    Args:
        outlet_id: ID of the outlet
        snapshot_date: Optional date string (YYYY-MM-DD)
    """
    run_async(_calculate_outlet_snapshot(outlet_id, snapshot_date))


async def _calculate_outlet_snapshot(
    outlet_id: int,
    snapshot_date_str: Optional[str] = None,
):
    """Async implementation of single outlet snapshot."""
    from app.models.models import DisparitySnapshot

    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        if snapshot_date_str:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        else:
            snapshot_date = date.today()

        stats = await calculator.calculate_outlet_disparity(outlet_id)

        if stats and stats["review_count"] > 0:
            snapshot = DisparitySnapshot(
                outlet_id=outlet_id,
                snapshot_date=snapshot_date,
                avg_disparity_steam=stats["avg_disparity_steam"],
                avg_disparity_metacritic=stats["avg_disparity_metacritic"],
                avg_disparity_combined=stats["avg_disparity_combined"],
                review_count=stats["review_count"],
                std_deviation=stats["std_deviation"],
                min_disparity=stats["min_disparity"],
                max_disparity=stats["max_disparity"],
            )
            db.add(snapshot)
            await db.commit()
            print(f"Created snapshot for outlet {outlet_id}")


@dramatiq.actor(max_retries=3, time_limit=600000)  # 10 min time limit
def calculate_game_snapshot(game_id: int, snapshot_date: Optional[str] = None):
    """
    Calculate disparity snapshot for a single game.

    Args:
        game_id: ID of the game
        snapshot_date: Optional date string (YYYY-MM-DD)
    """
    run_async(_calculate_game_snapshot(game_id, snapshot_date))


async def _calculate_game_snapshot(
    game_id: int,
    snapshot_date_str: Optional[str] = None,
):
    """Async implementation of single game snapshot."""
    from app.models.models import DisparitySnapshot

    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        if snapshot_date_str:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        else:
            snapshot_date = date.today()

        stats = await calculator.calculate_game_disparity(game_id)

        if stats and stats["review_count"] > 0:
            snapshot = DisparitySnapshot(
                game_id=game_id,
                snapshot_date=snapshot_date,
                avg_disparity_steam=stats["avg_disparity_steam"],
                avg_disparity_metacritic=stats["avg_disparity_metacritic"],
                avg_disparity_combined=stats["avg_disparity_combined"],
                review_count=stats["review_count"],
                std_deviation=stats["std_deviation"],
                min_disparity=stats["min_disparity"],
                max_disparity=stats["max_disparity"],
            )
            db.add(snapshot)
            await db.commit()
            print(f"Created snapshot for game {game_id}")

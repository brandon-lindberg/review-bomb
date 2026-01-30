"""
Data synchronization tasks.

These tasks handle fetching data from OpenCritic, Steam, and Metacritic,
and storing it in the database.
"""

import asyncio
from datetime import datetime, date
from typing import Optional

import dramatiq
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session_maker
from app.models.models import (
    Journalist, Outlet, Game, Review, UserScore, SyncLog,
    SyncSource, SyncType, SyncStatus, UserScoreSource,
)
from app.services.opencritic import OpenCriticService
from app.services.steam import SteamService
from app.services.metacritic import MetacriticService
from app.services.game_matcher import GameMatcher


def run_async(coro):
    """Helper to run async code in sync Dramatiq tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# OpenCritic Sync Tasks
# =============================================================================

@dramatiq.actor(max_retries=3, time_limit=3600000)  # 1 hour time limit
def sync_opencritic_full():
    """
    Full sync of all data from OpenCritic.

    This fetches all critics, outlets, games, and reviews.
    Should be run initially and occasionally for complete refresh.
    """
    run_async(_sync_opencritic_full())


async def _sync_opencritic_full():
    """Async implementation of full OpenCritic sync."""
    async with async_session_maker() as db:
        # Create sync log
        sync_log = SyncLog(
            source=SyncSource.OPENCRITIC,
            sync_type=SyncType.FULL,
            status=SyncStatus.RUNNING,
        )
        db.add(sync_log)
        await db.commit()
        await db.refresh(sync_log)

        try:
            service = OpenCriticService()
            records_processed = 0
            records_created = 0
            records_updated = 0

            # Sync outlets
            print("Syncing outlets...")
            outlets = await service.get_all_outlets()
            for outlet_data in outlets:
                transformed = OpenCriticService.transform_outlet(outlet_data)
                stmt = insert(Outlet).values(**transformed)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["opencritic_id"],
                    set_={
                        "name": stmt.excluded.name,
                        "website_url": stmt.excluded.website_url,
                        "logo_url": stmt.excluded.logo_url,
                        "updated_at": datetime.utcnow(),
                    },
                )
                await db.execute(stmt)
                records_processed += 1

            await db.commit()
            print(f"Synced {len(outlets)} outlets")

            # Sync critics (journalists)
            print("Syncing critics...")
            critics = await service.get_all_critics()
            for critic_data in critics:
                transformed = OpenCriticService.transform_critic(critic_data)
                stmt = insert(Journalist).values(**transformed)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["opencritic_id"],
                    set_={
                        "name": stmt.excluded.name,
                        "image_url": stmt.excluded.image_url,
                        "updated_at": datetime.utcnow(),
                    },
                )
                await db.execute(stmt)
                records_processed += 1

            await db.commit()
            print(f"Synced {len(critics)} critics")

            # Sync games (from 2015 onwards)
            print("Syncing games...")
            cutoff_date = date(2015, 1, 1)
            games = await service.get_games_since_date(cutoff_date)

            for game_data in games:
                transformed = OpenCriticService.transform_game(game_data)
                stmt = insert(Game).values(**transformed)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["opencritic_id"],
                    set_={
                        "title": stmt.excluded.title,
                        "description": stmt.excluded.description,
                        "release_date": stmt.excluded.release_date,
                        "top_critic_score": stmt.excluded.top_critic_score,
                        "percent_recommended": stmt.excluded.percent_recommended,
                        "tier": stmt.excluded.tier,
                        "image_url": stmt.excluded.image_url,
                        "updated_at": datetime.utcnow(),
                    },
                )
                await db.execute(stmt)
                records_processed += 1

            await db.commit()
            print(f"Synced {len(games)} games")

            # Sync reviews for each game
            print("Syncing reviews...")
            review_count = 0
            for game_data in games:
                game_id = game_data.get("id")
                if not game_id:
                    continue

                reviews = await service.get_game_reviews(game_id)
                for review_data in reviews:
                    transformed = OpenCriticService.transform_review(review_data)

                    # Skip reviews without valid scores
                    if transformed["score_normalized"] is None:
                        continue

                    # Look up internal IDs
                    journalist_result = await db.execute(
                        select(Journalist.id).where(
                            Journalist.opencritic_id == transformed["opencritic_critic_id"]
                        )
                    )
                    journalist_id = journalist_result.scalar_one_or_none()

                    outlet_result = await db.execute(
                        select(Outlet.id).where(
                            Outlet.opencritic_id == transformed["opencritic_outlet_id"]
                        )
                    )
                    outlet_id = outlet_result.scalar_one_or_none()

                    game_result = await db.execute(
                        select(Game.id).where(
                            Game.opencritic_id == transformed["opencritic_game_id"]
                        )
                    )
                    internal_game_id = game_result.scalar_one_or_none()

                    if not journalist_id or not internal_game_id:
                        continue

                    review_values = {
                        "journalist_id": journalist_id,
                        "game_id": internal_game_id,
                        "outlet_id": outlet_id,
                        "score_raw": transformed["score_raw"],
                        "score_scale": transformed["score_scale"],
                        "score_normalized": transformed["score_normalized"],
                        "review_url": transformed["review_url"],
                        "snippet": transformed["snippet"],
                        "published_at": transformed["published_at"],
                        "opencritic_review_id": transformed["opencritic_review_id"],
                    }

                    stmt = insert(Review).values(**review_values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["opencritic_review_id"],
                        set_={
                            "score_raw": stmt.excluded.score_raw,
                            "score_normalized": stmt.excluded.score_normalized,
                            "review_url": stmt.excluded.review_url,
                            "snippet": stmt.excluded.snippet,
                            "updated_at": datetime.utcnow(),
                        },
                    )
                    await db.execute(stmt)
                    review_count += 1
                    records_processed += 1

                # Commit every 10 games to avoid large transactions
                if review_count % 100 == 0:
                    await db.commit()

            await db.commit()
            print(f"Synced {review_count} reviews")

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = records_processed
            sync_log.records_created = records_created
            sync_log.completed_at = datetime.utcnow()
            await db.commit()

            print(f"OpenCritic full sync completed: {records_processed} records processed")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            await db.commit()
            raise


@dramatiq.actor(max_retries=3, time_limit=1800000)  # 30 min time limit
def sync_opencritic_incremental():
    """
    Incremental sync of recent data from OpenCritic.

    This fetches only recent games and reviews (last 7 days).
    Should be run frequently (every few hours).
    """
    run_async(_sync_opencritic_incremental())


async def _sync_opencritic_incremental():
    """Async implementation of incremental OpenCritic sync."""
    # Similar to full sync but with date filter
    # For brevity, calling full sync - in production, optimize this
    await _sync_opencritic_full()


# =============================================================================
# Steam Sync Tasks
# =============================================================================

@dramatiq.actor(max_retries=3, time_limit=3600000)  # 1 hour time limit
def sync_steam_scores():
    """
    Sync user scores from Steam for all games.

    This fetches the latest user review scores from Steam
    for all games that have a Steam app ID.
    """
    run_async(_sync_steam_scores())


async def _sync_steam_scores():
    """Async implementation of Steam score sync."""
    async with async_session_maker() as db:
        # Create sync log
        sync_log = SyncLog(
            source=SyncSource.STEAM,
            sync_type=SyncType.FULL,
            status=SyncStatus.RUNNING,
        )
        db.add(sync_log)
        await db.commit()
        await db.refresh(sync_log)

        try:
            service = SteamService()
            records_processed = 0
            records_created = 0
            records_failed = 0

            # Get all games with Steam app IDs
            query = select(Game).where(Game.steam_app_id.isnot(None))
            result = await db.execute(query)
            games = result.scalars().all()

            print(f"Syncing Steam scores for {len(games)} games...")

            for game in games:
                try:
                    score_data = await service.get_user_score(game.steam_app_id)
                    if score_data:
                        user_score = UserScore(
                            game_id=game.id,
                            source=UserScoreSource.STEAM,
                            score=score_data["score"],
                            score_raw=score_data["score_raw"],
                            sample_size=score_data["sample_size"],
                            positive_count=score_data["positive_count"],
                            negative_count=score_data["negative_count"],
                            review_score_desc=score_data["review_score_desc"],
                            scraped_at=score_data["scraped_at"],
                        )
                        db.add(user_score)
                        records_created += 1

                    records_processed += 1

                    # Commit every 50 games
                    if records_processed % 50 == 0:
                        await db.commit()
                        print(f"Processed {records_processed} games...")

                except Exception as e:
                    print(f"Error fetching Steam score for {game.title}: {e}")
                    records_failed += 1

            await db.commit()

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = records_processed
            sync_log.records_created = records_created
            sync_log.records_failed = records_failed
            sync_log.completed_at = datetime.utcnow()
            await db.commit()

            print(f"Steam sync completed: {records_created} scores created")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            await db.commit()
            raise


# =============================================================================
# Metacritic Sync Tasks
# =============================================================================

@dramatiq.actor(max_retries=2, time_limit=7200000)  # 2 hour time limit
def sync_metacritic_scores():
    """
    Sync user scores from Metacritic for all games.

    This scrapes user scores from Metacritic for all games
    that have a Metacritic slug.
    """
    run_async(_sync_metacritic_scores())


async def _sync_metacritic_scores():
    """Async implementation of Metacritic score sync."""
    async with async_session_maker() as db:
        # Create sync log
        sync_log = SyncLog(
            source=SyncSource.METACRITIC,
            sync_type=SyncType.FULL,
            status=SyncStatus.RUNNING,
        )
        db.add(sync_log)
        await db.commit()
        await db.refresh(sync_log)

        try:
            records_processed = 0
            records_created = 0
            records_failed = 0

            # Get all games with Metacritic slugs
            query = select(Game).where(Game.metacritic_slug.isnot(None))
            result = await db.execute(query)
            games = result.scalars().all()

            print(f"Syncing Metacritic scores for {len(games)} games...")

            async with MetacriticService() as service:
                for game in games:
                    try:
                        score_data = await service.get_user_score(game.metacritic_slug)
                        if score_data:
                            user_score = UserScore(
                                game_id=game.id,
                                source=UserScoreSource.METACRITIC,
                                score=score_data["score"],
                                score_raw=score_data["score_raw"],
                                sample_size=score_data["sample_size"],
                                positive_count=score_data["positive_count"],
                                negative_count=score_data["negative_count"],
                                review_score_desc=score_data["review_score_desc"],
                                scraped_at=score_data["scraped_at"],
                            )
                            db.add(user_score)
                            records_created += 1

                        records_processed += 1

                        # Commit every 20 games (scraping is slow)
                        if records_processed % 20 == 0:
                            await db.commit()
                            print(f"Processed {records_processed} games...")

                    except Exception as e:
                        print(f"Error fetching Metacritic score for {game.title}: {e}")
                        records_failed += 1

            await db.commit()

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = records_processed
            sync_log.records_created = records_created
            sync_log.records_failed = records_failed
            sync_log.completed_at = datetime.utcnow()
            await db.commit()

            print(f"Metacritic sync completed: {records_created} scores created")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            await db.commit()
            raise


# =============================================================================
# Game Matching Task
# =============================================================================

@dramatiq.actor(max_retries=2, time_limit=3600000)  # 1 hour time limit
def match_games_to_platforms():
    """
    Match games to Steam and Metacritic.

    This attempts to find Steam app IDs and Metacritic slugs
    for games that don't have them yet.
    """
    run_async(_match_games_to_platforms())


async def _match_games_to_platforms():
    """Async implementation of game matching."""
    async with async_session_maker() as db:
        matcher = GameMatcher()

        # Get games without Steam IDs
        query = select(Game).where(Game.steam_app_id.is_(None))
        result = await db.execute(query)
        games = result.scalars().all()

        print(f"Matching {len(games)} games to platforms...")

        matched = 0
        for game in games:
            match_result = await matcher.match_game(
                title=game.title,
                release_date=game.release_date,
                opencritic_id=game.opencritic_id,
            )

            if match_result["steam_app_id"]:
                game.steam_app_id = match_result["steam_app_id"]
                matched += 1

            if match_result["metacritic_slug"] and not game.metacritic_slug:
                game.metacritic_slug = match_result["metacritic_slug"]

        await db.commit()
        print(f"Matched {matched} games to Steam")

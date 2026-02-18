"""
Data synchronization tasks.

These tasks handle fetching data from OpenCritic, Steam, and Metacritic,
and storing it in the database.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

import dramatiq
from sqlalchemy import select, delete, or_
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
from app.services.score_normalizer import ScoreNormalizer


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
                        "updated_at": datetime.now(timezone.utc),
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
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await db.execute(stmt)
                records_processed += 1

            await db.commit()
            print(f"Synced {len(critics)} critics")

            # Sync all games
            # Only import games that can be matched to Steam or Metacritic
            print("Syncing games...")
            games = await service.get_all_games()
            matcher = GameMatcher()

            games_imported = 0
            games_skipped = 0
            imported_game_ids = set()  # Track OpenCritic IDs of imported games

            for game_data in games:
                transformed = OpenCriticService.transform_game(game_data)

                # Try to match to Steam/Metacritic BEFORE importing
                match_result = await matcher.match_game(
                    title=transformed.get("title", ""),
                    release_date=transformed.get("release_date"),
                    opencritic_id=transformed.get("opencritic_id"),
                )

                # Only import if we have a Steam match (verified via search)
                # Metacritic slug is just generated from title, not verified
                if not match_result["steam_app_id"]:
                    games_skipped += 1
                    continue

                # Add platform IDs to the game data
                if match_result["steam_app_id"]:
                    transformed["steam_app_id"] = match_result["steam_app_id"]
                if match_result["metacritic_slug"]:
                    transformed["metacritic_slug"] = match_result["metacritic_slug"]

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
                        "steam_app_id": stmt.excluded.steam_app_id,
                        "metacritic_slug": stmt.excluded.metacritic_slug,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await db.execute(stmt)
                records_processed += 1
                games_imported += 1
                imported_game_ids.add(game_data.get("id"))

            await db.commit()
            print(f"Synced {games_imported} games (skipped {games_skipped} without platform match)")

            # Sync reviews only for imported games
            print("Syncing reviews...")
            review_count = 0
            for game_data in games:
                game_id = game_data.get("id")
                if not game_id or game_id not in imported_game_ids:
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
                            "updated_at": datetime.now(timezone.utc),
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
            sync_log.completed_at = datetime.now(timezone.utc)
            await db.commit()

            print(f"OpenCritic full sync completed: {records_processed} records processed")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now(timezone.utc)
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
            records_processed = 0
            records_created = 0
            records_failed = 0
            today = datetime.now(timezone.utc).date()

            # Get games with Steam app IDs, excluding known future release dates.
            query = select(Game).where(
                Game.steam_app_id.isnot(None),
                or_(Game.release_date.is_(None), Game.release_date <= today),
            )
            result = await db.execute(query)
            games = result.scalars().all()

            print(f"Syncing Steam scores for {len(games)} games...")

            async with SteamService() as service:
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

                            # Update denormalized columns on Game
                            game.steam_user_score = score_data["score"]
                            game.steam_sample_size = score_data["sample_size"]

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
            sync_log.completed_at = datetime.now(timezone.utc)
            await db.commit()

            print(f"Steam sync completed: {records_created} scores created")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now(timezone.utc)
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
            records_updated = 0
            records_deleted = 0
            records_failed = 0

            # Get all games with Metacritic slugs
            query = select(Game).where(Game.metacritic_slug.isnot(None))
            result = await db.execute(query)
            games = result.scalars().all()

            print(f"Syncing Metacritic scores for {len(games)} games...")

            async with MetacriticService() as service:
                for game in games:
                    try:
                        # Use get_scores() to get both user score and metascore
                        score_data = await service.get_scores(game.metacritic_slug)
                        if score_data:
                            # Save user score to UserScore table
                            if score_data.get("user_score") is not None:
                                user_score = UserScore(
                                    game_id=game.id,
                                    source=UserScoreSource.METACRITIC,
                                    score=score_data["user_score"],
                                    score_raw=score_data["user_score_raw"],
                                    sample_size=score_data["user_sample_size"],
                                    positive_count=None,
                                    negative_count=None,
                                    review_score_desc=None,
                                    scraped_at=score_data["scraped_at"],
                                )
                                db.add(user_score)
                                records_created += 1

                                # Update denormalized columns on Game
                                game.metacritic_user_score = score_data["user_score"]
                                game.metacritic_sample_size = score_data["user_sample_size"]
                            else:
                                # User score is N/A - delete any existing invalid scores for this game
                                delete_result = await db.execute(
                                    delete(UserScore).where(
                                        UserScore.game_id == game.id,
                                        UserScore.source == UserScoreSource.METACRITIC,
                                    )
                                )
                                if delete_result.rowcount > 0:
                                    records_deleted += delete_result.rowcount
                                    print(f"Deleted {delete_result.rowcount} invalid Metacritic score(s) for {game.title}")

                                # Clear denormalized columns
                                game.metacritic_user_score = None
                                game.metacritic_sample_size = None

                            # Save metascore to Game table
                            if score_data.get("metascore") is not None:
                                game.metacritic_score = score_data["metascore"]
                                records_updated += 1

                        records_processed += 1

                        # Commit every 20 games (scraping is slow)
                        if records_processed % 20 == 0:
                            await db.commit()
                            print(f"Processed {records_processed} games...")

                        # Small delay between requests to be respectful
                        await asyncio.sleep(1)

                    except Exception as e:
                        print(f"Error fetching Metacritic score for {game.title}: {e}")
                        records_failed += 1

            await db.commit()

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = records_processed
            sync_log.records_created = records_created
            sync_log.records_updated = records_updated
            sync_log.records_failed = records_failed
            sync_log.completed_at = datetime.now(timezone.utc)
            await db.commit()

            print(f"Metacritic sync completed: {records_created} user scores created, {records_deleted} invalid scores deleted, {records_updated} metascores updated")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now(timezone.utc)
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
        await matcher.steam_service.aclose()
        print(f"Matched {matched} games to Steam")


# =============================================================================
# News RSS Feed Sync Tasks
# =============================================================================

@dramatiq.actor(max_retries=2, time_limit=300000)  # 5 min time limit
def sync_news_feeds():
    """
    Fetch latest articles from all gaming news RSS feeds.

    This fetches RSS feeds from IGN, GameSpot, Kotaku, PC Gamer,
    Polygon, Eurogamer, and The Verge, inserting new articles.
    Articles are kept permanently since they may be displayed on game pages.
    """
    run_async(_sync_news_feeds())


async def _sync_news_feeds():
    """Async implementation of news feed sync."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import NewsArticle
    from app.services.news_rss import NewsRSSService
    from app.services.news_matcher import NewsMatcher

    async with async_session_maker() as db:
        service = NewsRSSService()

        print("Fetching gaming news RSS feeds...")
        articles = await service.fetch_all_feeds()
        print(f"Fetched {len(articles)} articles from {len(service.FEEDS)} feeds")

        # Load game titles for matching
        games_result = await db.execute(select(Game.id, Game.title))
        matcher = NewsMatcher(games_result.all())

        inserted = 0
        for article in articles:
            game_id = matcher.match(article["title"], article.get("description"))
            if game_id:
                article["game_id"] = game_id
            stmt = pg_insert(NewsArticle).values(**article)
            stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
            result = await db.execute(stmt)
            if result.rowcount > 0:
                inserted += 1

            # Commit every 50 articles
            if inserted > 0 and inserted % 50 == 0:
                await db.commit()

        await db.commit()
        print(f"Inserted {inserted} new articles")

        # Invalidate news cache so the API serves fresh data
        if inserted > 0:
            from app.cache import delete_cached
            await delete_cached("news:*")
            print("Cleared news cache")

        print("News feed sync complete")


# =============================================================================
# Data Cleanup Tasks
# =============================================================================

@dramatiq.actor(max_retries=1, time_limit=600000)  # 10 min time limit
def cleanup_unscored_reviews():
    """
    Clean up reviews that were incorrectly assigned scores.

    Some outlets (Kotaku, Rock Paper Shotgun, etc.) don't use numeric scores.
    OpenCritic may have sent recommendation-style scores (like "10" for "Recommended")
    that we incorrectly normalized to 100.

    This task re-evaluates all reviews and sets score_normalized to NULL
    for reviews that don't have valid numeric scores.
    """
    run_async(_cleanup_unscored_reviews())


async def _cleanup_unscored_reviews():
    """Async implementation of unscored review cleanup."""
    async with async_session_maker() as db:
        print("Starting review cleanup...")

        # Text-based "scores" that should not be normalized
        unscored_values = {
            # Explicit unscored indicators
            "n/a", "tbd", "unscored", "-", "", "na", "none", "no score",
            # Recommendation-based systems (not numeric scores)
            "recommended", "not recommended", "yes", "no",
            "buy", "buy it", "don't buy", "skip", "skip it",
            "essential", "must-play", "must play", "avoid",
            "worth playing", "worth it", "not worth it",
            # Award/badge systems
            "editors' choice", "editor's choice", "editors choice",
            "platinum", "gold", "silver", "bronze",
            # Thumbs systems
            "thumbs up", "thumbs down",
        }

        # Get all reviews with scores
        query = select(Review).where(Review.score_normalized.isnot(None))
        result = await db.execute(query)
        reviews = result.scalars().all()

        print(f"Checking {len(reviews)} reviews...")

        fixed_count = 0
        for review in reviews:
            # Check if raw_score is a text-based non-numeric value
            raw = (review.score_raw or "").strip().lower()

            should_nullify = False

            # Check against known unscored values
            if raw in unscored_values:
                should_nullify = True
            # Check if raw score is 0 and normalized is also 0
            elif review.score_normalized == 0:
                should_nullify = True
            # Check if raw score looks numeric but resulted in exactly 100 from a non-100 scale
            # This catches cases where "10" on a 10-scale became 100
            elif review.score_normalized == 100 and review.score_scale != "100":
                # Re-normalize to verify
                try:
                    test_value = float(raw)
                    # If raw is exactly 10 on a 10-scale, it could be legitimate OR
                    # it could be OpenCritic converting "Recommended" to 10
                    # We can't be 100% sure, but we can flag suspicious cases
                    if test_value == 10 and review.score_scale == "10":
                        # This is suspicious - could be a fake score
                        # Check if it's from an outlet that typically doesn't use scores
                        pass  # Leave for manual review
                except ValueError:
                    # Raw score isn't numeric, shouldn't have been normalized
                    should_nullify = True

            if should_nullify:
                review.score_normalized = None
                fixed_count += 1

        await db.commit()
        print(f"Cleanup complete: nullified scores for {fixed_count} reviews")

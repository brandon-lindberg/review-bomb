"""
Sync orchestrator for OpenCritic data.

API Plan: MEGA ($50/mo)
- Unlimited requests
- 100 requests/second rate limit (enforced by rate_limiter in opencritic.py)
- 10GB bandwidth/month

Features:
- Continuous sync mode: fetches ALL games until complete
- Extracts critics/outlets from review responses to maximize data per request
- Saves progress periodically to allow resuming
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Set

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.models import (
    Game, Journalist, Outlet, Review, SyncState, SyncLog,
    SyncSource, SyncType, SyncStatus,
)
from app.services.opencritic import OpenCriticService
from app.services.score_normalizer import ScoreNormalizer
from app.services.game_matcher import GameMatcher
from app.services.steam import SteamService


class SyncOrchestrator:
    """
    Sync orchestrator for OpenCritic data.

    MEGA plan strategy (100 req/s, unlimited requests):
    - Fetches all game lists in bulk
    - Fetches all reviews without request limits
    - Extracts critics/outlets from review responses (no extra API calls)
    - Rate limiting handled by opencritic.py (100 req/s)
    """

    GAMES_PER_REQUEST = 50  # OpenCritic limit per request

    # State keys for persistence
    STATE_SYNCED_GAMES = "synced_opencritic_game_ids"
    STATE_GAMES_QUEUE = "games_queue"
    STATE_LAST_GAME_SKIP = "last_game_skip"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.service = OpenCriticService()
        self._request_count = 0  # For stats tracking only

    async def _get_state(self, key: str, default: str = "") -> str:
        """Get a sync state value."""
        result = await self.db.execute(
            select(SyncState.value).where(SyncState.key == key)
        )
        value = result.scalar_one_or_none()
        return value if value is not None else default

    async def _set_state(self, key: str, value: str) -> None:
        """Set a sync state value."""
        stmt = insert(SyncState).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": stmt.excluded.value, "updated_at": datetime.utcnow()},
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _get_synced_game_ids(self) -> Set[int]:
        """Get set of already-synced OpenCritic game IDs."""
        data = await self._get_state(self.STATE_SYNCED_GAMES, "[]")
        return set(json.loads(data))

    async def _add_synced_game_id(self, game_id: int) -> None:
        """Mark a game as synced."""
        synced = await self._get_synced_game_ids()
        synced.add(game_id)
        await self._set_state(self.STATE_SYNCED_GAMES, json.dumps(list(synced)))

    async def _get_games_queue(self) -> List[Dict[str, Any]]:
        """Get queue of games waiting to be synced."""
        data = await self._get_state(self.STATE_GAMES_QUEUE, "[]")
        return json.loads(data)

    async def _set_games_queue(self, queue: List[Dict[str, Any]]) -> None:
        """Update the games queue."""
        await self._set_state(self.STATE_GAMES_QUEUE, json.dumps(queue))

    async def _fetch_game_batch(self, skip: int = 0) -> tuple[List[Dict[str, Any]], bool]:
        """
        Fetch a batch of games from OpenCritic.
        
        Returns:
            Tuple of (games_list, success_flag)
            - If API returns data: (games, True)
            - If API returns empty but succeeded: ([], True) 
            - If API error after retries: ([], False)
        """
        print(f"Fetching games batch (skip={skip})...")
        games = await self.service.get_games(skip=skip, limit=self.GAMES_PER_REQUEST, sort="date")
        self._request_count += 1

        # If games is empty, it could be end of data OR API error
        # The API should return at least some games if skip is valid
        if not games:
            # If we're at a high skip value, empty might mean API error
            if skip > 0:
                return [], False  # Indicate potential API failure
            return [], True  # skip=0 returning empty means genuinely no data

        # Filter to games with valid data
        filtered = []
        for game in games:
            release_str = game.get("firstReleaseDate")
            if release_str:
                filtered.append(game)
            else:
                # Include games without release date if they have reviews
                if game.get("numReviews", 0) > 0:
                    filtered.append(game)

        return filtered, True

    async def _upsert_outlet_from_review(self, outlet_data: Dict[str, Any]) -> Optional[int]:
        """Insert/update outlet from review data and return internal ID."""
        if not outlet_data or not outlet_data.get("id"):
            return None

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
        await self.db.execute(stmt)

        # Get the ID
        result = await self.db.execute(
            select(Outlet.id).where(Outlet.opencritic_id == transformed["opencritic_id"])
        )
        return result.scalar_one_or_none()

    async def _upsert_journalist_from_review(self, author_data: Dict[str, Any]) -> Optional[int]:
        """Insert/update journalist from review author data and return internal ID."""
        if not author_data or not author_data.get("id"):
            return None

        transformed = OpenCriticService.transform_critic(author_data)
        stmt = insert(Journalist).values(**transformed)
        stmt = stmt.on_conflict_do_update(
            index_elements=["opencritic_id"],
            set_={
                "name": stmt.excluded.name,
                "image_url": stmt.excluded.image_url,
                "updated_at": datetime.utcnow(),
            },
        )
        await self.db.execute(stmt)

        # Get the ID
        result = await self.db.execute(
            select(Journalist.id).where(Journalist.opencritic_id == transformed["opencritic_id"])
        )
        return result.scalar_one_or_none()

    async def _upsert_game(self, game_data: Dict[str, Any]) -> Optional[int]:
        """Insert/update game and return internal ID."""
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
        await self.db.execute(stmt)

        # Get the ID
        result = await self.db.execute(
            select(Game.id).where(Game.opencritic_id == transformed["opencritic_id"])
        )
        return result.scalar_one_or_none()

    async def _sync_game_reviews(self, opencritic_game_id: int, internal_game_id: int) -> int:
        """
        Fetch and sync all reviews for a game.

        Also extracts and upserts critics/outlets from the review data.

        Returns number of reviews synced.
        """
        reviews = await self.service.get_game_reviews(opencritic_game_id)
        self._request_count += 1

        synced_count = 0
        for review_data in reviews:
            try:
                # Extract and upsert outlet from review
                outlet_data = review_data.get("Outlet", {})
                outlet_id = await self._upsert_outlet_from_review(outlet_data)

                # Extract and upsert author (journalist) from review
                authors = review_data.get("Authors", [])
                journalist_id = None
                if authors:
                    journalist_id = await self._upsert_journalist_from_review(authors[0])

                if not journalist_id:
                    continue

                # Transform and insert review
                transformed = OpenCriticService.transform_review(review_data)

                # Skip reviews without valid scores
                if transformed["score_normalized"] is None:
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
                await self.db.execute(stmt)
                synced_count += 1

            except Exception as e:
                print(f"Error processing review: {e}")
                continue

        await self.db.commit()
        return synced_count

    async def run_daily_sync(self, continuous: bool = True) -> Dict[str, Any]:
        """
        Run the sync.

        Args:
            continuous: If True, keep fetching until all games are synced.
                       If False, only fetch one batch.

        Returns stats about what was synced.
        """
        print(f"Starting sync (continuous={continuous})")

        # Create sync log
        sync_log = SyncLog(
            source=SyncSource.OPENCRITIC,
            sync_type=SyncType.FULL if continuous else SyncType.INCREMENTAL,
            status=SyncStatus.RUNNING,
        )
        self.db.add(sync_log)
        await self.db.commit()
        await self.db.refresh(sync_log)

        stats = {
            "games_synced": 0,
            "reviews_synced": 0,
            "journalists_discovered": 0,
            "outlets_discovered": 0,
            "requests_used": 0,
        }

        try:
            # Count existing entities for stats
            journalists_before = await self.db.execute(select(func.count()).select_from(Journalist))
            outlets_before = await self.db.execute(select(func.count()).select_from(Outlet))
            journalists_count_before = journalists_before.scalar() or 0
            outlets_count_before = outlets_before.scalar() or 0

            synced_ids = await self._get_synced_game_ids()
            games_queue = await self._get_games_queue()
            all_games_fetched = False

            # Main sync loop - keeps running until all games are fetched and processed
            while not all_games_fetched:
                # If queue is empty, fetch more games
                if not games_queue:
                    last_skip = int(await self._get_state(self.STATE_LAST_GAME_SKIP, "0"))

                    # Fetch a batch of games
                    batch, api_success = await self._fetch_game_batch(skip=last_skip)

                    if not batch:
                        if api_success:
                            # Empty batch with success = genuinely no more games
                            all_games_fetched = True
                            print("All games fetched from API")
                        else:
                            # API error - save state and exit gracefully
                            print(f"API error at skip={last_skip}. Run sync again to resume.")
                            stats["api_error"] = True
                        break

                    # Filter out already-synced games
                    games_queue = [
                        g for g in batch
                        if g.get("id") and g["id"] not in synced_ids
                    ]

                    await self._set_state(self.STATE_LAST_GAME_SKIP, str(last_skip + len(batch)))

                    if games_queue:
                        print(f"Fetched {len(batch)} games, {len(games_queue)} new to sync (skip={last_skip})")

                    # In non-continuous mode, only fetch once
                    if not continuous and not games_queue:
                        break

                # Process games from queue
                while games_queue:
                    game_data = games_queue.pop(0)
                    opencritic_game_id = game_data.get("id")

                    if not opencritic_game_id or opencritic_game_id in synced_ids:
                        continue

                    print(f"Syncing game: {game_data.get('name')} (OC ID: {opencritic_game_id})")

                    # Upsert game
                    internal_game_id = await self._upsert_game(game_data)
                    if not internal_game_id:
                        continue

                    # Fetch and sync reviews (uses 1 API request)
                    reviews_synced = await self._sync_game_reviews(opencritic_game_id, internal_game_id)

                    # Mark as synced
                    await self._add_synced_game_id(opencritic_game_id)
                    synced_ids.add(opencritic_game_id)

                    stats["games_synced"] += 1
                    stats["reviews_synced"] += reviews_synced

                    print(f"  Synced {reviews_synced} reviews")

                    # Save progress periodically
                    if stats["games_synced"] % 50 == 0:
                        await self._set_games_queue(games_queue)
                        print(f"Progress: {stats['games_synced']} games synced, {stats['reviews_synced']} reviews")

            # Count new entities
            journalists_after = await self.db.execute(select(func.count()).select_from(Journalist))
            outlets_after = await self.db.execute(select(func.count()).select_from(Outlet))

            stats["journalists_discovered"] = (journalists_after.scalar() or 0) - journalists_count_before
            stats["outlets_discovered"] = (outlets_after.scalar() or 0) - outlets_count_before
            stats["requests_used"] = self._request_count

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = stats["games_synced"]
            sync_log.records_created = stats["reviews_synced"]
            sync_log.completed_at = datetime.utcnow()
            await self.db.commit()

            print(f"\nSync complete:")
            print(f"  Games synced: {stats['games_synced']}")
            print(f"  Reviews synced: {stats['reviews_synced']}")
            print(f"  New journalists: {stats['journalists_discovered']}")
            print(f"  New outlets: {stats['outlets_discovered']}")
            print(f"  API requests used: {stats['requests_used']}")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            await self.db.commit()
            raise

        return stats

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and stats."""
        synced_ids = await self._get_synced_game_ids()
        games_queue = await self._get_games_queue()
        last_skip = int(await self._get_state(self.STATE_LAST_GAME_SKIP, "0"))

        # Get database counts
        games_count = await self.db.execute(select(func.count()).select_from(Game))
        reviews_count = await self.db.execute(select(func.count()).select_from(Review))
        journalists_count = await self.db.execute(select(func.count()).select_from(Journalist))
        outlets_count = await self.db.execute(select(func.count()).select_from(Outlet))

        return {
            "games_synced_total": len(synced_ids),
            "games_in_queue": len(games_queue),
            "last_skip_position": last_skip,
            "database_stats": {
                "games": games_count.scalar() or 0,
                "reviews": reviews_count.scalar() or 0,
                "journalists": journalists_count.scalar() or 0,
                "outlets": outlets_count.scalar() or 0,
            },
        }

    async def reset_sync_state(self) -> None:
        """Reset all sync state (for testing or starting fresh)."""
        # Set proper default values (not empty strings, which break JSON parsing)
        await self._set_state(self.STATE_SYNCED_GAMES, "[]")  # Valid empty JSON array
        await self._set_state(self.STATE_GAMES_QUEUE, "[]")   # Valid empty JSON array
        await self._set_state(self.STATE_LAST_GAME_SKIP, "0")
        print("Sync state reset")

    async def match_games_to_steam(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Match games in database to Steam app IDs.

        Args:
            limit: Optional limit on number of games to process

        Returns:
            Stats about matching results
        """
        from app.services.game_matcher import GameMatcher

        matcher = GameMatcher()

        # Get games without Steam IDs
        query = select(Game).where(Game.steam_app_id.is_(None))
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        games = result.scalars().all()

        print(f"Matching {len(games)} games to Steam...")

        stats = {
            "total": len(games),
            "matched": 0,
            "failed": 0,
        }

        for game in games:
            try:
                match_result = await matcher.match_game(
                    title=game.title,
                    release_date=game.release_date,
                    opencritic_id=game.opencritic_id,
                )

                if match_result["steam_app_id"]:
                    game.steam_app_id = match_result["steam_app_id"]
                    stats["matched"] += 1
                    print(f"  Matched: {game.title} -> Steam ID {match_result['steam_app_id']}")

                if match_result["metacritic_slug"] and not game.metacritic_slug:
                    game.metacritic_slug = match_result["metacritic_slug"]

                # Commit every 10 games
                if stats["matched"] % 10 == 0:
                    await self.db.commit()

            except Exception as e:
                print(f"  Error matching {game.title}: {e}")
                stats["failed"] += 1

        await self.db.commit()

        print(f"\nMatching complete: {stats['matched']} matched, {stats['failed']} failed")
        return stats


async def run_daily_sync(continuous: bool = True):
    """Convenience function to run the sync.
    
    Args:
        continuous: If True, keep fetching until all games are synced.
    """
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)
        return await orchestrator.run_daily_sync(continuous=continuous)


async def get_sync_status():
    """Convenience function to get sync status."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)
        return await orchestrator.get_sync_status()

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
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Set

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.models import (
    Game, Journalist, Outlet, Review, SyncState, SyncLog,
    SyncSource, SyncType, SyncStatus,
)
from app.public_ids import generate_public_id
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

    GAMES_PER_REQUEST = 20  # OpenCritic RapidAPI currently returns max 20 per page
    DEFAULT_STALE_PAGES_BEFORE_STOP = 5  # For fast incremental tail-scan runs
    DEFAULT_TAIL_SCAN_PAGES = 60  # Always scan this many tail pages before stale-stop
    RECENT_ID_RECON_WINDOW = 300  # Reconcile /game/{id} for recent IDs missing from /game list
    MATCH_NEW_GAME_GRACE_DAYS = 14  # Include newly added games even if release_date is old
    AUTO_REVIEW_REFRESH_DAYS = 14  # Rolling refresh window for existing games
    AUTO_REVIEW_REFRESH_LIMIT = None  # Refresh all games in the rolling window
    AUTO_REVIEW_REFRESH_MIN_HOURS = 6  # Skip games refreshed very recently

    # State keys for persistence
    STATE_SYNCED_GAMES = "synced_opencritic_game_ids"
    STATE_GAMES_QUEUE = "games_queue"
    STATE_LAST_GAME_SKIP = "last_game_skip"

    # Merged games: maps deprecated OpenCritic IDs to their canonical OpenCritic ID.
    # Reviews from deprecated games are redirected to the canonical game.
    # The deprecated game record is skipped during sync (not upserted).
    GAME_MERGES: Dict[int, int] = {
        # Overwatch 2 (OC 13288) merged back into Overwatch (OC 1673)
        # Blizzard dropped the "2" in Feb 2026, making OW2 just "Overwatch" again.
        13288: 1673,
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.service = OpenCriticService()
        self._request_count = 0  # For stats tracking only

    @staticmethod
    def _should_replace_release_date(
        existing_release_date: Optional[date],
        candidate_release_date: Optional[date],
        today: Optional[date] = None,
    ) -> bool:
        """
        Decide whether an incoming release date should replace the existing one.

        Guardrail: once a game has a known released date (<= today), do not allow
        OpenCritic to overwrite it with a future date, which can happen when the
        upstream API temporarily serves placeholder/fallback dates.
        """
        if candidate_release_date is None:
            return False
        if existing_release_date is None:
            return True
        if candidate_release_date == existing_release_date:
            return False

        if today is None:
            today = datetime.now(timezone.utc).date()

        if existing_release_date <= today and candidate_release_date > today:
            return False

        # For already-released dates, do not drift backward in time from
        # upstream placeholder/regression noise.
        if (
            existing_release_date <= today
            and candidate_release_date <= today
            and candidate_release_date < existing_release_date
        ):
            return False

        return True

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
            set_={"value": stmt.excluded.value, "updated_at": datetime.now(timezone.utc)},
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

    async def _fetch_game_batch(self, skip: int = 0) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch a batch of games from OpenCritic.

        Returns:
            Tuple of (games_list, api_count).
            api_count is the number of raw records returned by OpenCritic.
        """
        print(f"Fetching games batch (skip={skip})...")
        games = await self.service.get_games(skip=skip, limit=self.GAMES_PER_REQUEST, sort="date")
        self._request_count += 1

        if not games:
            return [], 0

        # Do not filter game list here: we want to ingest newly created titles
        # even if OpenCritic has not populated release/review metadata yet.
        return games, len(games)

    async def _upsert_outlet_from_review(self, outlet_data: Dict[str, Any]) -> Optional[int]:
        """Insert/update outlet from review data and return internal ID."""
        if not outlet_data or not outlet_data.get("id"):
            return None

        transformed = OpenCriticService.transform_outlet(outlet_data)
        stmt = insert(Outlet).values(public_id=generate_public_id(), **transformed)
        stmt = stmt.on_conflict_do_update(
            index_elements=["opencritic_id"],
            set_={
                "name": stmt.excluded.name,
                "website_url": stmt.excluded.website_url,
                "logo_url": stmt.excluded.logo_url,
                "updated_at": datetime.now(timezone.utc),
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
        stmt = insert(Journalist).values(public_id=generate_public_id(), **transformed)
        stmt = stmt.on_conflict_do_update(
            index_elements=["opencritic_id"],
            set_={
                "name": stmt.excluded.name,
                "image_url": stmt.excluded.image_url,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

        # Get the ID
        result = await self.db.execute(
            select(Journalist.id).where(Journalist.opencritic_id == transformed["opencritic_id"])
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _outlet_staff_opencritic_id(outlet_opencritic_id: int) -> int:
        """
        Build a deterministic synthetic OpenCritic critic ID for outlet-staff fallbacks.

        OpenCritic critic IDs are positive integers; we reserve a distant negative range
        for generated "Outlet Staff" pseudo-critics so reviews without author data can
        still be ingested and associated with a stable journalist row.
        """
        return -(1_000_000_000 + int(outlet_opencritic_id))

    async def _upsert_outlet_staff_journalist(
        self,
        outlet_data: Dict[str, Any],
    ) -> Optional[int]:
        """
        Upsert a deterministic pseudo-journalist for reviews that have no author.

        This preserves scored reviews where OpenCritic omits Authors while still
        satisfying our non-null Review.journalist_id constraint.
        """
        if not outlet_data:
            return None

        outlet_opencritic_id = outlet_data.get("id")
        outlet_name = (outlet_data.get("name") or "").strip() or "Unknown Outlet"
        pseudo_name = f"{outlet_name} Staff"

        synthetic_oc_id = None
        if outlet_opencritic_id is not None:
            try:
                synthetic_oc_id = self._outlet_staff_opencritic_id(int(outlet_opencritic_id))
            except (TypeError, ValueError):
                synthetic_oc_id = None

        if synthetic_oc_id is not None:
            stmt = insert(Journalist).values(
                public_id=generate_public_id(),
                name=pseudo_name,
                opencritic_id=synthetic_oc_id,
                image_url=None,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["opencritic_id"],
                set_={
                    "name": stmt.excluded.name,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(stmt)
            result = await self.db.execute(
                select(Journalist.id).where(Journalist.opencritic_id == synthetic_oc_id)
            )
            return result.scalar_one_or_none()

        # Last-resort fallback when outlet has no numeric OpenCritic ID.
        result = await self.db.execute(
            select(Journalist.id).where(
                Journalist.opencritic_id.is_(None),
                Journalist.name == pseudo_name,
            ).limit(1)
        )
        existing_id = result.scalar_one_or_none()
        if existing_id:
            return existing_id

        stmt = insert(Journalist).values(
            public_id=generate_public_id(),
            name=pseudo_name,
            opencritic_id=None,
            image_url=None,
        )
        await self.db.execute(stmt)
        result = await self.db.execute(
            select(Journalist.id).where(
                Journalist.opencritic_id.is_(None),
                Journalist.name == pseudo_name,
            ).order_by(Journalist.id.desc()).limit(1)
        )
        return result.scalars().first()

    async def _upsert_game(self, game_data: Dict[str, Any]) -> Optional[int]:
        """Insert/update game and return internal ID."""
        transformed = OpenCriticService.transform_game(game_data)
        stmt = insert(Game).values(public_id=generate_public_id(), **transformed)
        today = datetime.now(timezone.utc).date()
        incoming_release_date = stmt.excluded.release_date
        preserve_existing_released_date = and_(
            Game.release_date.isnot(None),
            Game.release_date <= today,
            incoming_release_date.isnot(None),
            incoming_release_date > today,
        )
        preserve_existing_backward_past_shift = and_(
            Game.release_date.isnot(None),
            Game.release_date <= today,
            incoming_release_date.isnot(None),
            incoming_release_date <= today,
            incoming_release_date < Game.release_date,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["opencritic_id"],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                # Keep existing date when OpenCritic omits it temporarily,
                # and prevent future placeholder dates from replacing known released dates.
                "release_date": case(
                    (or_(preserve_existing_released_date, preserve_existing_backward_past_shift), Game.release_date),
                    else_=func.coalesce(
                        incoming_release_date,
                        Game.release_date,
                    ),
                ),
                "top_critic_score": stmt.excluded.top_critic_score,
                "percent_recommended": stmt.excluded.percent_recommended,
                "tier": stmt.excluded.tier,
                "image_url": stmt.excluded.image_url,
                "updated_at": datetime.now(timezone.utc),
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
        # Track journalist/outlet published_at for last_review_at updates
        journalist_latest: Dict[int, datetime] = {}
        outlet_latest: Dict[int, datetime] = {}

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

                # OpenCritic sometimes emits valid scored reviews without Authors.
                # Preserve these via a stable per-outlet pseudo-journalist.
                if not journalist_id:
                    journalist_id = await self._upsert_outlet_staff_journalist(outlet_data)

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
                        "journalist_id": stmt.excluded.journalist_id,
                        "game_id": stmt.excluded.game_id,
                        "outlet_id": stmt.excluded.outlet_id,
                        "score_raw": stmt.excluded.score_raw,
                        "score_scale": stmt.excluded.score_scale,
                        "score_normalized": stmt.excluded.score_normalized,
                        "review_url": stmt.excluded.review_url,
                        "snippet": stmt.excluded.snippet,
                        "published_at": stmt.excluded.published_at,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await self.db.execute(stmt)
                synced_count += 1

                # Track latest published_at per journalist/outlet
                # Guard against obviously wrong future dates from OpenCritic
                pub_at = transformed.get("published_at")
                max_reasonable_date = datetime.now(timezone.utc) + timedelta(days=30)
                if pub_at and pub_at <= max_reasonable_date:
                    if journalist_id not in journalist_latest or pub_at > journalist_latest[journalist_id]:
                        journalist_latest[journalist_id] = pub_at
                    if outlet_id and (outlet_id not in outlet_latest or pub_at > outlet_latest[outlet_id]):
                        outlet_latest[outlet_id] = pub_at
                elif pub_at and pub_at > max_reasonable_date:
                    print(f"Warning: Skipping future date {pub_at} for review {transformed.get('opencritic_review_id')}")

            except Exception as e:
                print(f"Error processing review: {e}")
                continue

        # Update last_review_at on journalists and outlets
        for j_id, latest in journalist_latest.items():
            j_obj = await self.db.get(Journalist, j_id)
            if j_obj and (j_obj.last_review_at is None or latest > j_obj.last_review_at):
                j_obj.last_review_at = latest

        for o_id, latest in outlet_latest.items():
            o_obj = await self.db.get(Outlet, o_id)
            if o_obj and (o_obj.last_review_at is None or latest > o_obj.last_review_at):
                o_obj.last_review_at = latest

        await self.db.commit()
        return synced_count

    async def _update_game_critic_aggregates(self, internal_game_id: int) -> None:
        """
        Recompute denormalized critic aggregates for a game from Review rows.

        This keeps avg_critic_score and critic_review_count current during sync,
        so a separate backfill is not required for newly synced games.
        """
        result = await self.db.execute(
            select(
                func.avg(Review.score_normalized),
                func.count(Review.id),
            ).where(
                Review.game_id == internal_game_id,
                Review.score_normalized.isnot(None),
            )
        )
        avg_score_raw, review_count = result.first() or (None, 0)

        game_obj = await self.db.get(Game, internal_game_id)
        if not game_obj:
            return

        if review_count and avg_score_raw is not None:
            game_obj.avg_critic_score = Decimal(str(round(float(avg_score_raw), 2)))
            game_obj.critic_review_count = int(review_count)
        else:
            game_obj.avg_critic_score = None
            game_obj.critic_review_count = 0

    async def _reconcile_recent_id_window(self, synced_ids: Set[int]) -> Dict[str, int]:
        """
        Reconcile recent OpenCritic IDs via direct /game/{id} calls.

        OpenCritic's paginated /game listing can omit some titles even though
        /game/{id} and search endpoints return them. This catches those gaps.
        """
        if not synced_ids:
            return {"discovered": 0, "games_synced": 0, "reviews_synced": 0}

        max_seen_id = max(synced_ids)
        start_id = max(1, max_seen_id - self.RECENT_ID_RECON_WINDOW)
        print(
            f"Reconciling direct OpenCritic IDs {start_id}-{max_seen_id} "
            f"for out-of-list games..."
        )

        stats = {
            "discovered": 0,
            "games_synced": 0,
            "reviews_synced": 0,
        }

        for opencritic_game_id in range(start_id, max_seen_id + 1):
            if opencritic_game_id in synced_ids:
                continue

            game_data = await self.service.get_game(opencritic_game_id)
            self._request_count += 1
            if not game_data or not game_data.get("id"):
                continue

            stats["discovered"] += 1
            print(
                f"Discovered out-of-list game: {game_data.get('name')} "
                f"(OC ID: {opencritic_game_id})"
            )

            # Handle deprecated merged IDs the same way as the main sync loop.
            if opencritic_game_id in self.GAME_MERGES:
                canonical_oc_id = self.GAME_MERGES[opencritic_game_id]
                canonical_result = await self.db.execute(
                    select(Game.id).where(Game.opencritic_id == canonical_oc_id)
                )
                canonical_game_id = canonical_result.scalar_one_or_none()
                if canonical_game_id:
                    reviews_synced = await self._sync_game_reviews(
                        opencritic_game_id, canonical_game_id
                    )
                    await self._update_game_critic_aggregates(canonical_game_id)
                    await self._add_synced_game_id(opencritic_game_id)
                    synced_ids.add(opencritic_game_id)
                    stats["reviews_synced"] += reviews_synced
                    print(f"  Redirected {reviews_synced} reviews to canonical game")
                    continue

            internal_game_id = await self._upsert_game(game_data)
            if not internal_game_id:
                continue

            reviews_synced = await self._sync_game_reviews(
                opencritic_game_id, internal_game_id
            )
            await self._update_game_critic_aggregates(internal_game_id)

            game_obj = await self.db.get(Game, internal_game_id)
            if game_obj:
                game_obj.last_review_sync_at = datetime.now(timezone.utc)

            await self._add_synced_game_id(opencritic_game_id)
            synced_ids.add(opencritic_game_id)

            stats["games_synced"] += 1
            stats["reviews_synced"] += reviews_synced
            print(f"  Synced {reviews_synced} reviews")

        return stats

    async def _refresh_recent_unreleased_games(
        self, synced_ids: Set[int]
    ) -> Dict[str, int]:
        """
        Recheck all games with unknown/future release dates.

        Some titles are discovered pre-release (or with missing release date),
        then later get metadata corrections. Refresh them explicitly so release
        dates are corrected as titles ship.
        """
        stats = {
            "games_checked": 0,
            "games_updated": 0,
            "release_dates_updated": 0,
            "reviews_synced": 0,
        }
        if not synced_ids:
            return stats

        today = datetime.now(timezone.utc).date()

        candidates_result = await self.db.execute(
            select(Game).where(
                Game.opencritic_id.isnot(None),
                or_(
                    Game.release_date.is_(None),
                    Game.release_date > today,
                ),
            )
            .order_by(
                Game.release_date.asc().nulls_first(),
                Game.opencritic_id.desc().nulls_last(),
                Game.id.desc(),
            )
        )
        candidates = candidates_result.scalars().all()
        if not candidates:
            return stats

        print(
            f"Refreshing {len(candidates)} games with unknown/future "
            "release dates..."
        )

        for game in candidates:
            opencritic_game_id = game.opencritic_id
            if not opencritic_game_id:
                continue

            stats["games_checked"] += 1
            old_release_date = game.release_date
            metadata_updated = False

            game_data = await self.service.get_game(opencritic_game_id)
            self._request_count += 1
            if game_data:
                transformed = OpenCriticService.transform_game(game_data)

                if transformed.get("title") and transformed["title"] != game.title:
                    game.title = transformed["title"]
                    metadata_updated = True

                if (
                    transformed.get("description") is not None
                    and transformed["description"] != game.description
                ):
                    game.description = transformed["description"]
                    metadata_updated = True

                new_release_date = transformed.get("release_date")
                if self._should_replace_release_date(
                    game.release_date,
                    new_release_date,
                    today=today,
                ):
                    game.release_date = new_release_date
                    metadata_updated = True
                    stats["release_dates_updated"] += 1

                for field in (
                    "top_critic_score",
                    "percent_recommended",
                    "tier",
                    "image_url",
                ):
                    new_value = transformed.get(field)
                    if new_value is not None and new_value != getattr(game, field):
                        setattr(game, field, new_value)
                        metadata_updated = True

            reviews_synced = await self._sync_game_reviews(opencritic_game_id, game.id)
            await self._update_game_critic_aggregates(game.id)
            stats["reviews_synced"] += reviews_synced

            if reviews_synced > 0:
                game.last_review_sync_at = datetime.now(timezone.utc)

            if metadata_updated:
                stats["games_updated"] += 1
                if old_release_date != game.release_date:
                    print(
                        f"  Release date updated: {game.title} "
                        f"({old_release_date} -> {game.release_date})"
                    )

            await self.db.commit()

        return stats

    async def run_daily_sync(
        self,
        continuous: bool = True,
        full_scan: bool = False,
        stale_pages_before_stop: int = DEFAULT_STALE_PAGES_BEFORE_STOP,
        auto_refresh_recent_reviews: bool = True,
        review_refresh_days: int = AUTO_REVIEW_REFRESH_DAYS,
        review_refresh_limit: Optional[int] = AUTO_REVIEW_REFRESH_LIMIT,
        review_refresh_min_hours: int = AUTO_REVIEW_REFRESH_MIN_HOURS,
    ) -> Dict[str, Any]:
        """
        Run the sync.

        Args:
            continuous: If True, keep fetching until all games are synced.
                       If False, only fetch one batch.
            full_scan: If True, always traverse the full OpenCritic catalog.
            stale_pages_before_stop: In incremental mode, stop after this many
                consecutive pages contain no unsynced game IDs. Set to 0 to disable.
            auto_refresh_recent_reviews: If True, also refresh recent existing games
                so new critic reviews are captured after initial game ingest.
            review_refresh_days: Release/created window used for auto refresh.
            review_refresh_limit: Max games to refresh automatically per run.
            review_refresh_min_hours: Skip games refreshed within this many hours.

        Returns stats about what was synced.
        """
        tail_scan_mode = continuous and not full_scan
        use_stale_stop = tail_scan_mode and stale_pages_before_stop > 0
        print(
            "Starting sync "
            f"(continuous={continuous}, full_scan={full_scan}, "
            f"stale_pages_before_stop={stale_pages_before_stop}, "
            f"auto_refresh_recent_reviews={auto_refresh_recent_reviews})"
        )

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
            "id_reconcile_discovered": 0,
            "release_dates_updated": 0,
            "unreleased_games_rechecked": 0,
            "recent_reviews_refreshed_games": 0,
            "recent_reviews_refreshed_reviews": 0,
            "recent_reviews_refresh_failed": 0,
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
            last_skip = int(await self._get_state(self.STATE_LAST_GAME_SKIP, "0"))
            stale_pages_seen = 0
            pages_fetched = 0
            min_pages_before_stale = 0

            # OpenCritic `sort=date` is oldest-first, so new games appear near
            # the end of pagination. Non-full scans start near the tail.
            if tail_scan_mode:
                estimated_total = max(last_skip, len(synced_ids))
                backtrack_pages = max(
                    self.DEFAULT_TAIL_SCAN_PAGES,
                    stale_pages_before_stop,
                )
                next_skip = max(0, estimated_total - (backtrack_pages * self.GAMES_PER_REQUEST))
                min_pages_before_stale = backtrack_pages if use_stale_stop else 0
                print(
                    f"Scanning near catalog tail (start skip={next_skip}, "
                    f"estimated total={estimated_total}, tail pages={backtrack_pages})"
                )
            else:
                next_skip = 0
                if continuous and full_scan:
                    print("Running full catalog scan from skip=0.")

            # Main sync loop - keeps running until all games are fetched and processed
            while not all_games_fetched:
                # If queue is empty, fetch more games
                if not games_queue:
                    # Fetch a batch of games
                    batch, api_count = await self._fetch_game_batch(skip=next_skip)
                    pages_fetched += 1

                    if api_count == 0:
                        # End of list for current scan.
                        all_games_fetched = True
                        print("All games fetched from API")
                        break

                    # Filter out already-synced games
                    games_queue = [
                        g for g in batch
                        if g.get("id") and g["id"] not in synced_ids
                    ]
                    new_games_in_batch = len(games_queue)

                    next_skip += api_count
                    await self._set_state(self.STATE_LAST_GAME_SKIP, str(next_skip))

                    if games_queue:
                        print(
                            f"Fetched {api_count} games, {new_games_in_batch} new to sync "
                            f"(skip={next_skip - api_count})"
                        )
                    elif use_stale_stop:
                        if pages_fetched >= min_pages_before_stale:
                            stale_pages_seen += 1
                            print(
                                f"Fetched {api_count} games, 0 new to sync "
                                f"(stale page {stale_pages_seen}/{stale_pages_before_stop})"
                            )
                            if stale_pages_seen >= stale_pages_before_stop:
                                all_games_fetched = True
                                print(
                                    "Stopping early after consecutive stale pages; "
                                    "run with --full-scan for a complete sweep."
                                )
                                break
                        else:
                            print(
                                f"Fetched {api_count} games, 0 new to sync "
                                f"(warming tail window {pages_fetched}/{min_pages_before_stale})"
                            )
                    else:
                        print(
                            f"Fetched {api_count} games, 0 new to sync "
                            f"(skip={next_skip - api_count})"
                        )

                    if new_games_in_batch > 0:
                        stale_pages_seen = 0

                    # In non-continuous mode, only fetch once
                    if not continuous and not games_queue:
                        break

                # Process games from queue
                while games_queue:
                    game_data = games_queue.pop(0)
                    opencritic_game_id = game_data.get("id")

                    if not opencritic_game_id or opencritic_game_id in synced_ids:
                        continue

                    # Check if this game has been merged into another
                    if opencritic_game_id in self.GAME_MERGES:
                        canonical_oc_id = self.GAME_MERGES[opencritic_game_id]
                        # Find canonical game's internal ID
                        canonical_result = await self.db.execute(
                            select(Game.id).where(Game.opencritic_id == canonical_oc_id)
                        )
                        canonical_game_id = canonical_result.scalar_one_or_none()
                        if canonical_game_id:
                            print(f"Redirecting merged game: {game_data.get('name')} (OC {opencritic_game_id}) -> canonical OC {canonical_oc_id}")
                            # Fetch reviews from the deprecated OC entry and attach to canonical game
                            reviews_synced = await self._sync_game_reviews(opencritic_game_id, canonical_game_id)
                            await self._update_game_critic_aggregates(canonical_game_id)
                            await self._add_synced_game_id(opencritic_game_id)
                            synced_ids.add(opencritic_game_id)
                            stats["reviews_synced"] += reviews_synced
                            print(f"  Redirected {reviews_synced} reviews to canonical game")
                            continue
                        else:
                            print(f"Warning: canonical game OC {canonical_oc_id} not found, syncing normally")

                    print(f"Syncing game: {game_data.get('name')} (OC ID: {opencritic_game_id})")

                    # Upsert game
                    internal_game_id = await self._upsert_game(game_data)
                    if not internal_game_id:
                        continue

                    # Fetch and sync reviews (uses 1 API request)
                    reviews_synced = await self._sync_game_reviews(opencritic_game_id, internal_game_id)
                    await self._update_game_critic_aggregates(internal_game_id)

                    # Set last_review_sync_at on the game
                    game_obj = await self.db.get(Game, internal_game_id)
                    if game_obj:
                        game_obj.last_review_sync_at = datetime.now(timezone.utc)

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

            if continuous:
                reconcile_stats = await self._reconcile_recent_id_window(synced_ids)
                stats["id_reconcile_discovered"] += reconcile_stats["discovered"]
                stats["games_synced"] += reconcile_stats["games_synced"]
                stats["reviews_synced"] += reconcile_stats["reviews_synced"]

                recheck_stats = await self._refresh_recent_unreleased_games(synced_ids)
                stats["unreleased_games_rechecked"] += recheck_stats["games_checked"]
                stats["release_dates_updated"] += recheck_stats["release_dates_updated"]
                stats["reviews_synced"] += recheck_stats["reviews_synced"]

                if auto_refresh_recent_reviews:
                    recent_games = await self._get_recent_review_refresh_games(
                        days=review_refresh_days,
                        limit=review_refresh_limit,
                        all_games=False,
                        min_hours_since_last_sync=review_refresh_min_hours,
                    )
                    print(
                        "Auto-refreshing recent reviews for "
                        f"{len(recent_games)} existing games "
                        f"(days={review_refresh_days}, limit={review_refresh_limit}, "
                        f"min_hours_since_last_sync={review_refresh_min_hours})"
                    )
                    refresh_stats = await self._refresh_games_reviews(recent_games)
                    stats["recent_reviews_refreshed_games"] += refresh_stats["games_refreshed"]
                    stats["recent_reviews_refreshed_reviews"] += refresh_stats["reviews_synced"]
                    stats["recent_reviews_refresh_failed"] += refresh_stats["games_failed"]
                    stats["reviews_synced"] += refresh_stats["reviews_synced"]

            # Clear persisted queue on clean completion so next run starts fresh.
            await self._set_games_queue([])

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
            sync_log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            print(f"\nSync complete:")
            print(f"  Games synced: {stats['games_synced']}")
            print(f"  Reviews synced: {stats['reviews_synced']}")
            print(
                "  Out-of-list games discovered via ID reconciliation: "
                f"{stats['id_reconcile_discovered']}"
            )
            print(
                "  Unknown/future-date games rechecked: "
                f"{stats['unreleased_games_rechecked']}"
            )
            print(f"  Release dates updated: {stats['release_dates_updated']}")
            print(
                "  Existing games refreshed for new reviews: "
                f"{stats['recent_reviews_refreshed_games']}"
            )
            print(
                "  Reviews synced from existing-game refresh: "
                f"{stats['recent_reviews_refreshed_reviews']}"
            )
            print(
                "  Existing-game refresh failures: "
                f"{stats['recent_reviews_refresh_failed']}"
            )
            print(f"  New journalists: {stats['journalists_discovered']}")
            print(f"  New outlets: {stats['outlets_discovered']}")
            print(f"  API requests used: {stats['requests_used']}")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now(timezone.utc)
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

    def _build_recent_review_refresh_query(
        self,
        days: int,
        all_games: bool,
        min_hours_since_last_sync: Optional[int] = None,
    ):
        """Build query for selecting games whose reviews should be refreshed."""
        if all_games:
            query = select(Game).where(Game.opencritic_id.isnot(None))
        else:
            now = datetime.now(timezone.utc)
            cutoff_date = (now - timedelta(days=days)).date()
            created_window_days = max(days, self.MATCH_NEW_GAME_GRACE_DAYS)
            created_cutoff_date = (now - timedelta(days=created_window_days)).date()
            created_cutoff_dt = datetime.combine(
                created_cutoff_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            query = select(Game).where(
                Game.opencritic_id.isnot(None),
                or_(
                    and_(
                        Game.release_date.isnot(None),
                        Game.release_date >= cutoff_date,
                    ),
                    Game.created_at >= created_cutoff_dt,
                ),
            )

        if min_hours_since_last_sync is not None and min_hours_since_last_sync > 0:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(
                hours=min_hours_since_last_sync
            )
            query = query.where(
                or_(
                    Game.last_review_sync_at.is_(None),
                    Game.last_review_sync_at < stale_cutoff,
                )
            )

        return query.order_by(
            Game.last_review_sync_at.asc().nulls_first(),
            Game.release_date.desc().nulls_last(),
            Game.created_at.desc().nulls_last(),
            Game.id.desc(),
        )

    async def _get_recent_review_refresh_games(
        self,
        days: int,
        limit: Optional[int],
        all_games: bool,
        min_hours_since_last_sync: Optional[int] = None,
    ) -> List[Game]:
        """Fetch candidate games for review refresh."""
        query = self._build_recent_review_refresh_query(
            days=days,
            all_games=all_games,
            min_hours_since_last_sync=min_hours_since_last_sync,
        )
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _refresh_games_reviews(self, games: List[Game]) -> Dict[str, int]:
        """Refresh metadata + reviews for provided games."""
        stats = {
            "games_refreshed": 0,
            "reviews_synced": 0,
            "games_skipped": 0,
            "games_failed": 0,
        }

        for game in games:
            try:
                # Skip deprecated merged games
                if game.opencritic_id in self.GAME_MERGES:
                    print(f"Skipping merged game: {game.title} (OC {game.opencritic_id})")
                    stats["games_skipped"] += 1
                    continue

                print(f"Refreshing: {game.title} (OC ID: {game.opencritic_id})")

                # Check if any deprecated games merge INTO this one
                # If so, also fetch reviews from those deprecated OC IDs
                merged_from = [
                    deprecated_oc_id
                    for deprecated_oc_id, canonical_oc_id in self.GAME_MERGES.items()
                    if canonical_oc_id == game.opencritic_id
                ]

                # Re-fetch game details to update top_critic_score, etc.
                game_data = await self.service.get_game(game.opencritic_id)
                self._request_count += 1
                if game_data:
                    transformed = OpenCriticService.transform_game(game_data)
                    today = datetime.now(timezone.utc).date()
                    if transformed.get("title"):
                        game.title = transformed["title"]
                    if transformed.get("description") is not None:
                        game.description = transformed["description"]
                    if self._should_replace_release_date(
                        game.release_date,
                        transformed.get("release_date"),
                        today=today,
                    ):
                        game.release_date = transformed["release_date"]
                    game.top_critic_score = transformed.get("top_critic_score")
                    game.percent_recommended = transformed.get("percent_recommended")
                    game.tier = transformed.get("tier")
                    if transformed.get("image_url"):
                        game.image_url = transformed["image_url"]

                # Re-fetch all reviews (upsert handles deduplication)
                reviews_synced = await self._sync_game_reviews(
                    game.opencritic_id, game.id
                )

                # Also fetch reviews from any merged-in deprecated game IDs
                for deprecated_oc_id in merged_from:
                    extra_reviews = await self._sync_game_reviews(
                        deprecated_oc_id, game.id
                    )
                    reviews_synced += extra_reviews
                    if extra_reviews:
                        print(f"  + {extra_reviews} reviews from merged OC {deprecated_oc_id}")

                await self._update_game_critic_aggregates(game.id)
                game.last_review_sync_at = datetime.now(timezone.utc)
                await self.db.commit()

                stats["games_refreshed"] += 1
                stats["reviews_synced"] += reviews_synced
                print(f"  Synced {reviews_synced} reviews")

            except Exception as e:
                await self.db.rollback()
                print(f"  Error refreshing {game.title}: {e}")
                stats["games_failed"] += 1

        return stats

    async def refresh_recent_reviews(
        self,
        days: int = 90,
        limit: Optional[int] = None,
        all_games: bool = False,
        min_hours_since_last_sync: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Re-fetch reviews for recently released games to pick up new reviews.

        Args:
            days: Refresh games released within this many days (default 90).
            limit: Optional limit on number of games to process.
            all_games: If True, refresh ALL games regardless of release date.
            min_hours_since_last_sync: Optional freshness gate. If provided,
                only refresh games whose `last_review_sync_at` is older than
                this many hours (or NULL).

        Returns stats about what was refreshed.
        """
        print(
            "Starting review refresh "
            f"(days={days}, all={all_games}, "
            f"min_hours_since_last_sync={min_hours_since_last_sync})"
        )

        sync_log = SyncLog(
            source=SyncSource.OPENCRITIC,
            sync_type=SyncType.INCREMENTAL,
            status=SyncStatus.RUNNING,
        )
        self.db.add(sync_log)
        await self.db.commit()
        await self.db.refresh(sync_log)

        try:
            games = await self._get_recent_review_refresh_games(
                days=days,
                limit=limit,
                all_games=all_games,
                min_hours_since_last_sync=min_hours_since_last_sync,
            )

            print(f"Found {len(games)} games to refresh")
            stats = await self._refresh_games_reviews(games)

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.records_processed = stats["games_refreshed"]
            sync_log.records_created = stats["reviews_synced"]
            sync_log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            print(f"\nRefresh complete:")
            print(f"  Games refreshed: {stats['games_refreshed']}")
            print(f"  Reviews synced: {stats['reviews_synced']}")
            print(f"  Failed: {stats['games_failed']}")

        except Exception as e:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise

        return stats

    async def match_games_to_steam(
        self,
        limit: Optional[int] = None,
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Match games in database to Steam app IDs and Metacritic slugs.

        Args:
            limit: Optional limit on number of games to process
            days: Optional release-date filter (only games in last N days)

        Returns:
            Stats about matching results
        """
        from app.services.game_matcher import GameMatcher

        matcher = GameMatcher()

        # Match games that are missing either platform identifier.
        query = select(Game).where(
            or_(
                Game.steam_app_id.is_(None),
                Game.metacritic_slug.is_(None),
            )
        )
        mode = "missing Steam ID or Metacritic slug"
        if days is not None:
            now = datetime.now(timezone.utc)
            today = now.date()
            cutoff_date = (now - timedelta(days=days)).date()
            created_cutoff_date = (now - timedelta(days=self.MATCH_NEW_GAME_GRACE_DAYS)).date()
            created_cutoff_dt = datetime.combine(
                created_cutoff_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            max_opencritic_id_subq = select(func.max(Game.opencritic_id)).scalar_subquery()
            recent_opencritic_condition = and_(
                Game.opencritic_id.isnot(None),
                Game.opencritic_id >= (max_opencritic_id_subq - self.RECENT_ID_RECON_WINDOW),
            )
            published_review_game_ids = (
                select(Review.game_id)
                .where(
                    Review.score_normalized.isnot(None),
                    Review.published_at.isnot(None),
                    Review.published_at <= now,
                )
                .distinct()
                .scalar_subquery()
            )
            release_date_reconcile_condition = and_(
                or_(Game.release_date.is_(None), Game.release_date > today),
                Game.id.in_(published_review_game_ids),
            )
            query = query.where(
                or_(
                    and_(
                        Game.release_date.isnot(None),
                        Game.release_date >= cutoff_date,
                    ),
                    Game.created_at >= created_cutoff_dt,
                    recent_opencritic_condition,
                    release_date_reconcile_condition,
                )
            )
            mode = (
                f"released in last {days} days, or added in last "
                f"{self.MATCH_NEW_GAME_GRACE_DAYS} days, or in recent OpenCritic ID window, "
                "or release-date reconciliation needed with missing platform IDs"
            )
        if days is not None:
            query = query.order_by(
                Game.created_at.desc().nulls_last(),
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
        else:
            query = query.order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        games = result.scalars().all()

        print(f"Matching {len(games)} games {mode}...")

        stats = {
            "total": len(games),
            "steam_matched": 0,
            "metacritic_slugs_assigned": 0,
            "matched": 0,
            "failed": 0,
        }
        processed = 0

        for game in games:
            processed += 1
            try:
                match_result = await matcher.match_game(
                    title=game.title,
                    release_date=game.release_date,
                    opencritic_id=game.opencritic_id,
                )

                if match_result["steam_app_id"]:
                    if game.steam_app_id != match_result["steam_app_id"]:
                        game.steam_app_id = match_result["steam_app_id"]
                        stats["steam_matched"] += 1
                        stats["matched"] += 1
                        print(
                            f"  Matched Steam: {game.title} -> "
                            f"{match_result['steam_app_id']}"
                        )

                if match_result["metacritic_slug"] and not game.metacritic_slug:
                    game.metacritic_slug = match_result["metacritic_slug"]
                    stats["metacritic_slugs_assigned"] += 1
                    print(
                        f"  Assigned Metacritic slug: {game.title} -> "
                        f"{match_result['metacritic_slug']}"
                    )

            except Exception as e:
                print(f"  Error matching {game.title}: {e}")
                stats["failed"] += 1

            # Commit every 25 games processed
            if processed % 25 == 0:
                await self.db.commit()
                print(f"  Processed {processed}/{len(games)} games...")

        await self.db.commit()
        await matcher.steam_service.aclose()

        print(
            "\nMatching complete: "
            f"{stats['steam_matched']} Steam IDs matched, "
            f"{stats['metacritic_slugs_assigned']} Metacritic slugs assigned, "
            f"{stats['failed']} failed"
        )
        return stats


async def run_daily_sync(
    continuous: bool = True,
    full_scan: bool = False,
    stale_pages_before_stop: int = SyncOrchestrator.DEFAULT_STALE_PAGES_BEFORE_STOP,
    auto_refresh_recent_reviews: bool = True,
    review_refresh_days: int = SyncOrchestrator.AUTO_REVIEW_REFRESH_DAYS,
    review_refresh_limit: Optional[int] = SyncOrchestrator.AUTO_REVIEW_REFRESH_LIMIT,
    review_refresh_min_hours: int = SyncOrchestrator.AUTO_REVIEW_REFRESH_MIN_HOURS,
):
    """Convenience function to run the sync.
    
    Args:
        continuous: If True, keep fetching until all games are synced.
        full_scan: If True, scan the entire OpenCritic catalog.
        stale_pages_before_stop: Incremental mode stop threshold.
        auto_refresh_recent_reviews: Whether to refresh existing recent games
            for new critic reviews after ingesting new games.
        review_refresh_days: Auto-review-refresh recency window (days).
        review_refresh_limit: Max games to refresh in the auto pass.
        review_refresh_min_hours: Skip games refreshed within this many hours.
    """
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)
        return await orchestrator.run_daily_sync(
            continuous=continuous,
            full_scan=full_scan,
            stale_pages_before_stop=stale_pages_before_stop,
            auto_refresh_recent_reviews=auto_refresh_recent_reviews,
            review_refresh_days=review_refresh_days,
            review_refresh_limit=review_refresh_limit,
            review_refresh_min_hours=review_refresh_min_hours,
        )


async def get_sync_status():
    """Convenience function to get sync status."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)
        return await orchestrator.get_sync_status()


async def refresh_recent_reviews(
    days: int = 90,
    limit: Optional[int] = None,
    all_games: bool = False,
    min_hours_since_last_sync: Optional[int] = None,
):
    """Convenience function to refresh recent reviews."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)
        return await orchestrator.refresh_recent_reviews(
            days=days,
            limit=limit,
            all_games=all_games,
            min_hours_since_last_sync=min_hours_since_last_sync,
        )

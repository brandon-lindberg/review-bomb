"""
Disparity calculation service.

Calculates the disparity between critic scores and user scores,
and generates aggregated statistics for journalists, outlets, and games.

Optimized to use bulk-loading: all user scores and reviews are loaded
upfront in a few queries, then all calculations happen in-memory.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple

from statistics import mean, stdev

from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Review, Game, UserScore, Journalist, Outlet, DisparitySnapshot,
    JournalistOutletDisparitySnapshot,
    UserScoreSource,
)

# Anti-gaming: minimum user reviews required for a game to count in disparity
# Steam typically has more reviews, Metacritic has fewer
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20


class DisparityCalculator:
    """
    Calculates disparity between critic and user scores.

    Disparity Formula:
        disparity = critic_normalized_score - user_normalized_score

        - Positive disparity: Critic scored higher than users
        - Negative disparity: Critic scored lower than users
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Caches populated by bulk loading
        self._user_scores_cache: Optional[Dict[int, Dict[str, Optional[Decimal]]]] = None
        self._reviews_cache: Optional[List[Tuple]] = None
        # Pre-built indexes for O(1) lookups by entity
        self._reviews_by_journalist: Optional[Dict[int, List[Tuple]]] = None
        self._reviews_by_outlet: Optional[Dict[int, List[Tuple]]] = None
        self._reviews_by_game: Optional[Dict[int, List[Tuple]]] = None
        self._detail_disparity_cache_snapshot_date: Optional[date] = None

    # =========================================================================
    # Bulk Loading
    # =========================================================================

    async def _load_all_user_scores(self) -> Dict[int, Dict[str, Optional[Decimal]]]:
        """
        Load the latest user scores for ALL games in 2 queries (Steam + Metacritic).
        Returns dict keyed by game_id with steam_score and metacritic_score.
        Only includes scores meeting minimum sample size thresholds.
        """
        if self._user_scores_cache is not None:
            return self._user_scores_cache

        scores: Dict[int, Dict[str, Optional[Decimal]]] = {}

        # Get latest Steam scores using DISTINCT ON (PostgreSQL)
        steam_query = (
            select(UserScore.game_id, UserScore.score, UserScore.sample_size)
            .where(UserScore.source == UserScoreSource.STEAM)
            .distinct(UserScore.game_id)
            .order_by(UserScore.game_id, UserScore.scraped_at.desc())
        )
        steam_result = await self.db.execute(steam_query)
        for row in steam_result:
            game_id, score, sample_size = row
            if game_id not in scores:
                scores[game_id] = {"steam_score": None, "metacritic_score": None}
            if (sample_size or 0) >= MIN_STEAM_USER_REVIEWS:
                scores[game_id]["steam_score"] = score

        # Get latest Metacritic scores using DISTINCT ON (PostgreSQL)
        metacritic_query = (
            select(UserScore.game_id, UserScore.score, UserScore.sample_size)
            .where(UserScore.source == UserScoreSource.METACRITIC)
            .distinct(UserScore.game_id)
            .order_by(UserScore.game_id, UserScore.scraped_at.desc())
        )
        metacritic_result = await self.db.execute(metacritic_query)
        for row in metacritic_result:
            game_id, score, sample_size = row
            if game_id not in scores:
                scores[game_id] = {"steam_score": None, "metacritic_score": None}
            if sample_size is None or sample_size >= MIN_METACRITIC_USER_REVIEWS:
                scores[game_id]["metacritic_score"] = score

        self._user_scores_cache = scores
        return scores

    async def _load_all_reviews(self) -> List[Tuple]:
        """
        Load all reviews with normalized scores in one query.
        Returns list of (review_id, game_id, journalist_id, outlet_id, score_normalized).
        Also builds per-entity indexes for O(1) lookups.
        """
        if self._reviews_cache is not None:
            return self._reviews_cache

        query = select(
            Review.id,
            Review.game_id,
            Review.journalist_id,
            Review.outlet_id,
            Review.score_normalized,
        ).where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
        )

        result = await self.db.execute(query)
        self._reviews_cache = result.all()

        # Build per-entity indexes
        self._reviews_by_journalist = defaultdict(list)
        self._reviews_by_outlet = defaultdict(list)
        self._reviews_by_game = defaultdict(list)
        for row in self._reviews_cache:
            _review_id, game_id, journalist_id, outlet_id, _score = row
            self._reviews_by_journalist[journalist_id].append(row)
            if outlet_id is not None:
                self._reviews_by_outlet[outlet_id].append(row)
            self._reviews_by_game[game_id].append(row)

        return self._reviews_cache

    # =========================================================================
    # Per-Review Disparity
    # =========================================================================

    @staticmethod
    def calculate_review_disparity(
        critic_score: Optional[Decimal],
        steam_score: Optional[Decimal] = None,
        metacritic_score: Optional[Decimal] = None,
    ) -> Dict[str, Optional[Decimal]]:
        """
        Calculate disparity for a single review.
        """
        result = {
            "disparity_steam": None,
            "disparity_metacritic": None,
            "disparity_combined": None,
        }

        if critic_score is None:
            return result

        if steam_score is not None:
            result["disparity_steam"] = critic_score - steam_score

        if metacritic_score is not None:
            result["disparity_metacritic"] = critic_score - metacritic_score

        # Combined is average of available disparities
        disparities = [
            d for d in [result["disparity_steam"], result["disparity_metacritic"]]
            if d is not None
        ]
        if disparities:
            result["disparity_combined"] = Decimal(str(round(
                sum(float(d) for d in disparities) / len(disparities), 2
            )))

        return result

    async def get_game_user_scores(
        self,
        game_id: int,
    ) -> Dict[str, Optional[Decimal]]:
        """
        Get the latest user scores for a game (only if they meet minimum sample size).
        Uses bulk-loaded cache if available, otherwise falls back to individual queries.
        """
        if self._user_scores_cache is not None:
            return self._user_scores_cache.get(
                game_id, {"steam_score": None, "metacritic_score": None}
            )

        # Fallback for individual calls (e.g. from API endpoints)
        result = {"steam_score": None, "metacritic_score": None}

        steam_query = (
            select(UserScore.score, UserScore.sample_size)
            .where(
                UserScore.game_id == game_id,
                UserScore.source == UserScoreSource.STEAM,
            )
            .order_by(UserScore.scraped_at.desc())
            .limit(1)
        )
        steam_result = await self.db.execute(steam_query)
        steam_row = steam_result.first()
        if steam_row and (steam_row[1] or 0) >= MIN_STEAM_USER_REVIEWS:
            result["steam_score"] = steam_row[0]

        metacritic_query = (
            select(UserScore.score, UserScore.sample_size)
            .where(
                UserScore.game_id == game_id,
                UserScore.source == UserScoreSource.METACRITIC,
            )
            .order_by(UserScore.scraped_at.desc())
            .limit(1)
        )
        metacritic_result = await self.db.execute(metacritic_query)
        metacritic_row = metacritic_result.first()
        if metacritic_row and (metacritic_row[1] is None or metacritic_row[1] >= MIN_METACRITIC_USER_REVIEWS):
            result["metacritic_score"] = metacritic_row[0]

        return result

    async def ensure_detail_disparity_caches(
        self,
        snapshot_date: Optional[date] = None,
    ) -> None:
        """
        Ensure pipeline-backed detail caches are refreshed for this run.

        Populates:
        - per-review cached disparities/user scores (for review list endpoints)
        - journalist+outlet disparity snapshots (for journalist outlet breakdown)
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        if self._detail_disparity_cache_snapshot_date == snapshot_date:
            return

        await self._load_all_user_scores()
        await self._load_all_reviews()

        review_count = await self._refresh_review_disparity_cache()
        pair_count = await self._generate_journalist_outlet_snapshots(snapshot_date)
        # Release review-table writes before continuing with the heavier snapshot loops.
        await self.db.commit()

        print(
            f"Refreshed detail disparity caches: {review_count} review cache rows updated, "
            f"{pair_count} journalist-outlet snapshots"
        )
        self._detail_disparity_cache_snapshot_date = snapshot_date

    async def _refresh_review_disparity_cache(
        self,
        batch_size: int = 5000,
    ) -> int:
        """
        Cache per-review disparities and the user scores used to calculate them.
        """
        await self._load_all_user_scores()
        await self._load_all_reviews()

        # Avoid rewriting every review on every disparity run; only update rows whose
        # cached values actually changed (new reviews or changed user scores).
        existing_cache_result = await self.db.execute(
            select(
                Review.id,
                Review.cached_steam_user_score,
                Review.cached_metacritic_user_score,
                Review.cached_disparity_steam,
                Review.cached_disparity_metacritic,
                Review.cached_disparity_combined,
            ).where(
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
        )
        existing_cache: Dict[
            int,
            Tuple[
                Optional[Decimal],
                Optional[Decimal],
                Optional[Decimal],
                Optional[Decimal],
                Optional[Decimal],
            ],
        ] = {
            review_id: (
                cached_steam_user_score,
                cached_metacritic_user_score,
                cached_disparity_steam,
                cached_disparity_metacritic,
                cached_disparity_combined,
            )
            for (
                review_id,
                cached_steam_user_score,
                cached_metacritic_user_score,
                cached_disparity_steam,
                cached_disparity_metacritic,
                cached_disparity_combined,
            ) in existing_cache_result
        }

        updates: List[Dict[str, Any]] = []
        updated_count = 0

        for review_id, game_id, _journalist_id, _outlet_id, score_normalized in self._reviews_cache:
            user_scores = self._user_scores_cache.get(
                game_id,
                {"steam_score": None, "metacritic_score": None},
            )
            disparity = self.calculate_review_disparity(
                score_normalized,
                user_scores.get("steam_score"),
                user_scores.get("metacritic_score"),
            )
            new_values = (
                user_scores.get("steam_score"),
                user_scores.get("metacritic_score"),
                disparity["disparity_steam"],
                disparity["disparity_metacritic"],
                disparity["disparity_combined"],
            )
            if existing_cache.get(review_id) == new_values:
                continue

            updates.append(
                {
                    "id": review_id,
                    "cached_steam_user_score": new_values[0],
                    "cached_metacritic_user_score": new_values[1],
                    "cached_disparity_steam": new_values[2],
                    "cached_disparity_metacritic": new_values[3],
                    "cached_disparity_combined": new_values[4],
                }
            )
            updated_count += 1

            if len(updates) >= batch_size:
                await self.db.execute(update(Review), updates)
                # Commit in chunks so the site is not impacted by one long-running
                # write transaction touching the entire reviews table.
                await self.db.commit()
                updates = []

        if updates:
            await self.db.execute(update(Review), updates)
            await self.db.commit()

        return updated_count

    async def _generate_journalist_outlet_snapshots(
        self,
        snapshot_date: date,
    ) -> int:
        """
        Generate per-(journalist, outlet) disparity snapshots from pipeline inputs.
        """
        await self._load_all_user_scores()
        await self._load_all_reviews()

        # If the job is re-run the same day, replace today's pair snapshots so API reads
        # a single canonical row per pair for that date.
        await self.db.execute(
            delete(JournalistOutletDisparitySnapshot).where(
                JournalistOutletDisparitySnapshot.snapshot_date == snapshot_date
            )
        )

        pair_steam: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        pair_metacritic: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        pair_combined: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        pair_review_counts: Dict[Tuple[int, int], int] = defaultdict(int)

        for _review_id, game_id, journalist_id, outlet_id, score_normalized in self._reviews_cache:
            if outlet_id is None:
                continue

            pair_key = (journalist_id, outlet_id)
            pair_review_counts[pair_key] += 1

            user_scores = self._user_scores_cache.get(
                game_id,
                {"steam_score": None, "metacritic_score": None},
            )
            disparity = self.calculate_review_disparity(
                score_normalized,
                user_scores.get("steam_score"),
                user_scores.get("metacritic_score"),
            )
            if disparity["disparity_steam"] is not None:
                pair_steam[pair_key].append(float(disparity["disparity_steam"]))
            if disparity["disparity_metacritic"] is not None:
                pair_metacritic[pair_key].append(float(disparity["disparity_metacritic"]))
            if disparity["disparity_combined"] is not None:
                pair_combined[pair_key].append(float(disparity["disparity_combined"]))

        count = 0
        for (journalist_id, outlet_id), review_count in pair_review_counts.items():
            stats = self._compute_stats(
                pair_steam.get((journalist_id, outlet_id), []),
                pair_metacritic.get((journalist_id, outlet_id), []),
                pair_combined.get((journalist_id, outlet_id), []),
                review_count,
            )
            self.db.add(
                JournalistOutletDisparitySnapshot(
                    journalist_id=journalist_id,
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
            )
            count += 1

        await self.db.flush()
        return count

    # =========================================================================
    # Journalist Aggregations
    # =========================================================================

    async def calculate_journalist_disparity(
        self,
        journalist_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate aggregate disparity statistics for a journalist.
        Uses bulk-loaded cache if available.
        """
        if self._user_scores_cache is not None and self._reviews_cache is not None:
            return self._calculate_entity_disparity_from_cache(
                "journalist", journalist_id
            )

        # Fallback for individual calls
        query = (
            select(Review, Game)
            .join(Game, Review.game_id == Game.id)
            .where(
                Review.journalist_id == journalist_id,
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
        )
        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            return None

        steam_disparities: List[float] = []
        metacritic_disparities: List[float] = []
        combined_disparities: List[float] = []

        for review, game in rows:
            user_scores = await self.get_game_user_scores(game.id)
            disparity = self.calculate_review_disparity(
                review.score_normalized,
                user_scores["steam_score"],
                user_scores["metacritic_score"],
            )

            if disparity["disparity_steam"] is not None:
                steam_disparities.append(float(disparity["disparity_steam"]))
            if disparity["disparity_metacritic"] is not None:
                metacritic_disparities.append(float(disparity["disparity_metacritic"]))
            if disparity["disparity_combined"] is not None:
                combined_disparities.append(float(disparity["disparity_combined"]))

        return self._compute_stats(
            steam_disparities, metacritic_disparities, combined_disparities, len(rows),
        )

    # =========================================================================
    # Outlet Aggregations
    # =========================================================================

    async def calculate_outlet_disparity(
        self,
        outlet_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate aggregate disparity statistics for an outlet.
        Uses bulk-loaded cache if available.
        """
        if self._user_scores_cache is not None and self._reviews_cache is not None:
            return self._calculate_entity_disparity_from_cache(
                "outlet", outlet_id
            )

        # Fallback for individual calls
        query = (
            select(Review, Game)
            .join(Game, Review.game_id == Game.id)
            .where(
                Review.outlet_id == outlet_id,
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
        )
        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            return None

        steam_disparities: List[float] = []
        metacritic_disparities: List[float] = []
        combined_disparities: List[float] = []

        for review, game in rows:
            user_scores = await self.get_game_user_scores(game.id)
            disparity = self.calculate_review_disparity(
                review.score_normalized,
                user_scores["steam_score"],
                user_scores["metacritic_score"],
            )

            if disparity["disparity_steam"] is not None:
                steam_disparities.append(float(disparity["disparity_steam"]))
            if disparity["disparity_metacritic"] is not None:
                metacritic_disparities.append(float(disparity["disparity_metacritic"]))
            if disparity["disparity_combined"] is not None:
                combined_disparities.append(float(disparity["disparity_combined"]))

        return self._compute_stats(
            steam_disparities, metacritic_disparities, combined_disparities, len(rows),
        )

    # =========================================================================
    # Game Aggregations
    # =========================================================================

    async def calculate_game_disparity(
        self,
        game_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate aggregate disparity statistics for a game.
        Uses bulk-loaded cache if available.
        """
        if self._user_scores_cache is not None and self._reviews_cache is not None:
            return self._calculate_entity_disparity_from_cache(
                "game", game_id
            )

        # Fallback for individual calls
        query = select(Review).where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
        )
        result = await self.db.execute(query)
        reviews = result.scalars().all()

        if not reviews:
            return None

        user_scores = await self.get_game_user_scores(game_id)

        steam_disparities: List[float] = []
        metacritic_disparities: List[float] = []
        combined_disparities: List[float] = []

        for review in reviews:
            disparity = self.calculate_review_disparity(
                review.score_normalized,
                user_scores["steam_score"],
                user_scores["metacritic_score"],
            )

            if disparity["disparity_steam"] is not None:
                steam_disparities.append(float(disparity["disparity_steam"]))
            if disparity["disparity_metacritic"] is not None:
                metacritic_disparities.append(float(disparity["disparity_metacritic"]))
            if disparity["disparity_combined"] is not None:
                combined_disparities.append(float(disparity["disparity_combined"]))

        return self._compute_stats(
            steam_disparities, metacritic_disparities, combined_disparities, len(reviews),
        )

    # =========================================================================
    # In-Memory Disparity from Cache
    # =========================================================================

    def _calculate_entity_disparity_from_cache(
        self,
        entity_type: str,
        entity_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate disparity for an entity using pre-loaded caches.
        No DB queries needed.
        """
        # Look up reviews for this entity using pre-built indexes (O(1) lookup)
        if entity_type == "journalist":
            entity_reviews = self._reviews_by_journalist.get(entity_id, [])
        elif entity_type == "outlet":
            entity_reviews = self._reviews_by_outlet.get(entity_id, [])
        elif entity_type == "game":
            entity_reviews = self._reviews_by_game.get(entity_id, [])
        else:
            return None

        if not entity_reviews:
            return None

        steam_disparities: List[float] = []
        metacritic_disparities: List[float] = []
        combined_disparities: List[float] = []

        for _review_id, game_id, _journalist_id, _outlet_id, score_normalized in entity_reviews:
            user_scores = self._user_scores_cache.get(
                game_id, {"steam_score": None, "metacritic_score": None}
            )
            disparity = self.calculate_review_disparity(
                score_normalized,
                user_scores["steam_score"],
                user_scores["metacritic_score"],
            )

            if disparity["disparity_steam"] is not None:
                steam_disparities.append(float(disparity["disparity_steam"]))
            if disparity["disparity_metacritic"] is not None:
                metacritic_disparities.append(float(disparity["disparity_metacritic"]))
            if disparity["disparity_combined"] is not None:
                combined_disparities.append(float(disparity["disparity_combined"]))

        return self._compute_stats(
            steam_disparities,
            metacritic_disparities,
            combined_disparities,
            len(entity_reviews),
        )

    # =========================================================================
    # Snapshot Generation (Optimized with Bulk Loading)
    # =========================================================================

    async def generate_all_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> Dict[str, int]:
        """
        Generate all disparity snapshots for journalists, outlets, and games.
        Also updates denormalized columns on each entity for fast UI queries.
        Uses bulk-loaded data for all calculations (3 DB queries total for data loading).
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Bulk load all data upfront (2 queries for user scores + 1 for reviews)
        print("Loading user scores...")
        user_scores = await self._load_all_user_scores()
        print(f"  Loaded scores for {len(user_scores)} games")

        print("Loading reviews...")
        reviews = await self._load_all_reviews()
        print(f"  Loaded {len(reviews)} scored reviews")

        # Refresh pipeline-backed detail caches used by review rows and journalist
        # outlet breakdowns before generating entity snapshots.
        await self.ensure_detail_disparity_caches(snapshot_date)

        # Entity IDs extracted from pre-built indexes
        journalist_ids = set(self._reviews_by_journalist.keys())
        outlet_ids = set(self._reviews_by_outlet.keys())
        game_ids = set(self._reviews_by_game.keys())

        print(f"  {len(journalist_ids)} journalists, {len(outlet_ids)} outlets, {len(game_ids)} games with reviews")

        # Pre-build last_review_at lookup from reviews cache
        # Reviews cache: (review_id, game_id, journalist_id, outlet_id, score_normalized)
        # We need published_at for last_review_at, load it separately
        print("Loading review dates for last_review_at...")
        last_review_query = (
            select(
                Review.journalist_id,
                Review.outlet_id,
                func.max(Review.published_at).label("last_review_at"),
            )
            .where(
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
            .group_by(Review.journalist_id, Review.outlet_id)
        )
        last_review_result = await self.db.execute(last_review_query)
        journalist_last_review: Dict[int, datetime] = {}
        outlet_last_review: Dict[int, datetime] = {}
        max_reasonable_date = datetime.now(timezone.utc) + timedelta(days=30)
        for row in last_review_result:
            j_id, o_id, last_at = row
            if last_at is not None and last_at <= max_reasonable_date:
                if j_id not in journalist_last_review or last_at > journalist_last_review[j_id]:
                    journalist_last_review[j_id] = last_at
                if o_id is not None:
                    if o_id not in outlet_last_review or last_at > outlet_last_review[o_id]:
                        outlet_last_review[o_id] = last_at

        # Load journalist_count per outlet
        journalist_count_query = (
            select(
                Review.outlet_id,
                func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
            )
            .where(
                Review.outlet_id.isnot(None),
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
            .group_by(Review.outlet_id)
        )
        jc_result = await self.db.execute(journalist_count_query)
        outlet_journalist_counts: Dict[int, int] = {
            row[0]: row[1] for row in jc_result
        }

        # ---- Journalists ----
        print(f"\nProcessing {len(journalist_ids)} journalists...")
        journalist_count = 0
        for i, journalist_id in enumerate(journalist_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("journalist", journalist_id)
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
                self.db.add(snapshot)
                journalist_count += 1

                # Update denormalized columns on Journalist
                journalist_obj = await self.db.get(Journalist, journalist_id)
                if journalist_obj:
                    journalist_obj.avg_disparity = stats["avg_disparity_combined"]
                    journalist_obj.review_count_scored = stats["review_count"]
                    journalist_obj.score_std_dev = stats["std_deviation"]
                    journalist_obj.last_review_at = journalist_last_review.get(journalist_id)

            if i % 1000 == 0:
                await self.db.commit()
                print(f"  {i}/{len(journalist_ids)} journalists processed...")

        await self.db.commit()
        print(f"  Done: {journalist_count} journalist snapshots")

        # ---- Outlets ----
        print(f"\nProcessing {len(outlet_ids)} outlets...")
        outlet_count = 0
        for i, outlet_id in enumerate(outlet_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("outlet", outlet_id)
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
                self.db.add(snapshot)
                outlet_count += 1

                # Update denormalized columns on Outlet
                outlet_obj = await self.db.get(Outlet, outlet_id)
                if outlet_obj:
                    outlet_obj.avg_disparity = stats["avg_disparity_combined"]
                    outlet_obj.review_count_scored = stats["review_count"]
                    outlet_obj.score_std_dev = stats["std_deviation"]
                    outlet_obj.last_review_at = outlet_last_review.get(outlet_id)
                    outlet_obj.journalist_count = outlet_journalist_counts.get(outlet_id, 0)

            if i % 100 == 0:
                await self.db.commit()
                print(f"  {i}/{len(outlet_ids)} outlets processed...")

        await self.db.commit()
        print(f"  Done: {outlet_count} outlet snapshots")

        # ---- Games ----
        print(f"\nProcessing {len(game_ids)} games...")
        game_count = 0
        for i, game_id in enumerate(game_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("game", game_id)
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
                self.db.add(snapshot)
                game_count += 1

                # Update denormalized columns on Game
                game_obj = await self.db.get(Game, game_id)
                if game_obj:
                    game_obj.disparity_steam = stats["avg_disparity_steam"]
                    game_obj.disparity_metacritic = stats["avg_disparity_metacritic"]

            if i % 2000 == 0:
                await self.db.commit()
                print(f"  {i}/{len(game_ids)} games processed...")

        await self.db.commit()
        print(f"  Done: {game_count} game snapshots")

        # Clear caches
        self._user_scores_cache = None
        self._reviews_cache = None
        self._reviews_by_journalist = None
        self._reviews_by_outlet = None
        self._reviews_by_game = None
        self._detail_disparity_cache_snapshot_date = None

        return {
            "journalists": journalist_count,
            "outlets": outlet_count,
            "games": game_count,
        }

    async def generate_journalist_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """Generate disparity snapshots for all journalists."""
        if snapshot_date is None:
            snapshot_date = date.today()

        await self.ensure_detail_disparity_caches(snapshot_date)

        # Build last_review_at lookup (guard against bad future dates).
        last_review_query = (
            select(
                Review.journalist_id,
                func.max(Review.published_at).label("last_review_at"),
            )
            .where(
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
            .group_by(Review.journalist_id)
        )
        last_review_result = await self.db.execute(last_review_query)
        journalist_last_review: Dict[int, datetime] = {}
        max_reasonable_date = datetime.now(timezone.utc) + timedelta(days=30)
        for journalist_id, last_at in last_review_result:
            if journalist_id is not None and last_at is not None and last_at <= max_reasonable_date:
                journalist_last_review[journalist_id] = last_at

        journalist_ids = set(r[2] for r in self._reviews_cache)
        print(f"Processing {len(journalist_ids)} journalists...")

        count = 0
        journalist_updates: List[Dict[str, Any]] = []
        for i, journalist_id in enumerate(journalist_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("journalist", journalist_id)
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
                self.db.add(snapshot)
                count += 1
                journalist_updates.append({
                    "id": journalist_id,
                    "avg_disparity": stats["avg_disparity_combined"],
                    "review_count_scored": stats["review_count"],
                    "score_std_dev": stats["std_deviation"],
                    "last_review_at": journalist_last_review.get(journalist_id),
                })

            if i % 1000 == 0:
                if journalist_updates:
                    await self.db.execute(update(Journalist), journalist_updates)
                    journalist_updates = []
                await self.db.flush()
                print(f"  {i}/{len(journalist_ids)} processed...")

        if journalist_updates:
            await self.db.execute(update(Journalist), journalist_updates)

        await self.db.commit()
        return count

    async def generate_outlet_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """Generate disparity snapshots for all outlets."""
        if snapshot_date is None:
            snapshot_date = date.today()

        await self.ensure_detail_disparity_caches(snapshot_date)

        # Build last_review_at lookup (guard against bad future dates).
        outlet_last_review_query = (
            select(
                Review.outlet_id,
                func.max(Review.published_at).label("last_review_at"),
            )
            .where(
                Review.outlet_id.isnot(None),
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
            .group_by(Review.outlet_id)
        )
        outlet_last_review_result = await self.db.execute(outlet_last_review_query)
        outlet_last_review: Dict[int, datetime] = {}
        max_reasonable_date = datetime.now(timezone.utc) + timedelta(days=30)
        for outlet_id, last_at in outlet_last_review_result:
            if outlet_id is not None and last_at is not None and last_at <= max_reasonable_date:
                outlet_last_review[outlet_id] = last_at

        # Build journalist_count per outlet.
        journalist_count_query = (
            select(
                Review.outlet_id,
                func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
            )
            .where(
                Review.outlet_id.isnot(None),
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
            )
            .group_by(Review.outlet_id)
        )
        journalist_count_result = await self.db.execute(journalist_count_query)
        outlet_journalist_counts: Dict[int, int] = {
            outlet_id: journalist_count
            for outlet_id, journalist_count in journalist_count_result
            if outlet_id is not None
        }

        outlet_ids = set(r[3] for r in self._reviews_cache if r[3] is not None)
        print(f"Processing {len(outlet_ids)} outlets...")

        count = 0
        outlet_updates: List[Dict[str, Any]] = []
        for i, outlet_id in enumerate(outlet_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("outlet", outlet_id)
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
                self.db.add(snapshot)
                count += 1
                outlet_updates.append({
                    "id": outlet_id,
                    "avg_disparity": stats["avg_disparity_combined"],
                    "review_count_scored": stats["review_count"],
                    "score_std_dev": stats["std_deviation"],
                    "last_review_at": outlet_last_review.get(outlet_id),
                    "journalist_count": outlet_journalist_counts.get(outlet_id, 0),
                })

            if i % 100 == 0:
                if outlet_updates:
                    await self.db.execute(update(Outlet), outlet_updates)
                    outlet_updates = []
                await self.db.flush()
                print(f"  {i}/{len(outlet_ids)} processed...")

        if outlet_updates:
            await self.db.execute(update(Outlet), outlet_updates)

        await self.db.commit()
        return count

    async def generate_game_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """Generate disparity snapshots for all games."""
        if snapshot_date is None:
            snapshot_date = date.today()

        await self.ensure_detail_disparity_caches(snapshot_date)

        game_ids = set(r[1] for r in self._reviews_cache)
        print(f"Processing {len(game_ids)} games...")

        count = 0
        game_updates: List[Dict[str, Any]] = []
        for i, game_id in enumerate(game_ids, 1):
            stats = self._calculate_entity_disparity_from_cache("game", game_id)
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
                self.db.add(snapshot)
                count += 1
                game_updates.append({
                    "id": game_id,
                    "disparity_steam": stats["avg_disparity_steam"],
                    "disparity_metacritic": stats["avg_disparity_metacritic"],
                })

            if i % 2000 == 0:
                if game_updates:
                    await self.db.execute(update(Game), game_updates)
                    game_updates = []
                await self.db.flush()
                print(f"  {i}/{len(game_ids)} processed...")

        if game_updates:
            await self.db.execute(update(Game), game_updates)

        await self.db.commit()
        return count

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _compute_stats(
        steam_disparities: List[float],
        metacritic_disparities: List[float],
        combined_disparities: List[float],
        review_count: int,
    ) -> Dict[str, Any]:
        """Compute aggregate statistics from disparity lists."""
        result = {
            "avg_disparity_steam": None,
            "avg_disparity_metacritic": None,
            "avg_disparity_combined": None,
            "review_count": review_count,
            "std_deviation": None,
            "min_disparity": None,
            "max_disparity": None,
        }

        if steam_disparities:
            result["avg_disparity_steam"] = Decimal(str(round(mean(steam_disparities), 2)))

        if metacritic_disparities:
            result["avg_disparity_metacritic"] = Decimal(str(round(mean(metacritic_disparities), 2)))

        if combined_disparities:
            result["avg_disparity_combined"] = Decimal(str(round(mean(combined_disparities), 2)))
            result["min_disparity"] = Decimal(str(round(min(combined_disparities), 2)))
            result["max_disparity"] = Decimal(str(round(max(combined_disparities), 2)))

            if len(combined_disparities) > 1:
                result["std_deviation"] = Decimal(str(round(stdev(combined_disparities), 2)))

        return result

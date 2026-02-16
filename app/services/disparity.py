"""
Disparity calculation service.

Calculates the disparity between critic scores and user scores,
and generates aggregated statistics for journalists, outlets, and games.

Optimized to use bulk-loading: all user scores and reviews are loaded
upfront in a few queries, then all calculations happen in-memory.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple

from statistics import mean, stdev

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Review, Game, UserScore, Journalist, Outlet, DisparitySnapshot,
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
        ).where(Review.score_normalized.isnot(None))

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
            .where(Review.journalist_id == journalist_id)
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
            .where(Review.outlet_id == outlet_id)
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
        query = select(Review).where(Review.game_id == game_id)
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
            .where(Review.score_normalized.isnot(None))
            .group_by(Review.journalist_id, Review.outlet_id)
        )
        last_review_result = await self.db.execute(last_review_query)
        journalist_last_review: Dict[int, datetime] = {}
        outlet_last_review: Dict[int, datetime] = {}
        max_reasonable_date = datetime.utcnow() + timedelta(days=30)
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
            .where(Review.outlet_id.isnot(None), Review.score_normalized.isnot(None))
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

        # Bulk load data
        await self._load_all_user_scores()
        await self._load_all_reviews()

        journalist_ids = set(r[2] for r in self._reviews_cache)
        print(f"Processing {len(journalist_ids)} journalists...")

        count = 0
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

            if i % 1000 == 0:
                await self.db.flush()
                print(f"  {i}/{len(journalist_ids)} processed...")

        await self.db.commit()
        return count

    async def generate_outlet_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """Generate disparity snapshots for all outlets."""
        if snapshot_date is None:
            snapshot_date = date.today()

        await self._load_all_user_scores()
        await self._load_all_reviews()

        outlet_ids = set(r[3] for r in self._reviews_cache if r[3] is not None)
        print(f"Processing {len(outlet_ids)} outlets...")

        count = 0
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

            if i % 100 == 0:
                await self.db.flush()
                print(f"  {i}/{len(outlet_ids)} processed...")

        await self.db.commit()
        return count

    async def generate_game_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """Generate disparity snapshots for all games."""
        if snapshot_date is None:
            snapshot_date = date.today()

        await self._load_all_user_scores()
        await self._load_all_reviews()

        game_ids = set(r[1] for r in self._reviews_cache)
        print(f"Processing {len(game_ids)} games...")

        count = 0
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

            if i % 2000 == 0:
                await self.db.flush()
                print(f"  {i}/{len(game_ids)} processed...")

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

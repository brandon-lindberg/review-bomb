"""
Disparity calculation service.

Calculates the disparity between critic scores and user scores,
and generates aggregated statistics for journalists, outlets, and games.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from statistics import mean, stdev

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Review, Game, UserScore, Journalist, Outlet, DisparitySnapshot,
    UserScoreSource,
)


class DisparityCalculator:
    """
    Calculates disparity between critic and user scores.

    Disparity Formula:
        disparity = critic_normalized_score - user_normalized_score

        - Positive disparity: Critic scored higher than users
        - Negative disparity: Critic scored lower than users
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize calculator with database session.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    # =========================================================================
    # Per-Review Disparity
    # =========================================================================

    async def calculate_review_disparity(
        self,
        review: Review,
        steam_score: Optional[Decimal] = None,
        metacritic_score: Optional[Decimal] = None,
    ) -> Dict[str, Optional[Decimal]]:
        """
        Calculate disparity for a single review.

        Args:
            review: Review object with normalized score
            steam_score: Optional Steam user score (0-100)
            metacritic_score: Optional Metacritic user score (0-100)

        Returns:
            Dictionary with disparity values
        """
        result = {
            "disparity_steam": None,
            "disparity_metacritic": None,
            "disparity_combined": None,
        }

        critic_score = review.score_normalized

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
        Get the latest user scores for a game.

        Args:
            game_id: Game ID

        Returns:
            Dictionary with steam_score and metacritic_score
        """
        result = {"steam_score": None, "metacritic_score": None}

        # Get latest Steam score
        steam_query = (
            select(UserScore.score)
            .where(
                UserScore.game_id == game_id,
                UserScore.source == UserScoreSource.STEAM,
            )
            .order_by(UserScore.scraped_at.desc())
            .limit(1)
        )
        steam_result = await self.db.execute(steam_query)
        steam_score = steam_result.scalar_one_or_none()
        if steam_score:
            result["steam_score"] = steam_score

        # Get latest Metacritic score
        metacritic_query = (
            select(UserScore.score)
            .where(
                UserScore.game_id == game_id,
                UserScore.source == UserScoreSource.METACRITIC,
            )
            .order_by(UserScore.scraped_at.desc())
            .limit(1)
        )
        metacritic_result = await self.db.execute(metacritic_query)
        metacritic_score = metacritic_result.scalar_one_or_none()
        if metacritic_score:
            result["metacritic_score"] = metacritic_score

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

        Args:
            journalist_id: Journalist ID

        Returns:
            Dictionary with aggregated disparity stats, or None if no data
        """
        # Get all reviews by this journalist with their game's user scores
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
            disparity = await self.calculate_review_disparity(
                review,
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
            len(rows),
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

        Args:
            outlet_id: Outlet ID

        Returns:
            Dictionary with aggregated disparity stats, or None if no data
        """
        # Get all reviews from this outlet
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
            disparity = await self.calculate_review_disparity(
                review,
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
            len(rows),
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

        This shows how critics as a whole rated a game vs users.

        Args:
            game_id: Game ID

        Returns:
            Dictionary with aggregated disparity stats, or None if no data
        """
        # Get all reviews for this game
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
            disparity = await self.calculate_review_disparity(
                review,
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
            len(reviews),
        )

    # =========================================================================
    # Snapshot Generation
    # =========================================================================

    async def generate_journalist_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """
        Generate disparity snapshots for all journalists.

        Args:
            snapshot_date: Date for the snapshot (defaults to today)

        Returns:
            Number of snapshots created
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Get all journalist IDs
        query = select(Journalist.id)
        result = await self.db.execute(query)
        journalist_ids = [row[0] for row in result.all()]

        count = 0
        for journalist_id in journalist_ids:
            stats = await self.calculate_journalist_disparity(journalist_id)
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

        await self.db.commit()
        return count

    async def generate_outlet_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """
        Generate disparity snapshots for all outlets.

        Args:
            snapshot_date: Date for the snapshot (defaults to today)

        Returns:
            Number of snapshots created
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Get all outlet IDs
        query = select(Outlet.id)
        result = await self.db.execute(query)
        outlet_ids = [row[0] for row in result.all()]

        count = 0
        for outlet_id in outlet_ids:
            stats = await self.calculate_outlet_disparity(outlet_id)
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

        await self.db.commit()
        return count

    async def generate_game_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> int:
        """
        Generate disparity snapshots for all games.

        Args:
            snapshot_date: Date for the snapshot (defaults to today)

        Returns:
            Number of snapshots created
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Get all game IDs that have reviews
        query = select(func.distinct(Review.game_id))
        result = await self.db.execute(query)
        game_ids = [row[0] for row in result.all()]

        count = 0
        for game_id in game_ids:
            stats = await self.calculate_game_disparity(game_id)
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

        await self.db.commit()
        return count

    async def generate_all_snapshots(
        self,
        snapshot_date: Optional[date] = None,
    ) -> Dict[str, int]:
        """
        Generate all disparity snapshots for journalists, outlets, and games.

        Args:
            snapshot_date: Date for the snapshot (defaults to today)

        Returns:
            Dictionary with counts for each entity type
        """
        journalist_count = await self.generate_journalist_snapshots(snapshot_date)
        outlet_count = await self.generate_outlet_snapshots(snapshot_date)
        game_count = await self.generate_game_snapshots(snapshot_date)

        return {
            "journalists": journalist_count,
            "outlets": outlet_count,
            "games": game_count,
        }

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
        """
        Compute aggregate statistics from disparity lists.

        Args:
            steam_disparities: List of Steam disparity values
            metacritic_disparities: List of Metacritic disparity values
            combined_disparities: List of combined disparity values
            review_count: Total number of reviews

        Returns:
            Dictionary with computed statistics
        """
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

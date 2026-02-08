"""Stats API endpoints."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game, Review, UserScore, UserScoreSource
from app.schemas.schemas import SiteStats, ReviewWithJournalist

router = APIRouter()

# Anti-gaming: minimum user reviews required for a game to count (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20


@router.get("", response_model=SiteStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get site-wide statistics."""
    # Subquery for journalists with scored reviews
    journalist_with_reviews_subq = (
        select(Review.journalist_id)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .distinct()
        .subquery()
    )

    # Count journalists (only those with scored reviews)
    journalist_count_query = (
        select(func.count())
        .select_from(journalist_with_reviews_subq)
    )
    journalist_result = await db.execute(journalist_count_query)
    total_journalists = journalist_result.scalar() or 0

    # Subquery for outlets with scored reviews
    outlet_with_reviews_subq = (
        select(Review.outlet_id)
        .where(
            Review.outlet_id.isnot(None),
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .distinct()
        .subquery()
    )

    # Count outlets (only those with scored reviews)
    outlet_count_query = (
        select(func.count())
        .select_from(outlet_with_reviews_subq)
    )
    outlet_result = await db.execute(outlet_count_query)
    total_outlets = outlet_result.scalar() or 0

    # Subquery for games with critic reviews
    games_with_reviews_subq = (
        select(Review.game_id)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .distinct()
        .subquery()
    )

    # Subquery for games with Steam user scores (50+ reviews)
    steam_subq = (
        select(UserScore.game_id, UserScore.sample_size)
        .where(UserScore.source == "STEAM")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Subquery for games with Metacritic user scores (50+ reviews)
    metacritic_subq = (
        select(UserScore.game_id, UserScore.sample_size)
        .where(UserScore.source == "METACRITIC")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Count games (only those with critic reviews AND at least one user score with 50+ reviews)
    game_count_query = (
        select(func.count(Game.id.distinct()))
        .select_from(Game)
        .join(games_with_reviews_subq, Game.id == games_with_reviews_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
        .where(
            or_(
                steam_subq.c.sample_size >= MIN_STEAM_USER_REVIEWS,
                metacritic_subq.c.sample_size >= MIN_METACRITIC_USER_REVIEWS,
            )
        )
    )
    game_result = await db.execute(game_count_query)
    total_games = game_result.scalar() or 0

    # Count reviews (only scored reviews)
    review_count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
    )
    review_result = await db.execute(review_count_query)
    total_reviews = review_result.scalar() or 0

    # Calculate site-wide average disparity dynamically
    # Get all scored reviews with user scores
    all_reviews_query = (
        select(Review, Game)
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
    )
    all_reviews_result = await db.execute(all_reviews_query)
    all_reviews = all_reviews_result.all()

    # Get user scores for all games
    game_ids = list(set(row[1].id for row in all_reviews)) if all_reviews else []
    user_score_lookup: dict = {}
    if game_ids:
        user_scores_query = (
            select(UserScore)
            .where(UserScore.game_id.in_(game_ids))
            .order_by(desc(UserScore.scraped_at))
        )
        user_scores_result = await db.execute(user_scores_query)
        user_scores = user_scores_result.scalars().all()
        for us in user_scores:
            key = (us.game_id, us.source.value)
            if key not in user_score_lookup:
                user_score_lookup[key] = us.score

    # Calculate average disparity
    all_disparities = []
    for review, game in all_reviews:
        steam_score = user_score_lookup.get((game.id, "steam"))
        metacritic_score = user_score_lookup.get((game.id, "metacritic"))
        if steam_score is not None:
            all_disparities.append(float(review.score_normalized - steam_score))
        if metacritic_score is not None:
            all_disparities.append(float(review.score_normalized - metacritic_score))

    avg_disparity = None
    if all_disparities:
        avg_disparity = Decimal(str(round(sum(all_disparities) / len(all_disparities), 2)))

    return SiteStats(
        total_journalists=total_journalists,
        total_outlets=total_outlets,
        total_games=total_games,
        total_reviews=total_reviews,
        avg_disparity_site=avg_disparity,
        last_updated=datetime.utcnow(),
    )


@router.get("/recent-reviews", response_model=list[ReviewWithJournalist])
async def get_recent_reviews(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Get most recent reviews site-wide."""
    from decimal import Decimal

    # Get recent reviews with journalist, game, and outlet info
    query = (
        select(Review, Journalist, Game, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
            Review.published_at.isnot(None),
        )
        .order_by(desc(Review.published_at))
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return []

    # Get user scores for these games
    game_ids = list(set(row[2].id for row in rows))
    user_score_lookup: dict = {}
    if game_ids:
        user_scores_query = (
            select(UserScore)
            .where(UserScore.game_id.in_(game_ids))
            .order_by(desc(UserScore.scraped_at))
        )
        user_scores_result = await db.execute(user_scores_query)
        user_scores = user_scores_result.scalars().all()
        for us in user_scores:
            key = (us.game_id, us.source.value.lower())
            if key not in user_score_lookup:
                user_score_lookup[key] = {"score": us.score, "sample_size": us.sample_size or 0}

    items = []
    for review, journalist, game, outlet in rows:
        steam_data = user_score_lookup.get((game.id, "steam"))
        metacritic_data = user_score_lookup.get((game.id, "metacritic"))

        # Only use scores if they meet minimum sample size
        steam_user_score = steam_data["score"] if steam_data and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS else None
        metacritic_user_score = metacritic_data["score"] if metacritic_data and metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS else None

        disparity_steam = None
        disparity_metacritic = None

        if steam_user_score and review.score_normalized:
            disparity_steam = review.score_normalized - steam_user_score
        if metacritic_user_score and review.score_normalized:
            disparity_metacritic = review.score_normalized - metacritic_user_score

        # Calculate review timing
        review_timing = "unknown"
        is_launch_window = False
        if review.published_at and game.release_date:
            review_date = review.published_at.date() if hasattr(review.published_at, 'date') else review.published_at
            days_diff = (review_date - game.release_date).days
            if days_diff < 0:
                review_timing = "early"
            elif days_diff <= 60:
                review_timing = "launch_window"
                is_launch_window = True
            else:
                review_timing = "late"

        items.append(
            ReviewWithJournalist(
                id=review.id,
                journalist_id=review.journalist_id,
                game_id=review.game_id,
                outlet_id=review.outlet_id,
                score_raw=review.score_raw,
                score_scale=review.score_scale,
                score_normalized=review.score_normalized,
                review_url=review.review_url,
                snippet=review.snippet,
                published_at=review.published_at,
                journalist_name=journalist.name,
                journalist_image_url=journalist.image_url,
                outlet_name=outlet.name if outlet else None,
                game_title=game.title,
                game_release_date=game.release_date,
                disparity_steam=disparity_steam,
                disparity_metacritic=disparity_metacritic,
                is_launch_window=is_launch_window,
                review_timing=review_timing,
            )
        )

    return items

"""Stats API endpoints."""

import json
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game, Review, UserScore
from app.schemas.schemas import SiteStats, ReviewWithJournalist
from app.cache import get_cached, set_cached, CACHE_TTL_SHORT

router = APIRouter()

# Anti-gaming: minimum user reviews required for a game to count (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20


@router.get("", response_model=SiteStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get site-wide statistics (fast using denormalized columns)."""
    # Count journalists with disparity data (uses index)
    journalist_count = await db.execute(
        select(func.count()).select_from(Journalist).where(Journalist.avg_disparity.isnot(None))
    )
    total_journalists = journalist_count.scalar() or 0

    # Count outlets with disparity data (uses index)
    outlet_count = await db.execute(
        select(func.count()).select_from(Outlet).where(Outlet.avg_disparity.isnot(None))
    )
    total_outlets = outlet_count.scalar() or 0

    # Count games with scored reviews
    games_with_reviews = (
        select(Review.game_id)
        .where(Review.score_normalized.isnot(None), Review.score_normalized > 0)
        .distinct()
        .subquery()
    )
    game_count = await db.execute(
        select(func.count()).select_from(games_with_reviews)
    )
    total_games = game_count.scalar() or 0

    # Count scored reviews (simple count)
    review_count = await db.execute(
        select(func.count()).select_from(Review).where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
        )
    )
    total_reviews = review_count.scalar() or 0

    # Calculate site-wide avg disparity from pre-computed journalist averages
    avg_disparity_result = await db.execute(
        select(func.avg(Journalist.avg_disparity))
        .where(Journalist.avg_disparity.isnot(None))
    )
    avg_disparity = avg_disparity_result.scalar()
    if avg_disparity is not None:
        avg_disparity = Decimal(str(round(float(avg_disparity), 2)))

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
    """Get most recent reviews site-wide (cached for 60 seconds)."""
    # Check cache first
    cache_key = f"recent-reviews:{limit}"
    cached = await get_cached(cache_key)
    if cached:
        data = json.loads(cached)
        return [ReviewWithJournalist(**item) for item in data]

    today = datetime.utcnow()

    # Get recent reviews with journalist, game, and outlet
    query = (
        select(Review, Journalist, Game, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
            Review.published_at.isnot(None),
            Review.published_at <= today,
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
                user_score_lookup[key] = {"score": us.score, "sample_size": us.sample_size}

    items = []
    for review, journalist, game, outlet in rows:
        steam_data = user_score_lookup.get((game.id, "steam"))
        metacritic_data = user_score_lookup.get((game.id, "metacritic"))

        # Only use scores if they meet minimum sample size
        steam_user_score = steam_data["score"] if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS else None
        metacritic_user_score = metacritic_data["score"] if metacritic_data and metacritic_data["score"] and (
            metacritic_data["sample_size"] is None or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
        ) else None

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

    # Cache the result for 60 seconds
    await set_cached(cache_key, json.dumps([item.model_dump(mode='json') for item in items]), CACHE_TTL_SHORT)

    return items


@router.get("/sitemap-data")
async def get_sitemap_data(
    db: AsyncSession = Depends(get_db),
):
    """Get all entity IDs for sitemap generation."""
    journalist_query = (
        select(Journalist.id)
        .where(
            Journalist.id.in_(
                select(Review.journalist_id)
                .where(Review.score_normalized.isnot(None), Review.score_normalized > 0)
                .distinct()
            )
        )
    )
    journalist_result = await db.execute(journalist_query)
    journalist_ids = [row[0] for row in journalist_result.all()]

    outlet_query = (
        select(Outlet.id)
        .where(
            Outlet.id.in_(
                select(Review.outlet_id)
                .where(
                    Review.outlet_id.isnot(None),
                    Review.score_normalized.isnot(None),
                    Review.score_normalized > 0,
                )
                .distinct()
            )
        )
    )
    outlet_result = await db.execute(outlet_query)
    outlet_ids = [row[0] for row in outlet_result.all()]

    game_query = (
        select(Game.id)
        .where(
            Game.id.in_(
                select(Review.game_id)
                .where(Review.score_normalized.isnot(None), Review.score_normalized > 0)
                .distinct()
            )
        )
    )
    game_result = await db.execute(game_query)
    game_ids = [row[0] for row in game_result.all()]

    return {
        "journalist_ids": journalist_ids,
        "outlet_ids": outlet_ids,
        "game_ids": game_ids,
    }

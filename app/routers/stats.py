"""Stats API endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game, Review
from app.schemas.schemas import (
    SiteStats,
    ReviewWithJournalist,
    TrendingGamesResponse,
    TrendingGameItem,
)
from app.cache import get_cached, set_cached, CACHE_TTL_SHORT
from app.services.site_stats import get_stored_site_stats_snapshot, refresh_site_stats_snapshot
from app.services.review_score_correction import corrected_normalized_score
from app.services.trending import TrendingAggregator

router = APIRouter()

@router.get("", response_model=SiteStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get site-wide statistics from a stored snapshot (fallback computes and stores)."""
    snapshot = await get_stored_site_stats_snapshot(db)
    if snapshot:
        return snapshot

    # Fallback path for first boot / empty cache-store.
    return await refresh_site_stats_snapshot(db)


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

    today = datetime.now(timezone.utc)

    # Get recent reviews with journalist, game, and outlet
    query = (
        select(Review, Journalist, Game, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.score_normalized.isnot(None),
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

    items = []
    corrected_count = 0
    for review, journalist, game, outlet in rows:
        corrected_score, was_corrected = corrected_normalized_score(
            score_raw=review.score_raw,
            score_scale=review.score_scale,
            stored_score_normalized=review.score_normalized,
        )
        if was_corrected:
            corrected_count += 1

        disparity_steam = review.cached_disparity_steam
        disparity_metacritic = review.cached_disparity_metacritic

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
                journalist_public_id=journalist.public_id or str(journalist.id),
                game_id=review.game_id,
                game_public_id=game.public_id or str(game.id),
                outlet_id=review.outlet_id,
                outlet_public_id=(outlet.public_id or str(outlet.id)) if outlet else None,
                score_raw=review.score_raw,
                score_scale=review.score_scale,
                score_normalized=corrected_score,
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

    if corrected_count:
        print(
            "Runtime score corrections (stats recent reviews): "
            f"{corrected_count}/{len(rows)}"
        )

    # Cache the result for 60 seconds
    await set_cached(cache_key, json.dumps([item.model_dump(mode='json') for item in items]), CACHE_TTL_SHORT)

    return items


@router.get("/trending-games", response_model=TrendingGamesResponse)
async def get_trending_games(
    limit: int = Query(8, ge=1, le=25),
    window_hours: int = Query(48, ge=6, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get trending games/topics from the pluggable trend aggregator."""
    cache_key = f"stats:trending-games:limit={limit}:window={window_hours}"
    cached = await get_cached(cache_key)
    if cached:
        return TrendingGamesResponse(**json.loads(cached))

    as_of = datetime.now(timezone.utc)
    aggregator = TrendingAggregator()
    rows = await aggregator.list_trending(
        db,
        limit=limit,
        window_hours=window_hours,
        now=as_of,
    )

    response = TrendingGamesResponse(
        as_of=as_of,
        window_hours=window_hours,
        items=[TrendingGameItem(**row) for row in rows],
    )
    await set_cached(cache_key, response.model_dump_json(), CACHE_TTL_SHORT)
    return response


@router.get("/sitemap-data")
async def get_sitemap_data(
    db: AsyncSession = Depends(get_db),
):
    """Get all entity identifiers for sitemap generation."""
    journalist_query = (
        select(Journalist.id, Journalist.public_id)
        .where(
            Journalist.id.in_(
                select(Review.journalist_id)
                .where(Review.score_normalized.isnot(None))
                .distinct()
            )
        )
    )
    journalist_result = await db.execute(journalist_query)
    journalist_rows = journalist_result.all()
    journalist_ids = [row[0] for row in journalist_rows]
    journalist_public_ids = [row[1] or str(row[0]) for row in journalist_rows]

    outlet_query = (
        select(Outlet.id, Outlet.public_id)
        .where(
            Outlet.id.in_(
                select(Review.outlet_id)
                .where(
                    Review.outlet_id.isnot(None),
                    Review.score_normalized.isnot(None),
                )
                .distinct()
            )
        )
    )
    outlet_result = await db.execute(outlet_query)
    outlet_rows = outlet_result.all()
    outlet_ids = [row[0] for row in outlet_rows]
    outlet_public_ids = [row[1] or str(row[0]) for row in outlet_rows]

    game_query = (
        select(Game.id, Game.public_id)
        .where(
            Game.id.in_(
                select(Review.game_id)
                .where(Review.score_normalized.isnot(None))
                .distinct()
            )
        )
    )
    game_result = await db.execute(game_query)
    game_rows = game_result.all()
    game_ids = [row[0] for row in game_rows]
    game_public_ids = [row[1] or str(row[0]) for row in game_rows]

    return {
        "journalist_ids": journalist_ids,
        "journalist_public_ids": journalist_public_ids,
        "outlet_ids": outlet_ids,
        "outlet_public_ids": outlet_public_ids,
        "game_ids": game_ids,
        "game_public_ids": game_public_ids,
    }

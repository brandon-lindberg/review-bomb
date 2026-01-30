"""Search API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game, Review
from app.schemas.schemas import (
    JournalistSummary,
    OutletSummary,
    GameSummary,
    SearchResult,
)

router = APIRouter()


@router.get("", response_model=SearchResult)
async def search(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search across journalists, outlets, and games."""
    search_term = f"%{q.lower()}%"

    # Search journalists
    journalist_query = (
        select(Journalist)
        .where(func.lower(Journalist.name).like(search_term))
        .limit(limit)
    )
    journalist_result = await db.execute(journalist_query)
    journalists = journalist_result.scalars().all()

    # Get review counts for journalists
    journalist_ids = [j.id for j in journalists]
    if journalist_ids:
        review_counts_query = (
            select(
                Review.journalist_id,
                func.count(Review.id).label("review_count"),
            )
            .where(Review.journalist_id.in_(journalist_ids))
            .group_by(Review.journalist_id)
        )
        review_counts_result = await db.execute(review_counts_query)
        review_counts = {row[0]: row[1] for row in review_counts_result.all()}
    else:
        review_counts = {}

    journalist_items = [
        JournalistSummary(
            id=j.id,
            name=j.name,
            image_url=j.image_url,
            bio=j.bio,
            opencritic_id=j.opencritic_id,
            review_count=review_counts.get(j.id, 0),
            avg_disparity=None,
        )
        for j in journalists
    ]

    # Search outlets
    outlet_query = (
        select(Outlet)
        .where(func.lower(Outlet.name).like(search_term))
        .limit(limit)
    )
    outlet_result = await db.execute(outlet_query)
    outlets = outlet_result.scalars().all()

    outlet_items = [
        OutletSummary(
            id=o.id,
            name=o.name,
            website_url=o.website_url,
            logo_url=o.logo_url,
            opencritic_id=o.opencritic_id,
        )
        for o in outlets
    ]

    # Search games
    game_query = (
        select(Game)
        .where(func.lower(Game.title).like(search_term))
        .order_by(Game.release_date.desc().nulls_last())
        .limit(limit)
    )
    game_result = await db.execute(game_query)
    games = game_result.scalars().all()

    # Get review counts for games
    game_ids = [g.id for g in games]
    if game_ids:
        game_review_counts_query = (
            select(
                Review.game_id,
                func.count(Review.id).label("review_count"),
            )
            .where(Review.game_id.in_(game_ids))
            .group_by(Review.game_id)
        )
        game_review_counts_result = await db.execute(game_review_counts_query)
        game_review_counts = {row[0]: row[1] for row in game_review_counts_result.all()}
    else:
        game_review_counts = {}

    game_items = [
        GameSummary(
            id=g.id,
            title=g.title,
            release_date=g.release_date,
            description=g.description,
            image_url=g.image_url,
            opencritic_id=g.opencritic_id,
            steam_app_id=g.steam_app_id,
            critic_review_count=game_review_counts.get(g.id, 0),
        )
        for g in games
    ]

    return SearchResult(
        journalists=journalist_items,
        outlets=outlet_items,
        games=game_items,
    )

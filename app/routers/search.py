"""Search API endpoints - uses denormalized columns for speed."""

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings
from app.database import get_db
from app.models.models import Journalist, Outlet, Game
from app.schemas.schemas import (
    JournalistSummary,
    OutletSummary,
    GameSummary,
    SearchResult,
)

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


def _compact_search_value(value: str) -> str:
    """Normalize search text so punctuation differences do not block matches."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _escape_like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_match_clause(column, query: str):
    normalized_query = query.strip().lower()
    literal_pattern = f"%{_escape_like_value(normalized_query)}%"
    compact_query = _compact_search_value(normalized_query)

    clauses = [func.lower(column).like(literal_pattern, escape="\\")]
    if compact_query:
        compact_column = func.regexp_replace(func.lower(column), "[^a-z0-9]+", "", "g")
        clauses.append(compact_column.like(f"%{compact_query}%", escape="\\"))

    return or_(*clauses)


@router.get("", response_model=SearchResult)
@limiter.limit(f"{settings.search_rate_limit_per_minute}/minute")
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search across journalists, outlets, and games using denormalized data."""
    search_query = q.strip()
    if len(search_query) < 2:
        return SearchResult()

    # Search journalists - use denormalized review_count_scored and avg_disparity
    journalist_query = (
        select(Journalist)
        .where(_search_match_clause(Journalist.name, search_query))
        .limit(limit)
    )
    journalist_result = await db.execute(journalist_query)
    journalists = journalist_result.scalars().all()

    journalist_items = [
        JournalistSummary(
            id=j.id,
            public_id=j.public_id or str(j.id),
            name=j.name,
            image_url=j.image_url,
            bio=j.bio,
            opencritic_id=j.opencritic_id,
            review_count=j.review_count_scored or 0,
            avg_disparity=j.avg_disparity,
        )
        for j in journalists
    ]

    # Search outlets
    outlet_query = (
        select(Outlet)
        .where(_search_match_clause(Outlet.name, search_query))
        .limit(limit)
    )
    outlet_result = await db.execute(outlet_query)
    outlets = outlet_result.scalars().all()

    outlet_items = [
        OutletSummary(
            id=o.id,
            public_id=o.public_id or str(o.id),
            name=o.name,
            website_url=o.website_url,
            logo_url=o.logo_url,
            opencritic_id=o.opencritic_id,
            journalist_count=o.journalist_count or 0,
            review_count=o.review_count_scored or 0,
            avg_disparity=o.avg_disparity,
        )
        for o in outlets
    ]

    # Search games - use denormalized critic_review_count
    game_query = (
        select(Game)
        .where(_search_match_clause(Game.title, search_query))
        .order_by(desc(func.coalesce(Game.release_date, func.date(Game.created_at))))
        .limit(limit)
    )
    game_result = await db.execute(game_query)
    games = game_result.scalars().all()

    game_items = [
        GameSummary(
            id=g.id,
            public_id=g.public_id or str(g.id),
            title=g.title,
            release_date=g.release_date,
            description=g.description,
            image_url=g.image_url,
            opencritic_id=g.opencritic_id,
            steam_app_id=g.steam_app_id,
            critic_review_count=g.critic_review_count or 0,
            steam_current_players=g.steam_current_players,
        )
        for g in games
    ]

    return SearchResult(
        journalists=journalist_items,
        outlets=outlet_items,
        games=game_items,
    )

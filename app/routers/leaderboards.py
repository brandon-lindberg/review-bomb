"""Leaderboards API endpoints - uses denormalized columns for speed."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, asc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game
from app.schemas.schemas import (
    JournalistRanking,
    OutletRanking,
    GameRanking,
    PaginatedResponse,
)

router = APIRouter()

# Anti-gaming: minimum requirements for leaderboard inclusion
MIN_REVIEWS_FOR_LEADERBOARD = 10
MIN_SCORE_STD_DEV = 10  # Minimum score standard deviation (filters out binary/extreme scorers)


@router.get("/journalists", response_model=PaginatedResponse[JournalistRanking])
async def journalist_leaderboard(
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", regex="^(highest|lowest|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get journalists ranked by disparity (uses denormalized columns - instant!)."""
    # Simple query using pre-calculated columns
    query = (
        select(Journalist)
        .where(
            Journalist.avg_disparity.isnot(None),
            Journalist.review_count_scored >= MIN_REVIEWS_FOR_LEADERBOARD,
            func.coalesce(Journalist.score_std_dev, 0) >= MIN_SCORE_STD_DEV,
        )
    )

    # Sort
    if sort == "recent":
        query = query.order_by(desc(Journalist.last_review_at).nulls_last())
    elif sort == "highest":
        query = query.order_by(
            desc(func.abs(Journalist.avg_disparity)).nulls_last(),
            desc(Journalist.review_count_scored).nulls_last(),
            asc(Journalist.id),
        )
    else:
        query = query.order_by(
            asc(func.abs(Journalist.avg_disparity)).nulls_last(),
            desc(Journalist.review_count_scored).nulls_last(),
            asc(Journalist.id),
        )

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Journalist)
        .where(
            Journalist.avg_disparity.isnot(None),
            Journalist.review_count_scored >= MIN_REVIEWS_FOR_LEADERBOARD,
            func.coalesce(Journalist.score_std_dev, 0) >= MIN_SCORE_STD_DEV,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    journalists = result.scalars().all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, journalist in enumerate(journalists):
        items.append(
            JournalistRanking(
                rank=start_rank + i,
                journalist_id=journalist.id,
                journalist_name=journalist.name,
                journalist_image_url=journalist.image_url,
                outlet_name=journalist.primary_outlet,
                avg_disparity=journalist.avg_disparity,
                review_count=journalist.review_count_scored or 0,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/outlets", response_model=PaginatedResponse[OutletRanking])
async def outlet_leaderboard(
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", regex="^(highest|lowest|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get outlets ranked by disparity (uses denormalized columns - instant!)."""
    # Simple query using pre-calculated columns
    query = (
        select(Outlet)
        .where(
            Outlet.avg_disparity.isnot(None),
            Outlet.review_count_scored >= MIN_REVIEWS_FOR_LEADERBOARD,
            func.coalesce(Outlet.score_std_dev, 0) >= MIN_SCORE_STD_DEV,
        )
    )

    # Sort
    if sort == "recent":
        query = query.order_by(desc(Outlet.last_review_at).nulls_last())
    elif sort == "highest":
        query = query.order_by(
            desc(func.abs(Outlet.avg_disparity)).nulls_last(),
            desc(Outlet.review_count_scored).nulls_last(),
            asc(Outlet.id),
        )
    else:
        query = query.order_by(
            asc(func.abs(Outlet.avg_disparity)).nulls_last(),
            desc(Outlet.review_count_scored).nulls_last(),
            asc(Outlet.id),
        )

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Outlet)
        .where(
            Outlet.avg_disparity.isnot(None),
            Outlet.review_count_scored >= MIN_REVIEWS_FOR_LEADERBOARD,
            func.coalesce(Outlet.score_std_dev, 0) >= MIN_SCORE_STD_DEV,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    outlets = result.scalars().all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, outlet in enumerate(outlets):
        items.append(
            OutletRanking(
                rank=start_rank + i,
                outlet_id=outlet.id,
                outlet_name=outlet.name,
                outlet_logo_url=outlet.logo_url,
                avg_disparity=outlet.avg_disparity,
                journalist_count=outlet.journalist_count or 0,
                review_count=outlet.review_count_scored or 0,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


# Anti-gaming: minimum requirements for a game to appear in leaderboards
MIN_STEAM_USER_REVIEWS = 50  # Minimum Steam user reviews
MIN_METACRITIC_USER_REVIEWS = 20  # Minimum Metacritic user reviews
MIN_CRITIC_REVIEWS_FOR_GAME = 10  # Minimum journalist reviews


@router.get("/games", response_model=PaginatedResponse[GameRanking])
async def game_leaderboard(
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", regex="^(highest|lowest|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get games ranked by disparity (uses denormalized columns - instant!)."""
    # Simple query using pre-calculated columns
    query = (
        select(Game)
        .where(
            Game.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAME,
            # At least one disparity must exist
            or_(
                Game.disparity_steam.isnot(None),
                Game.disparity_metacritic.isnot(None),
            )
        )
    )

    combined_disparity_expr = func.coalesce(
        (Game.disparity_steam + Game.disparity_metacritic) / 2,
        Game.disparity_steam,
        Game.disparity_metacritic,
    )

    # Sort using pre-computed disparities
    if sort == "recent":
        query = query.order_by(
            desc(func.coalesce(Game.release_date, func.date(Game.created_at)))
        )
    elif sort == "highest":
        query = query.order_by(
            desc(func.abs(combined_disparity_expr)).nulls_last(),
            desc(func.coalesce(Game.release_date, func.date(Game.created_at))).nulls_last(),
            asc(Game.id),
        )
    else:
        query = query.order_by(
            asc(func.abs(combined_disparity_expr)).nulls_last(),
            desc(func.coalesce(Game.release_date, func.date(Game.created_at))).nulls_last(),
            asc(Game.id),
        )

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Game)
        .where(
            Game.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAME,
            or_(
                Game.disparity_steam.isnot(None),
                Game.disparity_metacritic.isnot(None),
            )
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    games = result.scalars().all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, game in enumerate(games):
        # Calculate combined disparity (average if both exist)
        if game.disparity_steam is not None and game.disparity_metacritic is not None:
            combined = (float(game.disparity_steam) + float(game.disparity_metacritic)) / 2
            disparity = Decimal(str(round(combined, 2)))
        else:
            disparity = game.disparity_steam or game.disparity_metacritic or Decimal("0")

        items.append(
            GameRanking(
                rank=start_rank + i,
                game_id=game.id,
                game_title=game.title,
                game_image_url=game.image_url,
                release_date=game.release_date,
                avg_critic_score=game.avg_critic_score or Decimal("0"),
                steam_user_score=game.steam_user_score,
                metacritic_user_score=game.metacritic_user_score,
                disparity=disparity,
                disparity_steam=game.disparity_steam,
                disparity_metacritic=game.disparity_metacritic,
                critic_review_count=game.critic_review_count or 0,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

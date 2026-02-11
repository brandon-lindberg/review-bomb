"""Leaderboards API endpoints."""

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import (
    Journalist, Outlet, Game, Review, UserScore
)
from app.schemas.schemas import (
    JournalistRanking,
    OutletRanking,
    GameRanking,
    PaginatedResponse,
)
from app.cache import get_cached, set_cached, CACHE_TTL_MEDIUM

router = APIRouter()

# Anti-gaming: minimum requirements for leaderboard inclusion
MIN_REVIEWS_FOR_LEADERBOARD = 10
MIN_SCORE_STD_DEV = 10  # Minimum score standard deviation (filters out binary/extreme scorers)


@router.get("/journalists", response_model=PaginatedResponse[JournalistRanking])
async def journalist_leaderboard(
    page: int = Query(1, ge=1),
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
        query = query.order_by(desc(Journalist.avg_disparity))
    else:
        query = query.order_by(asc(Journalist.avg_disparity))

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
    page: int = Query(1, ge=1),
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
        query = query.order_by(desc(Outlet.avg_disparity))
    else:
        query = query.order_by(asc(Outlet.avg_disparity))

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
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", regex="^(highest|lowest|recent)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get games ranked by disparity (cached for 5 minutes)."""
    # Check cache first
    cache_key = f"leaderboard:games:{page}:{per_page}:{sort}"
    cached = await get_cached(cache_key)
    if cached:
        data = json.loads(cached)
        return PaginatedResponse[GameRanking](**data)
    
    # Subquery for avg critic score (only reviews with actual scores)
    critic_subq = (
        select(
            Review.game_id,
            func.avg(Review.score_normalized).label("avg_critic_score"),
            func.count(Review.id).label("critic_review_count"),
        )
        .where(
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .group_by(Review.game_id)
        .subquery()
    )

    # Subquery for latest Steam score (with sample_size for filtering)
    steam_subq = (
        select(
            UserScore.game_id,
            UserScore.score.label("steam_score"),
            UserScore.sample_size.label("steam_sample_size"),
        )
        .where(UserScore.source == "STEAM")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Subquery for latest Metacritic score (with sample_size for filtering)
    metacritic_subq = (
        select(
            UserScore.game_id,
            UserScore.score.label("metacritic_score"),
            UserScore.sample_size.label("metacritic_sample_size"),
        )
        .where(UserScore.source == "METACRITIC")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Calculate individual disparities (critic - user)
    steam_disparity_expr = critic_subq.c.avg_critic_score - steam_subq.c.steam_score
    metacritic_disparity_expr = critic_subq.c.avg_critic_score - metacritic_subq.c.metacritic_score

    # Combined disparity: average when both exist, otherwise use whichever is available
    disparity_expr = case(
        (
            (steam_disparity_expr.isnot(None)) & (metacritic_disparity_expr.isnot(None)),
            (steam_disparity_expr + metacritic_disparity_expr) / 2
        ),
        else_=func.coalesce(steam_disparity_expr, metacritic_disparity_expr)
    )

    query = (
        select(
            Game,
            critic_subq.c.avg_critic_score,
            critic_subq.c.critic_review_count,
            steam_subq.c.steam_score,
            metacritic_subq.c.metacritic_score,
            steam_disparity_expr.label("steam_disparity"),
            metacritic_disparity_expr.label("metacritic_disparity"),
            disparity_expr.label("disparity"),
        )
        .join(critic_subq, Game.id == critic_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
        .where(
            # Minimum 10 critic reviews
            critic_subq.c.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAME,
            # At least one user score must exist with enough reviews (anti-gaming)
            (
                (steam_subq.c.steam_score.isnot(None)) &
                (func.coalesce(steam_subq.c.steam_sample_size, 0) >= MIN_STEAM_USER_REVIEWS)
            ) | (
                # Allow Metacritic if score exists and (sample_size is NULL or meets minimum)
                (metacritic_subq.c.metacritic_score.isnot(None)) &
                (
                    (metacritic_subq.c.metacritic_sample_size.is_(None)) |
                    (metacritic_subq.c.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS)
                )
            )
        )
    )

    # Sort
    if sort == "recent":
        query = query.order_by(desc(Game.release_date).nulls_last())
    elif sort == "highest":
        query = query.order_by(desc(func.abs(disparity_expr)))
    else:
        query = query.order_by(asc(func.abs(disparity_expr)))

    # Get total count (games with 10+ critic reviews AND at least one user score meeting threshold)
    count_subq = (
        select(Game.id)
        .join(critic_subq, Game.id == critic_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
        .where(
            # Minimum 10 critic reviews
            critic_subq.c.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAME,
            # At least one user score meeting threshold
            (
                (steam_subq.c.steam_score.isnot(None)) &
                (func.coalesce(steam_subq.c.steam_sample_size, 0) >= MIN_STEAM_USER_REVIEWS)
            ) | (
                # Allow Metacritic if score exists and (sample_size is NULL or meets minimum)
                (metacritic_subq.c.metacritic_score.isnot(None)) &
                (
                    (metacritic_subq.c.metacritic_sample_size.is_(None)) |
                    (metacritic_subq.c.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS)
                )
            )
        )
    )
    count_query = select(func.count()).select_from(count_subq.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, row in enumerate(rows):
        game = row[0]
        avg_critic = row[1]
        critic_count = row[2]
        steam_score = row[3]
        metacritic_score = row[4]
        steam_disparity = row[5]
        metacritic_disparity = row[6]
        disparity = row[7]

        items.append(
            GameRanking(
                rank=start_rank + i,
                game_id=game.id,
                game_title=game.title,
                game_image_url=game.image_url,
                release_date=game.release_date,
                avg_critic_score=Decimal(str(round(avg_critic, 2))) if avg_critic else Decimal("0"),
                steam_user_score=steam_score,
                metacritic_user_score=metacritic_score,
                disparity=Decimal(str(round(disparity, 2))) if disparity else Decimal("0"),
                disparity_steam=Decimal(str(round(steam_disparity, 2))) if steam_disparity else None,
                disparity_metacritic=Decimal(str(round(metacritic_disparity, 2))) if metacritic_disparity else None,
                critic_review_count=critic_count,
            )
        )

    result = PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )
    
    # Cache the result
    await set_cached(cache_key, result.model_dump_json(), CACHE_TTL_MEDIUM)
    
    return result

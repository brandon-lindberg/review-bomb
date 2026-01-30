"""Leaderboards API endpoints."""

from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import (
    Journalist, Outlet, Game, Review, UserScore, DisparitySnapshot
)
from app.schemas.schemas import (
    JournalistRanking,
    OutletRanking,
    GameRanking,
    PaginatedResponse,
)

router = APIRouter()


@router.get("/journalists", response_model=PaginatedResponse[JournalistRanking])
async def journalist_leaderboard(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("highest", regex="^(highest|lowest)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get journalists ranked by disparity."""
    # Get latest disparity snapshot for each journalist
    latest_snapshot_subq = (
        select(
            DisparitySnapshot.journalist_id,
            DisparitySnapshot.avg_disparity_combined,
            DisparitySnapshot.review_count,
        )
        .where(DisparitySnapshot.journalist_id.isnot(None))
        .distinct(DisparitySnapshot.journalist_id)
        .order_by(
            DisparitySnapshot.journalist_id,
            desc(DisparitySnapshot.snapshot_date)
        )
        .subquery()
    )

    # Get most recent outlet for each journalist
    recent_outlet_subq = (
        select(
            Review.journalist_id,
            Outlet.name.label("outlet_name"),
        )
        .join(Outlet, Review.outlet_id == Outlet.id)
        .distinct(Review.journalist_id)
        .order_by(Review.journalist_id, desc(Review.published_at))
        .subquery()
    )

    query = (
        select(
            Journalist,
            latest_snapshot_subq.c.avg_disparity_combined,
            latest_snapshot_subq.c.review_count,
            recent_outlet_subq.c.outlet_name,
        )
        .join(latest_snapshot_subq, Journalist.id == latest_snapshot_subq.c.journalist_id)
        .outerjoin(recent_outlet_subq, Journalist.id == recent_outlet_subq.c.journalist_id)
        .where(latest_snapshot_subq.c.avg_disparity_combined.isnot(None))
    )

    # Sort by disparity
    if sort == "highest":
        query = query.order_by(desc(latest_snapshot_subq.c.avg_disparity_combined))
    else:
        query = query.order_by(asc(latest_snapshot_subq.c.avg_disparity_combined))

    # Get total count
    count_query = (
        select(func.count())
        .select_from(latest_snapshot_subq)
        .where(latest_snapshot_subq.c.avg_disparity_combined.isnot(None))
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, row in enumerate(rows):
        journalist = row[0]
        avg_disparity = row[1]
        review_count = row[2]
        outlet_name = row[3]

        items.append(
            JournalistRanking(
                rank=start_rank + i,
                journalist_id=journalist.id,
                journalist_name=journalist.name,
                journalist_image_url=journalist.image_url,
                outlet_name=outlet_name,
                avg_disparity=avg_disparity,
                review_count=review_count,
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
    sort: str = Query("highest", regex="^(highest|lowest)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get outlets ranked by disparity."""
    # Get latest disparity snapshot for each outlet
    latest_snapshot_subq = (
        select(
            DisparitySnapshot.outlet_id,
            DisparitySnapshot.avg_disparity_combined,
            DisparitySnapshot.review_count,
        )
        .where(DisparitySnapshot.outlet_id.isnot(None))
        .distinct(DisparitySnapshot.outlet_id)
        .order_by(
            DisparitySnapshot.outlet_id,
            desc(DisparitySnapshot.snapshot_date)
        )
        .subquery()
    )

    # Get journalist count per outlet
    journalist_count_subq = (
        select(
            Review.outlet_id,
            func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
        )
        .where(Review.outlet_id.isnot(None))
        .group_by(Review.outlet_id)
        .subquery()
    )

    query = (
        select(
            Outlet,
            latest_snapshot_subq.c.avg_disparity_combined,
            latest_snapshot_subq.c.review_count,
            func.coalesce(journalist_count_subq.c.journalist_count, 0).label("journalist_count"),
        )
        .join(latest_snapshot_subq, Outlet.id == latest_snapshot_subq.c.outlet_id)
        .outerjoin(journalist_count_subq, Outlet.id == journalist_count_subq.c.outlet_id)
        .where(latest_snapshot_subq.c.avg_disparity_combined.isnot(None))
    )

    # Sort by disparity
    if sort == "highest":
        query = query.order_by(desc(latest_snapshot_subq.c.avg_disparity_combined))
    else:
        query = query.order_by(asc(latest_snapshot_subq.c.avg_disparity_combined))

    # Get total count
    count_query = (
        select(func.count())
        .select_from(latest_snapshot_subq)
        .where(latest_snapshot_subq.c.avg_disparity_combined.isnot(None))
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = []
    start_rank = (page - 1) * per_page + 1
    for i, row in enumerate(rows):
        outlet = row[0]
        avg_disparity = row[1]
        review_count = row[2]
        journalist_count = row[3]

        items.append(
            OutletRanking(
                rank=start_rank + i,
                outlet_id=outlet.id,
                outlet_name=outlet.name,
                outlet_logo_url=outlet.logo_url,
                avg_disparity=avg_disparity,
                journalist_count=journalist_count,
                review_count=review_count,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/games", response_model=PaginatedResponse[GameRanking])
async def game_leaderboard(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort: str = Query("highest", regex="^(highest|lowest)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get games ranked by disparity (most divisive)."""
    # Subquery for avg critic score
    critic_subq = (
        select(
            Review.game_id,
            func.avg(Review.score_normalized).label("avg_critic_score"),
            func.count(Review.id).label("critic_review_count"),
        )
        .group_by(Review.game_id)
        .subquery()
    )

    # Subquery for latest Steam score
    steam_subq = (
        select(
            UserScore.game_id,
            UserScore.score.label("steam_score"),
        )
        .where(UserScore.source == "STEAM")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Subquery for latest Metacritic score
    metacritic_subq = (
        select(
            UserScore.game_id,
            UserScore.score.label("metacritic_score"),
        )
        .where(UserScore.source == "METACRITIC")
        .distinct(UserScore.game_id)
        .order_by(UserScore.game_id, desc(UserScore.scraped_at))
        .subquery()
    )

    # Calculate disparity as difference from steam score (or metacritic if no steam)
    disparity_expr = func.coalesce(
        critic_subq.c.avg_critic_score - steam_subq.c.steam_score,
        critic_subq.c.avg_critic_score - metacritic_subq.c.metacritic_score,
    )

    query = (
        select(
            Game,
            critic_subq.c.avg_critic_score,
            critic_subq.c.critic_review_count,
            steam_subq.c.steam_score,
            metacritic_subq.c.metacritic_score,
            disparity_expr.label("disparity"),
        )
        .join(critic_subq, Game.id == critic_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
        .where(
            # At least one user score must exist
            (steam_subq.c.steam_score.isnot(None)) |
            (metacritic_subq.c.metacritic_score.isnot(None))
        )
    )

    # Sort by absolute disparity
    if sort == "highest":
        query = query.order_by(desc(func.abs(disparity_expr)))
    else:
        query = query.order_by(asc(func.abs(disparity_expr)))

    # Get total count (games with both critic reviews and user scores)
    count_subq = (
        select(Game.id)
        .join(critic_subq, Game.id == critic_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
        .where(
            (steam_subq.c.steam_score.isnot(None)) |
            (metacritic_subq.c.metacritic_score.isnot(None))
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
        disparity = row[5]

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
                critic_review_count=critic_count,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

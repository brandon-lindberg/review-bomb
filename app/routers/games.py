"""Games API endpoints."""

from typing import Optional
from decimal import Decimal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, asc, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Game, Review, Journalist, Outlet, UserScore
from app.schemas.schemas import (
    GameSummary,
    GameDetail,
    GameWithScores,
    ReviewWithJournalist,
    PaginatedResponse,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[GameWithScores])
async def list_games(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    year: Optional[int] = Query(None, ge=2015),
    sort_by: str = Query("release_date", regex="^(release_date|title|disparity)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all games with pagination and filtering."""
    # Subquery for review count and avg critic score
    review_stats_subq = (
        select(
            Review.game_id,
            func.count(Review.id).label("critic_review_count"),
            func.avg(Review.score_normalized).label("avg_critic_score"),
        )
        .group_by(Review.game_id)
        .subquery()
    )

    # Subquery for latest Steam user score
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

    # Subquery for latest Metacritic user score
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

    query = (
        select(
            Game,
            func.coalesce(review_stats_subq.c.critic_review_count, 0).label("critic_review_count"),
            review_stats_subq.c.avg_critic_score,
            steam_subq.c.steam_score,
            steam_subq.c.steam_sample_size,
            metacritic_subq.c.metacritic_score,
            metacritic_subq.c.metacritic_sample_size,
        )
        .outerjoin(review_stats_subq, Game.id == review_stats_subq.c.game_id)
        .outerjoin(steam_subq, Game.id == steam_subq.c.game_id)
        .outerjoin(metacritic_subq, Game.id == metacritic_subq.c.game_id)
    )

    # Filter by year if provided
    if year:
        query = query.where(extract("year", Game.release_date) == year)

    # Apply sorting
    if sort_by == "release_date":
        order_col = Game.release_date
    elif sort_by == "title":
        order_col = Game.title
    else:  # disparity - sort by difference between critic and user scores
        # Use steam score for disparity sorting
        order_col = func.abs(
            review_stats_subq.c.avg_critic_score - steam_subq.c.steam_score
        )

    if sort_order == "desc":
        query = query.order_by(desc(order_col).nulls_last())
    else:
        query = query.order_by(asc(order_col).nulls_last())

    # Get total count
    count_query = select(func.count()).select_from(Game)
    if year:
        count_query = count_query.where(extract("year", Game.release_date) == year)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        game = row[0]
        critic_count = row[1]
        avg_critic = row[2]
        steam_score = row[3]
        steam_sample = row[4]
        metacritic_score = row[5]
        metacritic_sample = row[6]

        disparity_steam = None
        disparity_metacritic = None

        if avg_critic and steam_score:
            disparity_steam = Decimal(str(round(float(avg_critic) - float(steam_score), 2)))
        if avg_critic and metacritic_score:
            disparity_metacritic = Decimal(str(round(float(avg_critic) - float(metacritic_score), 2)))

        items.append(
            GameWithScores(
                id=game.id,
                title=game.title,
                release_date=game.release_date,
                description=game.description,
                image_url=game.image_url,
                opencritic_id=game.opencritic_id,
                steam_app_id=game.steam_app_id,
                critic_review_count=critic_count,
                opencritic_score=game.top_critic_score,
                steam_user_score=steam_score,
                steam_sample_size=steam_sample,
                metacritic_user_score=metacritic_score,
                metacritic_sample_size=metacritic_sample,
                avg_critic_score=Decimal(str(round(avg_critic, 2))) if avg_critic else None,
                disparity_steam=disparity_steam,
                disparity_metacritic=disparity_metacritic,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{game_id}", response_model=GameDetail)
async def get_game(
    game_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get game detail with all scores."""
    result = await db.execute(
        select(Game).where(Game.id == game_id)
    )
    game = result.scalar_one_or_none()

    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get critic stats
    critic_stats_query = select(
        func.count(Review.id).label("critic_review_count"),
        func.avg(Review.score_normalized).label("avg_critic_score"),
    ).where(Review.game_id == game_id)

    critic_result = await db.execute(critic_stats_query)
    critic_row = critic_result.one()

    # Get latest Steam score
    steam_query = (
        select(UserScore)
        .where(UserScore.game_id == game_id, UserScore.source == "STEAM")
        .order_by(desc(UserScore.scraped_at))
        .limit(1)
    )
    steam_result = await db.execute(steam_query)
    steam_score = steam_result.scalar_one_or_none()

    # Get latest Metacritic score
    metacritic_query = (
        select(UserScore)
        .where(UserScore.game_id == game_id, UserScore.source == "METACRITIC")
        .order_by(desc(UserScore.scraped_at))
        .limit(1)
    )
    metacritic_result = await db.execute(metacritic_query)
    metacritic_score = metacritic_result.scalar_one_or_none()

    avg_critic = critic_row.avg_critic_score
    disparity_steam = None
    disparity_metacritic = None

    if avg_critic and steam_score:
        disparity_steam = Decimal(str(round(float(avg_critic) - float(steam_score.score), 2)))
    if avg_critic and metacritic_score:
        disparity_metacritic = Decimal(str(round(float(avg_critic) - float(metacritic_score.score), 2)))

    return GameDetail(
        id=game.id,
        title=game.title,
        release_date=game.release_date,
        description=game.description,
        image_url=game.image_url,
        opencritic_id=game.opencritic_id,
        steam_app_id=game.steam_app_id,
        critic_review_count=critic_row.critic_review_count or 0,
        opencritic_score=game.top_critic_score,
        steam_user_score=steam_score.score if steam_score else None,
        steam_sample_size=steam_score.sample_size if steam_score else None,
        metacritic_user_score=metacritic_score.score if metacritic_score else None,
        metacritic_sample_size=metacritic_score.sample_size if metacritic_score else None,
        avg_critic_score=Decimal(str(round(avg_critic, 2))) if avg_critic else None,
        disparity_steam=disparity_steam,
        disparity_metacritic=disparity_metacritic,
        tier=game.tier,
        percent_recommended=game.percent_recommended,
        created_at=game.created_at,
        updated_at=game.updated_at,
    )


@router.get("/{game_id}/reviews", response_model=PaginatedResponse[ReviewWithJournalist])
async def get_game_reviews(
    game_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all critic reviews for a game."""
    # Verify game exists
    game_result = await db.execute(
        select(Game.id).where(Game.id == game_id)
    )
    if not game_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Game not found")

    # Get user scores for disparity calculation
    steam_query = (
        select(UserScore.score)
        .where(UserScore.game_id == game_id, UserScore.source == "STEAM")
        .order_by(desc(UserScore.scraped_at))
        .limit(1)
    )
    steam_result = await db.execute(steam_query)
    steam_score = steam_result.scalar_one_or_none()

    metacritic_query = (
        select(UserScore.score)
        .where(UserScore.game_id == game_id, UserScore.source == "METACRITIC")
        .order_by(desc(UserScore.scraped_at))
        .limit(1)
    )
    metacritic_result = await db.execute(metacritic_query)
    metacritic_score = metacritic_result.scalar_one_or_none()

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(Review.game_id == game_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews
    query = (
        select(Review, Journalist, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(Review.game_id == game_id)
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    for review, journalist, outlet in rows:
        disparity_steam = None
        disparity_metacritic = None

        if steam_score:
            disparity_steam = review.score_normalized - steam_score
        if metacritic_score:
            disparity_metacritic = review.score_normalized - metacritic_score

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
                disparity_steam=disparity_steam,
                disparity_metacritic=disparity_metacritic,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )
